"""
Chronological Backtrader validation for the final combined long + short study.

Each combined candidate represents one long finalist paired with one short
finalist. Both sides share the same portfolio equity curve, concurrency cap,
drawdown tracking, and consistency accounting.
"""

from __future__ import annotations

import argparse
import gc
import math
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import backtrader as bt
import pandas as pd
from tqdm import tqdm

from backtrader_evaluate import (
    DEFAULT_DAILY_PATH,
    DEFAULT_INTRADAY_PATH,
    INITIAL_BALANCE,
    MAX_CONCURRENT_TRADES,
    MAX_CRYPTO_LEVERAGE,
    MAX_TRAILING_DRAWDOWN_PCT,
    MarketDataCatalog,
    RISK_PER_TRADE_USD,
    STOP_LOSS_ATR_MULTIPLIER,
    TP1_ATR_MULTIPLIER,
    TP2_ATR_MULTIPLIER,
)


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

DEFAULT_CANDIDATES_PATH = os.path.join(RESULTS_DIR, "backtrader_combined_candidates.csv")
DEFAULT_OUTPUT_PREFIX = os.path.join(RESULTS_DIR, "backtrader_combined")

ATR_PERIOD = 14
FIB_LOOKBACK = 30
CONSISTENCY_LIMIT_PCT = 20.0


def first_present(row: pd.Series, names: List[str], default: object = None) -> object:
    """Return the first present, non-null value from a pandas row."""
    for name in names:
        if name in row.index and pd.notna(row[name]):
            return row[name]
    return default


def parse_boolish(value: object, default: bool = False) -> bool:
    """Parse booleans robustly from CSV-friendly values."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)

    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return default


@dataclass
class SideCandidateConfig:
    """One fully specified parameter block for either the long or short side."""

    side: str
    param_id: str
    source_symbol: str
    sma: int
    ema: int
    fib_floor: float
    fib_band: float
    rw: float
    eb: float
    rw_lookback: int
    confirm_enabled: bool
    confirm_ema_period: int
    confirm_min_distance: float
    confirm_mode: str

    @classmethod
    def from_prefixed_row(cls, row: pd.Series, prefix: str, default_side: str) -> "SideCandidateConfig":
        """Build one side configuration from a prefixed combined-candidate row."""
        return cls(
            side=str(first_present(row, [f"{prefix}_side"], default_side)).lower(),
            param_id=str(row[f"{prefix}_param_id"]),
            source_symbol=str(row[f"{prefix}_source_symbol"]),
            sma=int(row[f"{prefix}_sma"]),
            ema=int(row[f"{prefix}_ema"]),
            fib_floor=float(row[f"{prefix}_fib_floor"]),
            fib_band=float(row[f"{prefix}_fib_band"]),
            rw=float(row[f"{prefix}_rw"]),
            eb=float(row[f"{prefix}_eb"]),
            rw_lookback=int(row[f"{prefix}_rw_lookback"]),
            confirm_enabled=parse_boolish(row.get(f"{prefix}_confirm_enabled", False), default=False),
            confirm_ema_period=int(first_present(row, [f"{prefix}_confirm_ema_period"], 20)),
            confirm_min_distance=float(first_present(row, [f"{prefix}_confirm_min_distance"], 0.0)),
            confirm_mode=str(
                first_present(
                    row,
                    [f"{prefix}_confirm_mode"],
                    "close_above_ema" if default_side == "long" else "close_below_ema",
                )
            ),
        )


@dataclass
class CombinedCandidateConfig:
    """One combined long/short portfolio candidate."""

    source_rank: int
    param_id: str
    pair_family: str
    long_candidate: SideCandidateConfig
    short_candidate: SideCandidateConfig

    @classmethod
    def from_row(cls, row: pd.Series) -> "CombinedCandidateConfig":
        """Build the combined candidate from one flat CSV row."""
        rank = int(first_present(row, ["combined_rank", "rank"], 0))
        return cls(
            source_rank=rank,
            param_id=str(first_present(row, ["param_id"], f"combined_{rank:03d}")),
            pair_family=str(first_present(row, ["pair_family"], "unknown_pair")),
            long_candidate=SideCandidateConfig.from_prefixed_row(row, prefix="long", default_side="long"),
            short_candidate=SideCandidateConfig.from_prefixed_row(row, prefix="short", default_side="short"),
        )


class MavenCombinedCandidateStrategy(bt.Strategy):
    """Evaluate one combined long/short portfolio under one shared Maven account."""

    params = (
        ("candidate", None),
        ("feed_map", None),
    )

    def __init__(self) -> None:
        self.candidate: CombinedCandidateConfig = self.p.candidate
        self.feed_map: Dict[str, Dict[str, str]] = self.p.feed_map

        self.sim_cash = INITIAL_BALANCE
        self.peak_equity = INITIAL_BALANCE
        self.max_drawdown_dollars = 0.0
        self.max_drawdown_pct = 0.0
        self.breached = False
        self.account_locked = False
        self.max_positions_seen = 0

        self.closed_fragments: List[Dict[str, object]] = []
        self.closed_positions = 0
        self.trade_counter = 0
        self.signal_conflicts = 0

        self.side_fragment_counts: Dict[str, int] = {"long": 0, "short": 0}
        self.side_closed_positions: Dict[str, int] = {"long": 0, "short": 0}
        self.side_total_profit: Dict[str, float] = {"long": 0.0, "short": 0.0}

        self.asset_states: Dict[str, Dict[str, object]] = {}
        for symbol, mapping in self.feed_map.items():
            signal_data = self.getdatabyname(mapping["signal_name"])
            exec_data = self.getdatabyname(mapping["exec_name"])
            self.asset_states[symbol] = {
                "symbol": symbol,
                "data_mode": mapping["data_mode"],
                "exec_data": exec_data,
                "signal_data": signal_data,
                "last_exec_len": 0,
                "last_signal_len": 0,
                "pending_entry": None,
                "position": None,
                "atr": bt.indicators.AverageTrueRange(signal_data, period=ATR_PERIOD),
                "high30": bt.indicators.Highest(signal_data.high, period=FIB_LOOKBACK),
                "low30": bt.indicators.Lowest(signal_data.low, period=FIB_LOOKBACK),
                "long_sma": bt.indicators.SimpleMovingAverage(signal_data.close, period=self.candidate.long_candidate.sma),
                "long_ema": bt.indicators.ExponentialMovingAverage(signal_data.close, period=self.candidate.long_candidate.ema),
                "short_sma": bt.indicators.SimpleMovingAverage(signal_data.close, period=self.candidate.short_candidate.sma),
                "short_ema": bt.indicators.ExponentialMovingAverage(signal_data.close, period=self.candidate.short_candidate.ema),
                "long_confirm_ema": (
                    bt.indicators.ExponentialMovingAverage(
                        exec_data.close,
                        period=self.candidate.long_candidate.confirm_ema_period,
                    )
                    if self.candidate.long_candidate.confirm_enabled
                    else None
                ),
                "short_confirm_ema": (
                    bt.indicators.ExponentialMovingAverage(
                        exec_data.close,
                        period=self.candidate.short_candidate.confirm_ema_period,
                    )
                    if self.candidate.short_candidate.confirm_enabled
                    else None
                ),
            }

    def _active_positions(self) -> int:
        return sum(1 for state in self.asset_states.values() if state["position"] is not None)

    def _mark_price(self, state: Dict[str, object], mark: str, side: str) -> float:
        data = state["exec_data"]
        if mark == "best":
            return float(data.high[0]) if side == "long" else float(data.low[0])
        if mark == "worst":
            return float(data.low[0]) if side == "long" else float(data.high[0])
        return float(data.close[0])

    def _open_notional(self, mark: str = "close") -> float:
        notional = 0.0
        for state in self.asset_states.values():
            position = state["position"]
            if not position:
                continue
            price = self._mark_price(state, mark=mark, side=str(position["side"]))
            notional += float(position["remaining_size"]) * price
        return notional

    def _portfolio_equity(self, mark: str = "close") -> float:
        equity = self.sim_cash
        for state in self.asset_states.values():
            position = state["position"]
            if not position:
                continue

            side = str(position["side"])
            current_price = self._mark_price(state, mark=mark, side=side)
            entry_price = float(position["entry_price"])
            size = float(position["remaining_size"])
            if side == "long":
                equity += (current_price - entry_price) * size
            else:
                equity += (entry_price - current_price) * size
        return float(equity)

    def _update_drawdown_state(self) -> None:
        best_equity = self._portfolio_equity(mark="best")
        worst_equity = self._portfolio_equity(mark="worst")

        if best_equity > self.peak_equity:
            self.peak_equity = best_equity

        drawdown_dollars = max(0.0, self.peak_equity - worst_equity)
        drawdown_pct = (drawdown_dollars / self.peak_equity) if self.peak_equity > 0 else 0.0

        if drawdown_dollars > self.max_drawdown_dollars:
            self.max_drawdown_dollars = drawdown_dollars
        if drawdown_pct > self.max_drawdown_pct:
            self.max_drawdown_pct = drawdown_pct

        if drawdown_pct >= MAX_TRAILING_DRAWDOWN_PCT:
            self.breached = True
            self.account_locked = True

    def _force_liquidate_all(self, reason: str) -> None:
        for state in self.asset_states.values():
            position = state["position"]
            if not position:
                continue
            exit_price = float(state["exec_data"].close[0])
            self._close_fragment(state, float(position["remaining_size"]), exit_price, reason, force_close=True)

    def _signal_is_ready(self, state: Dict[str, object], cfg: SideCandidateConfig) -> bool:
        signal_data = state["signal_data"]
        min_required = max(cfg.sma, cfg.ema, FIB_LOOKBACK, cfg.rw_lookback, ATR_PERIOD) + 1
        if len(signal_data) < min_required:
            return False

        if not cfg.confirm_enabled:
            return True
        return len(state["exec_data"]) >= max(1, cfg.confirm_ema_period)

    def _confirmation_is_valid(self, state: Dict[str, object], cfg: SideCandidateConfig) -> bool:
        if not cfg.confirm_enabled:
            return True

        confirm_key = "long_confirm_ema" if cfg.side == "long" else "short_confirm_ema"
        confirm_ema = state[confirm_key]
        if confirm_ema is None:
            return False

        exec_close = float(state["exec_data"].close[0])
        ema_value = float(confirm_ema[0])
        if any(math.isnan(value) for value in [exec_close, ema_value]):
            return False
        if exec_close <= 0.0 or ema_value <= 0.0:
            return False

        if cfg.side == "long":
            confirm_distance = (exec_close - ema_value) / ema_value
            return bool(exec_close > ema_value and confirm_distance >= cfg.confirm_min_distance)

        confirm_distance = (ema_value - exec_close) / ema_value
        return bool(exec_close < ema_value and confirm_distance >= cfg.confirm_min_distance)

    def _signal_is_valid(self, state: Dict[str, object], cfg: SideCandidateConfig) -> Optional[Dict[str, float]]:
        if not self._signal_is_ready(state, cfg):
            return None

        signal_data = state["signal_data"]
        close = float(signal_data.close[0])
        sma_line = state["long_sma"] if cfg.side == "long" else state["short_sma"]
        ema_line = state["long_ema"] if cfg.side == "long" else state["short_ema"]
        sma = float(sma_line[0])
        ema = float(ema_line[0])
        atr = float(state["atr"][0])
        high30 = float(state["high30"][0])
        low30 = float(state["low30"][0])

        if any(math.isnan(value) for value in [close, sma, ema, atr, high30, low30]):
            return None
        if close <= 0.0 or atr <= 0.0 or high30 <= low30:
            return None

        prev_close = float(signal_data.close[-cfg.rw_lookback])
        if prev_close <= 0.0:
            return None

        ema_distance = abs(close - ema) / close
        if cfg.side == "long":
            retracement = (high30 - close) / (high30 - low30)
            rw_value = (prev_close - close) / prev_close
            is_valid = (
                close > sma
                and cfg.fib_floor <= retracement <= cfg.fib_band
                and ema_distance <= cfg.eb
                and rw_value >= cfg.rw
            )
            payload = {"retracement": retracement, "rw_value": rw_value}
        else:
            bounce_retracement = (close - low30) / (high30 - low30)
            downside_momentum = (prev_close - close) / prev_close
            is_valid = (
                close < sma
                and cfg.fib_floor <= bounce_retracement <= cfg.fib_band
                and ema_distance <= cfg.eb
                and downside_momentum >= cfg.rw
            )
            payload = {"bounce_retracement": bounce_retracement, "downside_momentum": downside_momentum}

        if not is_valid or not self._confirmation_is_valid(state, cfg):
            return None

        payload.update({"side": cfg.side, "atr": atr, "signal_close": close})
        return payload

    def _schedule_entry_if_needed(self, state: Dict[str, object]) -> None:
        """Schedule at most one next-bar entry for the current symbol."""
        if self.account_locked:
            return
        if state["position"] is not None or state["pending_entry"] is not None:
            return

        long_payload = self._signal_is_valid(state, self.candidate.long_candidate)
        short_payload = self._signal_is_valid(state, self.candidate.short_candidate)

        if long_payload and short_payload:
            self.signal_conflicts += 1
            return

        signal_payload = long_payload or short_payload
        if not signal_payload:
            return

        state["pending_entry"] = {
            "side": str(signal_payload["side"]),
            "atr": float(signal_payload["atr"]),
            "scheduled_from": bt.num2date(state["signal_data"].datetime[0]),
            "signal_close": float(signal_payload["signal_close"]),
        }

    def _try_open_pending_entry(self, state: Dict[str, object]) -> None:
        """Open one pending side-specific entry at the next execution-bar open."""
        pending = state["pending_entry"]
        if not pending:
            return

        state["pending_entry"] = None

        if self.account_locked:
            return
        if state["position"] is not None:
            return
        if self._active_positions() >= MAX_CONCURRENT_TRADES:
            return

        side = str(pending["side"])
        entry_price = float(state["exec_data"].open[0])
        atr = float(pending["atr"])
        stop_distance = atr * STOP_LOSS_ATR_MULTIPLIER

        if entry_price <= 0.0 or stop_distance <= 0.0:
            return

        current_equity = self._portfolio_equity(mark="close")
        max_notional = max(0.0, current_equity * MAX_CRYPTO_LEVERAGE)
        available_notional = max(0.0, max_notional - self._open_notional(mark="close"))

        raw_size = RISK_PER_TRADE_USD / stop_distance
        leverage_capped_size = available_notional / entry_price if entry_price > 0 else 0.0
        size = min(raw_size, leverage_capped_size)
        if size <= 0.0:
            return

        self.trade_counter += 1
        position = {
            "side": side,
            "trade_id": self.trade_counter,
            "entry_dt": bt.num2date(state["exec_data"].datetime[0]),
            "entry_price": entry_price,
            "remaining_size": size,
            "initial_size": size,
            "tp1_done": False,
        }

        if side == "long":
            position["stop_price"] = entry_price - stop_distance
            position["tp1_price"] = entry_price + (atr * TP1_ATR_MULTIPLIER)
            position["tp2_price"] = entry_price + (atr * TP2_ATR_MULTIPLIER)
        else:
            position["stop_price"] = entry_price + stop_distance
            position["tp1_price"] = entry_price - (atr * TP1_ATR_MULTIPLIER)
            position["tp2_price"] = entry_price - (atr * TP2_ATR_MULTIPLIER)

        state["position"] = position
        self.max_positions_seen = max(self.max_positions_seen, self._active_positions())

    def _close_fragment(
        self,
        state: Dict[str, object],
        size_to_close: float,
        exit_price: float,
        reason: str,
        force_close: bool = False,
    ) -> None:
        """Realize one long or short exit fragment and update all ledgers."""
        position = state["position"]
        if not position or size_to_close <= 0.0:
            return

        side = str(position["side"])
        size_to_close = min(size_to_close, float(position["remaining_size"]))
        entry_price = float(position["entry_price"])
        if side == "long":
            pnl = (exit_price - entry_price) * size_to_close
        else:
            pnl = (entry_price - exit_price) * size_to_close

        self.sim_cash += pnl
        self.side_total_profit[side] += float(pnl)
        self.side_fragment_counts[side] += 1

        self.closed_fragments.append(
            {
                "trade_id": int(position["trade_id"]),
                "side": side,
                "symbol": str(state["symbol"]),
                "entry_dt": position["entry_dt"],
                "exit_dt": bt.num2date(state["exec_data"].datetime[0]),
                "entry_price": entry_price,
                "exit_price": float(exit_price),
                "size": float(size_to_close),
                "pnl": float(pnl),
                "reason": reason,
            }
        )

        position["remaining_size"] = float(position["remaining_size"]) - size_to_close
        if force_close or position["remaining_size"] <= 1e-12:
            state["position"] = None
            self.closed_positions += 1
            self.side_closed_positions[side] += 1

    def _manage_long_position(self, state: Dict[str, object]) -> None:
        position = state["position"]
        if not position:
            return

        bar_high = float(state["exec_data"].high[0])
        bar_low = float(state["exec_data"].low[0])
        stop_price = float(position["stop_price"])
        tp1_price = float(position["tp1_price"])
        tp2_price = float(position["tp2_price"])
        remaining_size = float(position["remaining_size"])

        if bar_low <= stop_price:
            self._close_fragment(state, remaining_size, stop_price, reason="stop_loss")
            return

        if (not position["tp1_done"]) and bar_high >= tp2_price:
            half_size = remaining_size * 0.5
            self._close_fragment(state, half_size, tp1_price, reason="tp1_scale_out")
            if state["position"] is not None:
                state["position"]["tp1_done"] = True
                state["position"]["stop_price"] = float(state["position"]["entry_price"])
                self._close_fragment(state, float(state["position"]["remaining_size"]), tp2_price, reason="tp2_final")
            return

        if (not position["tp1_done"]) and bar_high >= tp1_price:
            half_size = remaining_size * 0.5
            self._close_fragment(state, half_size, tp1_price, reason="tp1_scale_out")
            if state["position"] is not None:
                state["position"]["tp1_done"] = True
                state["position"]["stop_price"] = float(state["position"]["entry_price"])
            return

        position = state["position"]
        if position and position["tp1_done"] and bar_high >= tp2_price:
            self._close_fragment(state, float(position["remaining_size"]), tp2_price, reason="tp2_final")

    def _manage_short_position(self, state: Dict[str, object]) -> None:
        position = state["position"]
        if not position:
            return

        bar_high = float(state["exec_data"].high[0])
        bar_low = float(state["exec_data"].low[0])
        stop_price = float(position["stop_price"])
        tp1_price = float(position["tp1_price"])
        tp2_price = float(position["tp2_price"])
        remaining_size = float(position["remaining_size"])

        if bar_high >= stop_price:
            self._close_fragment(state, remaining_size, stop_price, reason="stop_loss")
            return

        if (not position["tp1_done"]) and bar_low <= tp2_price:
            half_size = remaining_size * 0.5
            self._close_fragment(state, half_size, tp1_price, reason="tp1_scale_out")
            if state["position"] is not None:
                state["position"]["tp1_done"] = True
                state["position"]["stop_price"] = float(state["position"]["entry_price"])
                self._close_fragment(state, float(state["position"]["remaining_size"]), tp2_price, reason="tp2_final")
            return

        if (not position["tp1_done"]) and bar_low <= tp1_price:
            half_size = remaining_size * 0.5
            self._close_fragment(state, half_size, tp1_price, reason="tp1_scale_out")
            if state["position"] is not None:
                state["position"]["tp1_done"] = True
                state["position"]["stop_price"] = float(state["position"]["entry_price"])
            return

        position = state["position"]
        if position and position["tp1_done"] and bar_low <= tp2_price:
            self._close_fragment(state, float(position["remaining_size"]), tp2_price, reason="tp2_final")

    def _manage_open_position(self, state: Dict[str, object]) -> None:
        position = state["position"]
        if not position:
            return
        if str(position["side"]) == "long":
            self._manage_long_position(state)
        else:
            self._manage_short_position(state)

    def next(self) -> None:
        """Advance the full mixed portfolio one Backtrader event at a time."""
        any_exec_advanced = False
        for state in self.asset_states.values():
            exec_len = len(state["exec_data"])
            if exec_len != state["last_exec_len"]:
                state["last_exec_len"] = exec_len
                any_exec_advanced = True
                self._try_open_pending_entry(state)

        if any_exec_advanced:
            self._update_drawdown_state()

            if self.breached and not self.account_locked:
                self.account_locked = True

            if self.account_locked:
                self._force_liquidate_all(reason="account_breach_liquidation")

            for state in self.asset_states.values():
                if state["position"] is None:
                    continue
                self._manage_open_position(state)

        for state in self.asset_states.values():
            signal_len = len(state["signal_data"])
            if signal_len != state["last_signal_len"]:
                state["last_signal_len"] = signal_len
                self._schedule_entry_if_needed(state)

    def stop(self) -> None:
        """Force-close any leftover positions at the final close."""
        for state in self.asset_states.values():
            if state["position"] is None:
                continue
            exit_price = float(state["exec_data"].close[0])
            self._close_fragment(state, float(state["position"]["remaining_size"]), exit_price, reason="final_bar_close", force_close=True)

    def build_metrics(self) -> Dict[str, float]:
        """Return one normalized dictionary of final mixed-portfolio metrics."""
        total_trades = len(self.closed_fragments)
        total_profit = float(sum(fragment["pnl"] for fragment in self.closed_fragments))
        winning_trades = int(sum(1 for fragment in self.closed_fragments if float(fragment["pnl"]) > 0.0))
        win_rate = (winning_trades / total_trades) if total_trades > 0 else 0.0
        expectancy = (total_profit / total_trades) if total_trades > 0 else 0.0
        total_return = total_profit / INITIAL_BALANCE if INITIAL_BALANCE > 0 else 0.0

        positive_fragments = [float(fragment["pnl"]) for fragment in self.closed_fragments if float(fragment["pnl"]) > 0.0]
        if total_profit > 0.0 and positive_fragments:
            consistency_score = (max(positive_fragments) / total_profit) * 100.0
        else:
            consistency_score = 999.0

        overall_survival = bool((not self.breached) and (consistency_score <= CONSISTENCY_LIMIT_PCT) and (total_profit > 0.0))
        return {
            "total_trades": int(total_trades),
            "closed_positions": int(self.closed_positions),
            "win_rate": float(win_rate),
            "expectancy": float(expectancy),
            "total_profit": float(total_profit),
            "total_return": float(total_return),
            "ending_equity": float(self._portfolio_equity(mark="close")),
            "peak_equity": float(self.peak_equity),
            "max_dd_dollars": float(self.max_drawdown_dollars),
            "max_dd_pct": float(self.max_drawdown_pct * 100.0),
            "breached": bool(self.breached),
            "consistency_score": float(consistency_score),
            "overall_survival": bool(overall_survival),
            "max_concurrent_observed": int(self.max_positions_seen),
            "signal_conflicts": int(self.signal_conflicts),
            "long_total_trades": int(self.side_fragment_counts["long"]),
            "short_total_trades": int(self.side_fragment_counts["short"]),
            "long_closed_positions": int(self.side_closed_positions["long"]),
            "short_closed_positions": int(self.side_closed_positions["short"]),
            "long_total_profit": float(self.side_total_profit["long"]),
            "short_total_profit": float(self.side_total_profit["short"]),
        }


class MavenComplianceAnalyzer(bt.Analyzer):
    """Passive analyzer that snapshots the mixed-portfolio compliance state."""

    def start(self) -> None:
        self.peak_equity = INITIAL_BALANCE
        self.max_drawdown_dollars = 0.0
        self.max_drawdown_pct = 0.0
        self.breached = False

    def next(self) -> None:
        self.peak_equity = max(self.peak_equity, float(self.strategy.peak_equity))
        self.max_drawdown_dollars = max(self.max_drawdown_dollars, float(self.strategy.max_drawdown_dollars))
        self.max_drawdown_pct = max(self.max_drawdown_pct, float(self.strategy.max_drawdown_pct * 100.0))
        self.breached = self.breached or bool(self.strategy.breached)

    def get_analysis(self) -> Dict[str, object]:
        metrics = self.strategy.build_metrics()
        metrics.update(
            {
                "peak_equity": float(self.peak_equity),
                "max_dd_dollars": float(self.max_drawdown_dollars),
                "max_dd_pct": float(self.max_drawdown_pct),
                "breached": bool(self.breached),
            }
        )
        return metrics


def load_candidates(path: str) -> List[CombinedCandidateConfig]:
    """Read the combined-candidate CSV and convert each row into a typed object."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Candidate file not found: {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError("Candidate file is empty.")
    return [CombinedCandidateConfig.from_row(row) for _, row in df.iterrows()]


def run_one_candidate(candidate: CombinedCandidateConfig, catalog: MarketDataCatalog, prefer_intraday: bool) -> Dict[str, object]:
    """Run one combined pair portfolio in its own Cerebro instance."""
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(INITIAL_BALANCE)

    feed_map = catalog.add_candidate_feeds(cerebro, prefer_intraday=prefer_intraday)
    data_modes = sorted(set(mapping["data_mode"] for mapping in feed_map.values()))

    cerebro.addstrategy(MavenCombinedCandidateStrategy, candidate=candidate, feed_map=feed_map)
    cerebro.addanalyzer(MavenComplianceAnalyzer, _name="maven")

    results = cerebro.run(runonce=False, stdstats=False, quicknotify=False)
    strategy = results[0]
    analysis = strategy.analyzers.maven.get_analysis()

    row = {
        "rank": int(candidate.source_rank),
        "param_id": candidate.param_id,
        "pair_family": candidate.pair_family,
        "long_param_id": candidate.long_candidate.param_id,
        "long_source_symbol": candidate.long_candidate.source_symbol,
        "long_sma": int(candidate.long_candidate.sma),
        "long_ema": int(candidate.long_candidate.ema),
        "long_fib_floor": float(candidate.long_candidate.fib_floor),
        "long_fib_band": float(candidate.long_candidate.fib_band),
        "long_rw": float(candidate.long_candidate.rw),
        "long_eb": float(candidate.long_candidate.eb),
        "long_rw_lookback": int(candidate.long_candidate.rw_lookback),
        "long_confirm_enabled": bool(candidate.long_candidate.confirm_enabled),
        "long_confirm_mode": str(candidate.long_candidate.confirm_mode),
        "long_confirm_ema_period": int(candidate.long_candidate.confirm_ema_period),
        "long_confirm_min_distance": float(candidate.long_candidate.confirm_min_distance),
        "short_param_id": candidate.short_candidate.param_id,
        "short_source_symbol": candidate.short_candidate.source_symbol,
        "short_sma": int(candidate.short_candidate.sma),
        "short_ema": int(candidate.short_candidate.ema),
        "short_fib_floor": float(candidate.short_candidate.fib_floor),
        "short_fib_band": float(candidate.short_candidate.fib_band),
        "short_rw": float(candidate.short_candidate.rw),
        "short_eb": float(candidate.short_candidate.eb),
        "short_rw_lookback": int(candidate.short_candidate.rw_lookback),
        "short_confirm_enabled": bool(candidate.short_candidate.confirm_enabled),
        "short_confirm_mode": str(candidate.short_candidate.confirm_mode),
        "short_confirm_ema_period": int(candidate.short_candidate.confirm_ema_period),
        "short_confirm_min_distance": float(candidate.short_candidate.confirm_min_distance),
        "data_mode_used": ", ".join(data_modes),
    }
    row.update(analysis)
    return row


def write_summary(
    summary_path: str,
    results_df: pd.DataFrame,
    catalog: MarketDataCatalog,
    candidates_path: str,
) -> None:
    """Write the markdown summary for the mixed long + short run."""

    survivors = results_df.loc[results_df["overall_survival"]].copy()
    top_survivors = survivors.head(10)
    mode_info = catalog.describe_modes()

    def _markdown_table(frame: pd.DataFrame) -> str:
        headers = list(frame.columns)
        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
        ]
        for _, row in frame.iterrows():
            values = [str(row[column]) for column in headers]
            lines.append("| " + " | ".join(values) + " |")
        return "\n".join(lines)

    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write("# Backtrader combined validation summary\n\n")
        handle.write(f"- **source_candidates_file**: {candidates_path}\n")
        handle.write(f"- **pair_portfolios_evaluated**: {len(results_df)}\n")
        handle.write(f"- **survivors**: {len(survivors)}\n")
        handle.write(f"- **breached_accounts**: {int(results_df['breached'].sum())}\n")
        handle.write(f"- **median_max_dd_pct**: {results_df['max_dd_pct'].median():.2f}\n")
        handle.write(f"- **median_consistency_score**: {results_df['consistency_score'].median():.2f}\n")
        handle.write(f"- **best_expectancy**: {results_df['expectancy'].max():.2f}\n")
        handle.write(f"- **best_total_return_pct**: {results_df['total_return'].max() * 100.0:.2f}\n")
        handle.write(f"- **median_signal_conflicts**: {results_df['signal_conflicts'].median():.2f}\n")
        handle.write("\n## Data Coverage Notes\n\n")
        handle.write(f"- **4H execution + Daily signals available**: {mode_info['intraday_symbols']} symbols\n")
        handle.write(f"- **Daily fallback symbols**: {mode_info['daily_fallback_symbols']} symbols\n")
        handle.write("- Mixed-timeframe validation is therefore partially intraday-aware, not fully intraday for the whole watchlist.\n")

        handle.write("\n## Top 10 Surviving Pair Portfolios\n\n")
        if top_survivors.empty:
            handle.write("No combined pair portfolios survived the current compliance filters.\n")
        else:
            cols = [
                "rank",
                "long_param_id",
                "short_param_id",
                "total_trades",
                "win_rate",
                "expectancy",
                "max_dd_pct",
                "consistency_score",
                "signal_conflicts",
                "overall_survival",
            ]
            handle.write(_markdown_table(top_survivors[cols]))
            handle.write("\n")


def evaluate_candidates(
    candidates: List[CombinedCandidateConfig],
    catalog: MarketDataCatalog,
    output_csv: str,
    summary_md: str,
    candidates_path: str,
    prefer_intraday: bool,
    flush_every: int,
) -> pd.DataFrame:
    """Evaluate every combined pair candidate and write incremental progress."""

    partial_rows: List[Dict[str, object]] = []
    all_rows: List[Dict[str, object]] = []

    if os.path.exists(output_csv):
        os.remove(output_csv)

    progress = tqdm(candidates, desc="Backtrader combined validation", unit="pair")
    for index, candidate in enumerate(progress, start=1):
        try:
            row = run_one_candidate(candidate, catalog=catalog, prefer_intraday=prefer_intraday)
            all_rows.append(row)
            partial_rows.append(row)
            progress.set_postfix(
                rank=candidate.source_rank,
                breached=int(bool(row["breached"])),
                survive=int(bool(row["overall_survival"])),
            )
        except Exception as exc:
            error_row = {
                "rank": int(candidate.source_rank),
                "param_id": candidate.param_id,
                "pair_family": candidate.pair_family,
                "long_param_id": candidate.long_candidate.param_id,
                "short_param_id": candidate.short_candidate.param_id,
                "long_source_symbol": candidate.long_candidate.source_symbol,
                "short_source_symbol": candidate.short_candidate.source_symbol,
                "data_mode_used": "error",
                "total_trades": 0,
                "closed_positions": 0,
                "win_rate": 0.0,
                "expectancy": 0.0,
                "total_profit": 0.0,
                "total_return": 0.0,
                "ending_equity": INITIAL_BALANCE,
                "peak_equity": INITIAL_BALANCE,
                "max_dd_dollars": 0.0,
                "max_dd_pct": 0.0,
                "breached": True,
                "consistency_score": 999.0,
                "overall_survival": False,
                "max_concurrent_observed": 0,
                "signal_conflicts": 0,
                "long_total_trades": 0,
                "short_total_trades": 0,
                "long_closed_positions": 0,
                "short_closed_positions": 0,
                "long_total_profit": 0.0,
                "short_total_profit": 0.0,
                "error": str(exc),
            }
            all_rows.append(error_row)
            partial_rows.append(error_row)

        if index % flush_every == 0 or index == len(candidates):
            partial_df = pd.DataFrame(partial_rows)
            partial_df.to_csv(output_csv, mode="a", header=not os.path.exists(output_csv), index=False)
            partial_rows.clear()
            gc.collect()

    results_df = pd.DataFrame(all_rows)
    results_df = results_df.sort_values(
        by=["overall_survival", "breached", "consistency_score", "max_dd_pct", "expectancy", "total_return"],
        ascending=[False, True, True, True, False, False],
    ).reset_index(drop=True)
    results_df.to_csv(output_csv, index=False)

    write_summary(
        summary_path=summary_md,
        results_df=results_df,
        catalog=catalog,
        candidates_path=candidates_path,
    )
    return results_df


def parse_args() -> argparse.Namespace:
    """Define the CLI surface for the combined portfolio phase."""
    parser = argparse.ArgumentParser(description="Chronological Backtrader validation for the combined long + short portfolio study.")
    parser.add_argument("--candidates", default=DEFAULT_CANDIDATES_PATH, help="Path to the combined-candidate CSV.")
    parser.add_argument("--daily-data", default=DEFAULT_DAILY_PATH, help="Path to the daily parquet file.")
    parser.add_argument(
        "--intraday-data",
        default=DEFAULT_INTRADAY_PATH,
        help="Path to the 4H parquet file used when intraday execution is available.",
    )
    parser.add_argument(
        "--output-prefix",
        default=DEFAULT_OUTPUT_PREFIX,
        help="Prefix for output files. Example: results/backtrader_combined",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional cap for smoke tests.")
    parser.add_argument("--start-rank", type=int, default=None, help="Optional inclusive candidate-rank lower bound.")
    parser.add_argument("--end-rank", type=int, default=None, help="Optional inclusive candidate-rank upper bound.")
    parser.add_argument(
        "--no-intraday",
        action="store_true",
        help="Force Daily-only validation even if 4H data exists.",
    )
    parser.add_argument(
        "--flush-every",
        type=int,
        default=5,
        help="Write partial CSV progress every N pair portfolios.",
    )
    return parser.parse_args()


def select_candidates(candidates: List[CombinedCandidateConfig], args: argparse.Namespace) -> List[CombinedCandidateConfig]:
    """Apply optional rank filters and smoke-test limits."""
    selected = candidates
    if args.start_rank is not None:
        selected = [candidate for candidate in selected if candidate.source_rank >= args.start_rank]
    if args.end_rank is not None:
        selected = [candidate for candidate in selected if candidate.source_rank <= args.end_rank]
    if args.limit is not None:
        selected = selected[: args.limit]

    if not selected:
        raise ValueError("No candidates matched the requested filters.")
    return selected


def main() -> None:
    """Main entry point used by `python scripts/backtrader_evaluate_combined.py`."""
    args = parse_args()

    candidates = load_candidates(args.candidates)
    candidates = select_candidates(candidates, args)
    catalog = MarketDataCatalog(daily_path=args.daily_data, intraday_path=args.intraday_data)

    output_csv = f"{args.output_prefix}_results.csv"
    summary_md = f"{args.output_prefix}_summary.md"

    results_df = evaluate_candidates(
        candidates=candidates,
        catalog=catalog,
        output_csv=output_csv,
        summary_md=summary_md,
        candidates_path=args.candidates,
        prefer_intraday=not args.no_intraday,
        flush_every=max(1, int(args.flush_every)),
    )

    survivors = int(results_df["overall_survival"].sum())
    print(f"Validation complete. Results: {output_csv}")
    print(f"Summary: {summary_md}")
    print(f"Pair portfolios evaluated: {len(results_df)}")
    print(f"Survivors: {survivors}")


if __name__ == "__main__":
    main()
