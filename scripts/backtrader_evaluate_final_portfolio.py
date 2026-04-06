"""
Chronological Backtrader validation for the exact final TRADE_ORACLE deployment portfolio.

This evaluator does not rank alternatives. It trades the final 5 shortlisted
combined pairs together inside one shared Maven account so we can inspect the
portfolio exactly as it would be run live on one funded account.
"""

from __future__ import annotations

import argparse
import math
import os
from typing import Dict, List, Optional, Tuple

import backtrader as bt
import pandas as pd

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
    WATCHLIST,
)
from backtrader_evaluate_combined import (
    ATR_PERIOD,
    CONSISTENCY_LIMIT_PCT,
    FIB_LOOKBACK,
    CombinedCandidateConfig,
    SideCandidateConfig,
)


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

DEFAULT_FINAL_SHORTLIST = os.path.join(RESULTS_DIR, "backtrader_combined_final_shortlist.csv")
DEFAULT_SURVIVOR_RANKING = os.path.join(RESULTS_DIR, "backtrader_combined_survivor_ranking.csv")
DEFAULT_OUTPUT_PREFIX = os.path.join(RESULTS_DIR, "backtrader_final_portfolio")


def load_csv(path: str) -> pd.DataFrame:
    """Read a CSV and fail loudly if it is missing or empty."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required file not found: {path}")
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f"Required file is empty: {path}")
    return frame


def resolve_final_pairs(
    shortlist_path: str,
    ranking_path: str,
    top_n: int,
) -> Tuple[List[CombinedCandidateConfig], pd.DataFrame]:
    """Resolve the compact final shortlist into full combined-candidate blocks."""
    shortlist_df = load_csv(shortlist_path).copy()
    ranking_df = load_csv(ranking_path).copy()

    shortlist_df = shortlist_df.sort_values("shortlist_priority").head(max(1, int(top_n))).reset_index(drop=True)
    ranking_lookup = {str(row["param_id"]): row for _, row in ranking_df.iterrows()}

    resolved_rows: List[pd.Series] = []
    resolved_candidates: List[CombinedCandidateConfig] = []
    for _, shortlist_row in shortlist_df.iterrows():
        param_id = str(shortlist_row["param_id"])
        if param_id not in ranking_lookup:
            raise KeyError(f"Final shortlist param_id not found in combined survivor ranking: {param_id}")

        ranking_row = ranking_lookup[param_id].copy()
        ranking_row["shortlist_priority"] = int(shortlist_row["shortlist_priority"])
        ranking_row["shortlist_role"] = str(shortlist_row.get("shortlist_role", "unspecified"))
        ranking_row["shortlist_rationale"] = str(shortlist_row.get("shortlist_rationale", ""))
        resolved_rows.append(ranking_row)
        resolved_candidates.append(CombinedCandidateConfig.from_row(ranking_row))

    resolved_df = pd.DataFrame(resolved_rows).reset_index(drop=True)
    return resolved_candidates, resolved_df


class MavenFinalPortfolioStrategy(bt.Strategy):
    """Trade the final 5 shortlisted combined pairs under one shared Maven account."""

    params = (
        ("final_pairs", None),
        ("pair_rows", None),
        ("feed_map", None),
    )

    def __init__(self) -> None:
        self.final_pairs: List[CombinedCandidateConfig] = list(self.p.final_pairs or [])
        self.pair_rows: List[Dict[str, object]] = list(self.p.pair_rows or [])
        self.feed_map: Dict[str, Dict[str, str]] = self.p.feed_map

        self.pair_lookup = {
            str(row["param_id"]): {
                "shortlist_priority": int(row["shortlist_priority"]),
                "shortlist_role": str(row.get("shortlist_role", "unspecified")),
                "expectancy": float(row["expectancy"]),
                "composite_score": float(row["composite_score"]),
                "long_param_id": str(row["long_param_id"]),
                "short_param_id": str(row["short_param_id"]),
            }
            for row in self.pair_rows
        }

        self.sim_cash = INITIAL_BALANCE
        self.peak_equity = INITIAL_BALANCE
        self.max_drawdown_dollars = 0.0
        self.max_drawdown_pct = 0.0
        self.breached = False
        self.account_locked = False
        self.max_positions_seen = 0

        self.closed_fragments: List[Dict[str, object]] = []
        self.closed_positions_log: List[Dict[str, object]] = []
        self.equity_timeline: List[Dict[str, object]] = []
        self.trade_counter = 0
        self.closed_positions = 0
        self.signal_conflicts = 0
        self.internal_pair_conflicts = 0

        self.side_fragment_counts: Dict[str, int] = {"long": 0, "short": 0}
        self.side_closed_positions: Dict[str, int] = {"long": 0, "short": 0}
        self.side_total_profit: Dict[str, float] = {"long": 0.0, "short": 0.0}

        self.asset_states: Dict[str, Dict[str, object]] = {}
        for symbol, mapping in self.feed_map.items():
            signal_data = self.getdatabyname(mapping["signal_name"])
            exec_data = self.getdatabyname(mapping["exec_name"])
            state: Dict[str, object] = {
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
                "pair_blocks": {},
            }

            for pair in self.final_pairs:
                pair_meta = self.pair_lookup[pair.param_id]
                state["pair_blocks"][pair.param_id] = {
                    "candidate": pair,
                    "pair_meta": pair_meta,
                    "long_sma": bt.indicators.SimpleMovingAverage(signal_data.close, period=pair.long_candidate.sma),
                    "long_ema": bt.indicators.ExponentialMovingAverage(signal_data.close, period=pair.long_candidate.ema),
                    "short_sma": bt.indicators.SimpleMovingAverage(signal_data.close, period=pair.short_candidate.sma),
                    "short_ema": bt.indicators.ExponentialMovingAverage(signal_data.close, period=pair.short_candidate.ema),
                    "long_confirm_ema": (
                        bt.indicators.ExponentialMovingAverage(exec_data.close, period=pair.long_candidate.confirm_ema_period)
                        if pair.long_candidate.confirm_enabled
                        else None
                    ),
                    "short_confirm_ema": (
                        bt.indicators.ExponentialMovingAverage(exec_data.close, period=pair.short_candidate.confirm_ema_period)
                        if pair.short_candidate.confirm_enabled
                        else None
                    ),
                }

            self.asset_states[symbol] = state

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

    def _confirmation_is_valid(self, state: Dict[str, object], cfg: SideCandidateConfig, pair_block: Dict[str, object]) -> bool:
        if not cfg.confirm_enabled:
            return True

        confirm_key = "long_confirm_ema" if cfg.side == "long" else "short_confirm_ema"
        confirm_ema = pair_block[confirm_key]
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

    def _signal_is_valid(
        self,
        state: Dict[str, object],
        cfg: SideCandidateConfig,
        pair_block: Dict[str, object],
    ) -> Optional[Dict[str, float]]:
        if not self._signal_is_ready(state, cfg):
            return None

        signal_data = state["signal_data"]
        close = float(signal_data.close[0])
        sma_line = pair_block["long_sma"] if cfg.side == "long" else pair_block["short_sma"]
        ema_line = pair_block["long_ema"] if cfg.side == "long" else pair_block["short_ema"]
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

        if not is_valid or not self._confirmation_is_valid(state, cfg, pair_block):
            return None

        payload.update({"side": cfg.side, "atr": atr, "signal_close": close})
        return payload

    def _collect_symbol_signal(self, state: Dict[str, object]) -> Optional[Dict[str, object]]:
        long_candidates: List[Dict[str, object]] = []
        short_candidates: List[Dict[str, object]] = []

        for pair_id, pair_block in state["pair_blocks"].items():
            pair: CombinedCandidateConfig = pair_block["candidate"]
            pair_meta = pair_block["pair_meta"]

            long_payload = self._signal_is_valid(state, pair.long_candidate, pair_block)
            short_payload = self._signal_is_valid(state, pair.short_candidate, pair_block)

            if long_payload and short_payload:
                self.internal_pair_conflicts += 1
                continue

            if long_payload:
                long_candidates.append(
                    {
                        "pair_id": pair_id,
                        "side": "long",
                        "atr": float(long_payload["atr"]),
                        "signal_close": float(long_payload["signal_close"]),
                        "shortlist_priority": int(pair_meta["shortlist_priority"]),
                        "pair_expectancy": float(pair_meta["expectancy"]),
                        "pair_composite_score": float(pair_meta["composite_score"]),
                    }
                )
            elif short_payload:
                short_candidates.append(
                    {
                        "pair_id": pair_id,
                        "side": "short",
                        "atr": float(short_payload["atr"]),
                        "signal_close": float(short_payload["signal_close"]),
                        "shortlist_priority": int(pair_meta["shortlist_priority"]),
                        "pair_expectancy": float(pair_meta["expectancy"]),
                        "pair_composite_score": float(pair_meta["composite_score"]),
                    }
                )

        if long_candidates and short_candidates:
            self.signal_conflicts += 1
            return None

        side_candidates = long_candidates or short_candidates
        if not side_candidates:
            return None

        side_candidates = sorted(
            side_candidates,
            key=lambda row: (
                int(row["shortlist_priority"]),
                -float(row["pair_expectancy"]),
                row["pair_id"],
            ),
        )
        chosen = dict(side_candidates[0])
        chosen["support_pair_ids"] = [str(row["pair_id"]) for row in side_candidates]
        chosen["support_pair_count"] = len(side_candidates)
        chosen["support_pair_expectancy_mean"] = float(
            sum(float(row["pair_expectancy"]) for row in side_candidates) / len(side_candidates)
        )
        return chosen

    def _schedule_entry_if_needed(self, state: Dict[str, object]) -> None:
        """Schedule at most one next-bar entry for the current symbol."""
        if self.account_locked:
            return
        if state["position"] is not None or state["pending_entry"] is not None:
            return

        selected_signal = self._collect_symbol_signal(state)
        if not selected_signal:
            return

        state["pending_entry"] = {
            "side": str(selected_signal["side"]),
            "atr": float(selected_signal["atr"]),
            "pair_id": str(selected_signal["pair_id"]),
            "support_pair_ids": list(selected_signal["support_pair_ids"]),
            "support_pair_count": int(selected_signal["support_pair_count"]),
            "support_pair_expectancy_mean": float(selected_signal["support_pair_expectancy_mean"]),
            "scheduled_from": bt.num2date(state["signal_data"].datetime[0]),
            "signal_close": float(selected_signal["signal_close"]),
        }

    def _try_open_pending_entry(self, state: Dict[str, object]) -> None:
        """Open one pending entry at the next execution-bar open."""
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
            "initial_stop_distance": stop_distance,
            "initial_atr": atr,
            "source_pair_id": str(pending["pair_id"]),
            "support_pair_ids": list(pending["support_pair_ids"]),
            "support_pair_count": int(pending["support_pair_count"]),
            "support_pair_expectancy_mean": float(pending["support_pair_expectancy_mean"]),
            "realized_pnl": 0.0,
            "fragment_count": 0,
        }

        if side == "long":
            position["stop_price"] = entry_price - stop_distance
            position["tp1_price"] = entry_price + (atr * TP1_ATR_MULTIPLIER)
            position["tp2_price"] = entry_price + (atr * TP2_ATR_MULTIPLIER)
        else:
            position["stop_price"] = entry_price + stop_distance
            position["tp1_price"] = entry_price - (atr * TP1_ATR_MULTIPLIER)
            position["tp2_price"] = entry_price - (atr * TP2_ATR_MULTIPLIER)

        position["initial_stop_price"] = float(position["stop_price"])
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
        """Realize one exit fragment and update the portfolio ledgers."""
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
        position["realized_pnl"] = float(position["realized_pnl"]) + float(pnl)
        position["fragment_count"] = int(position["fragment_count"]) + 1

        self.closed_fragments.append(
            {
                "trade_id": int(position["trade_id"]),
                "source_pair_id": str(position["source_pair_id"]),
                "support_pair_ids": "|".join(position["support_pair_ids"]),
                "support_pair_count": int(position["support_pair_count"]),
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
            exit_dt = bt.num2date(state["exec_data"].datetime[0])
            holding_days = (exit_dt - position["entry_dt"]).total_seconds() / 86400.0
            self.closed_positions_log.append(
                {
                    "trade_id": int(position["trade_id"]),
                    "source_pair_id": str(position["source_pair_id"]),
                    "support_pair_ids": "|".join(position["support_pair_ids"]),
                    "support_pair_count": int(position["support_pair_count"]),
                    "support_pair_expectancy_mean": float(position["support_pair_expectancy_mean"]),
                    "side": side,
                    "symbol": str(state["symbol"]),
                    "entry_dt": position["entry_dt"],
                    "exit_dt": exit_dt,
                    "entry_price": float(position["entry_price"]),
                    "exit_price": float(exit_price),
                    "initial_size": float(position["initial_size"]),
                    "initial_atr": float(position["initial_atr"]),
                    "initial_stop_price": float(position["initial_stop_price"]),
                    "tp1_price": float(position["tp1_price"]),
                    "tp2_price": float(position["tp2_price"]),
                    "realized_pnl": float(position["realized_pnl"]),
                    "fragment_count": int(position["fragment_count"]),
                    "holding_days": float(holding_days),
                    "final_reason": reason,
                    "winning_position": bool(float(position["realized_pnl"]) > 0.0),
                }
            )
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

    def _record_equity_snapshot(self) -> None:
        timestamp = bt.num2date(self.datetime[0])
        self.equity_timeline.append(
            {
                "timestamp": timestamp,
                "equity": float(self._portfolio_equity(mark="close")),
                "cash": float(self.sim_cash),
                "open_positions": int(self._active_positions()),
            }
        )

    def next(self) -> None:
        """Advance the full final deployment portfolio one Backtrader event at a time."""
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

            self._record_equity_snapshot()

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
        self._record_equity_snapshot()

    def build_metrics(self) -> Dict[str, float]:
        """Return the Maven-compliance and PnL metrics for the live-style final portfolio."""
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
            "active_pairs": int(len(self.final_pairs)),
            "watchlist_size": int(len(WATCHLIST)),
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
            "internal_pair_conflicts": int(self.internal_pair_conflicts),
            "long_total_trades": int(self.side_fragment_counts["long"]),
            "short_total_trades": int(self.side_fragment_counts["short"]),
            "long_closed_positions": int(self.side_closed_positions["long"]),
            "short_closed_positions": int(self.side_closed_positions["short"]),
            "long_total_profit": float(self.side_total_profit["long"]),
            "short_total_profit": float(self.side_total_profit["short"]),
        }


def compute_sequence_streak(values: List[bool], target: bool) -> int:
    """Return the longest consecutive streak matching the target boolean."""
    best = 0
    current = 0
    for value in values:
        if value == target:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def safe_float(value: object, default: float = 0.0) -> float:
    """Convert a scalar into float while handling NaN and missing values."""
    try:
        result = float(value)
    except Exception:
        return default
    if math.isnan(result):
        return default
    return result


def compute_additional_metrics(
    base_metrics: Dict[str, object],
    positions_df: pd.DataFrame,
    equity_df: pd.DataFrame,
) -> Tuple[Dict[str, object], pd.DataFrame]:
    """Build position, monthly-return, and risk-adjusted metrics from the raw ledgers."""
    metrics = dict(base_metrics)

    monthly_returns_df = pd.DataFrame(columns=["month", "monthly_return_pct", "month_end_equity"])
    if positions_df.empty:
        metrics.update(
            {
                "winning_positions": 0,
                "losing_positions": 0,
                "breakeven_positions": 0,
                "position_win_rate": 0.0,
                "avg_position_pnl": 0.0,
                "avg_winner_pnl": 0.0,
                "avg_loser_pnl": 0.0,
                "profit_factor": 0.0,
                "avg_holding_days": 0.0,
                "median_holding_days": 0.0,
                "best_position_pnl": 0.0,
                "worst_position_pnl": 0.0,
                "max_consecutive_position_wins": 0,
                "max_consecutive_position_losses": 0,
                "avg_support_pair_count": 0.0,
                "cagr": 0.0,
                "daily_sharpe": 0.0,
                "daily_sortino": 0.0,
                "calmar": 0.0,
                "months_traded": 0,
                "profitable_months": 0,
                "losing_months": 0,
                "monthly_win_rate": 0.0,
                "best_month_return_pct": 0.0,
                "worst_month_return_pct": 0.0,
            }
        )
        return metrics, monthly_returns_df

    ordered_positions = positions_df.copy()
    ordered_positions["entry_dt"] = pd.to_datetime(ordered_positions["entry_dt"])
    ordered_positions["exit_dt"] = pd.to_datetime(ordered_positions["exit_dt"])
    ordered_positions = ordered_positions.sort_values(["exit_dt", "trade_id"]).reset_index(drop=True)

    winning_positions = int((ordered_positions["realized_pnl"] > 0.0).sum())
    losing_positions = int((ordered_positions["realized_pnl"] < 0.0).sum())
    breakeven_positions = int((ordered_positions["realized_pnl"] == 0.0).sum())
    total_positions = len(ordered_positions)
    position_win_rate = (winning_positions / total_positions) if total_positions > 0 else 0.0

    winners = ordered_positions.loc[ordered_positions["realized_pnl"] > 0.0, "realized_pnl"]
    losers = ordered_positions.loc[ordered_positions["realized_pnl"] < 0.0, "realized_pnl"]
    gross_profit = float(winners.sum()) if not winners.empty else 0.0
    gross_loss_abs = abs(float(losers.sum())) if not losers.empty else 0.0
    profit_factor = (gross_profit / gross_loss_abs) if gross_loss_abs > 0.0 else (float("inf") if gross_profit > 0.0 else 0.0)

    win_flags = [bool(value) for value in (ordered_positions["realized_pnl"] > 0.0).tolist()]
    loss_flags = [bool(value) for value in (ordered_positions["realized_pnl"] < 0.0).tolist()]

    metrics.update(
        {
            "winning_positions": winning_positions,
            "losing_positions": losing_positions,
            "breakeven_positions": breakeven_positions,
            "position_win_rate": float(position_win_rate),
            "avg_position_pnl": float(ordered_positions["realized_pnl"].mean()),
            "avg_winner_pnl": float(winners.mean()) if not winners.empty else 0.0,
            "avg_loser_pnl": float(losers.mean()) if not losers.empty else 0.0,
            "profit_factor": float(profit_factor) if math.isfinite(profit_factor) else float("inf"),
            "avg_holding_days": float(ordered_positions["holding_days"].mean()),
            "median_holding_days": float(ordered_positions["holding_days"].median()),
            "best_position_pnl": float(ordered_positions["realized_pnl"].max()),
            "worst_position_pnl": float(ordered_positions["realized_pnl"].min()),
            "max_consecutive_position_wins": int(compute_sequence_streak(win_flags, True)),
            "max_consecutive_position_losses": int(compute_sequence_streak(loss_flags, True)),
            "avg_support_pair_count": float(ordered_positions["support_pair_count"].mean()),
        }
    )

    if equity_df.empty:
        metrics.update(
            {
                "cagr": 0.0,
                "daily_sharpe": 0.0,
                "daily_sortino": 0.0,
                "calmar": 0.0,
                "months_traded": 0,
                "profitable_months": 0,
                "losing_months": 0,
                "monthly_win_rate": 0.0,
                "best_month_return_pct": 0.0,
                "worst_month_return_pct": 0.0,
            }
        )
        return metrics, monthly_returns_df

    equity_series = equity_df.copy()
    equity_series["timestamp"] = pd.to_datetime(equity_series["timestamp"])
    equity_series = equity_series.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last").set_index("timestamp")

    daily_equity = equity_series["equity"].resample("D").last().ffill()
    daily_returns = daily_equity.pct_change().dropna()
    downside_returns = daily_returns.loc[daily_returns < 0.0]

    days_elapsed = max(1, (daily_equity.index[-1] - daily_equity.index[0]).days)
    ending_equity = safe_float(daily_equity.iloc[-1], default=INITIAL_BALANCE)
    cagr = (ending_equity / INITIAL_BALANCE) ** (365.0 / days_elapsed) - 1.0 if ending_equity > 0.0 else -1.0

    if not daily_returns.empty and safe_float(daily_returns.std(), 0.0) > 0.0:
        daily_sharpe = float((daily_returns.mean() / daily_returns.std()) * math.sqrt(365.0))
    else:
        daily_sharpe = 0.0

    if not downside_returns.empty and safe_float(downside_returns.std(), 0.0) > 0.0:
        daily_sortino = float((daily_returns.mean() / downside_returns.std()) * math.sqrt(365.0))
    else:
        daily_sortino = 0.0

    max_dd_pct_decimal = safe_float(metrics["max_dd_pct"], 0.0) / 100.0
    calmar = (cagr / max_dd_pct_decimal) if max_dd_pct_decimal > 0.0 else 0.0

    monthly_equity = daily_equity.resample("ME").last()
    monthly_returns = monthly_equity.pct_change().dropna()
    monthly_returns_df = pd.DataFrame(
        {
            "month": monthly_returns.index.strftime("%Y-%m"),
            "monthly_return_pct": monthly_returns.values * 100.0,
            "month_end_equity": monthly_equity.loc[monthly_returns.index].values,
        }
    )

    profitable_months = int((monthly_returns > 0.0).sum()) if not monthly_returns.empty else 0
    losing_months = int((monthly_returns < 0.0).sum()) if not monthly_returns.empty else 0
    months_traded = int(len(monthly_returns))
    monthly_win_rate = (profitable_months / months_traded) if months_traded > 0 else 0.0

    metrics.update(
        {
            "cagr": float(cagr),
            "daily_sharpe": float(daily_sharpe),
            "daily_sortino": float(daily_sortino),
            "calmar": float(calmar),
            "months_traded": months_traded,
            "profitable_months": profitable_months,
            "losing_months": losing_months,
            "monthly_win_rate": float(monthly_win_rate),
            "best_month_return_pct": float((monthly_returns.max() * 100.0) if not monthly_returns.empty else 0.0),
            "worst_month_return_pct": float((monthly_returns.min() * 100.0) if not monthly_returns.empty else 0.0),
        }
    )
    return metrics, monthly_returns_df


def build_pair_stats(positions_df: pd.DataFrame, pair_rows_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate realized performance by chosen source pair."""
    if positions_df.empty:
        return pd.DataFrame(
            columns=[
                "source_pair_id",
                "positions",
                "winning_positions",
                "position_win_rate",
                "total_profit",
                "avg_position_pnl",
                "avg_support_pair_count",
                "shortlist_priority",
                "shortlist_role",
            ]
        )

    grouped = (
        positions_df.groupby("source_pair_id", dropna=False)
        .agg(
            positions=("trade_id", "count"),
            winning_positions=("winning_position", "sum"),
            total_profit=("realized_pnl", "sum"),
            avg_position_pnl=("realized_pnl", "mean"),
            avg_support_pair_count=("support_pair_count", "mean"),
        )
        .reset_index()
    )
    grouped["position_win_rate"] = grouped["winning_positions"] / grouped["positions"]

    merge_cols = ["param_id", "shortlist_priority", "shortlist_role", "long_param_id", "short_param_id"]
    merged = grouped.merge(pair_rows_df[merge_cols], left_on="source_pair_id", right_on="param_id", how="left").drop(columns=["param_id"])
    merged = merged.sort_values(["total_profit", "positions"], ascending=[False, False]).reset_index(drop=True)
    return merged


def build_symbol_stats(positions_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate realized performance by traded symbol."""
    if positions_df.empty:
        return pd.DataFrame(columns=["symbol", "positions", "winning_positions", "position_win_rate", "total_profit", "avg_position_pnl"])

    grouped = (
        positions_df.groupby("symbol", dropna=False)
        .agg(
            positions=("trade_id", "count"),
            winning_positions=("winning_position", "sum"),
            total_profit=("realized_pnl", "sum"),
            avg_position_pnl=("realized_pnl", "mean"),
        )
        .reset_index()
    )
    grouped["position_win_rate"] = grouped["winning_positions"] / grouped["positions"]
    return grouped.sort_values(["total_profit", "positions"], ascending=[False, False]).reset_index(drop=True)


def markdown_table(frame: pd.DataFrame) -> str:
    """Render a compact markdown table."""
    if frame.empty:
        return "No rows.\n"

    table = frame.copy()
    for column in table.columns:
        if pd.api.types.is_float_dtype(table[column]):
            table[column] = table[column].map(lambda value: f"{float(value):.4f}")

    headers = list(table.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in table.iterrows():
        lines.append("| " + " | ".join(str(row[column]) for column in headers) + " |")
    return "\n".join(lines) + "\n"


def write_summary(
    summary_path: str,
    metrics: Dict[str, object],
    pair_rows_df: pd.DataFrame,
    pair_stats_df: pd.DataFrame,
    symbol_stats_df: pd.DataFrame,
    monthly_returns_df: pd.DataFrame,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    catalog: MarketDataCatalog,
    assumptions: List[str],
) -> None:
    """Write the high-level markdown summary for the final deployment portfolio."""
    mode_info = catalog.describe_modes()

    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write("# Backtrader final portfolio summary\n\n")
        handle.write(f"- **raw_data_start**: {start_ts.strftime('%Y-%m-%d %H:%M')}\n")
        handle.write(f"- **raw_data_end**: {end_ts.strftime('%Y-%m-%d %H:%M')}\n")
        handle.write(f"- **effective_backtest_start**: {metrics['backtest_start']}\n")
        handle.write(f"- **effective_backtest_end**: {metrics['backtest_end']}\n")
        handle.write(f"- **final_pairs_active**: {int(metrics['active_pairs'])}\n")
        handle.write(f"- **watchlist_size**: {int(metrics['watchlist_size'])}\n")
        handle.write(f"- **4H execution + Daily signals available**: {mode_info['intraday_symbols']} symbols\n")
        handle.write(f"- **Daily fallback symbols**: {mode_info['daily_fallback_symbols']} symbols\n")
        handle.write(f"- **ending_equity**: {float(metrics['ending_equity']):.2f}\n")
        handle.write(f"- **total_profit**: {float(metrics['total_profit']):.2f}\n")
        handle.write(f"- **total_return_pct**: {float(metrics['total_return']) * 100.0:.2f}\n")
        handle.write(f"- **max_dd_pct**: {float(metrics['max_dd_pct']):.2f}\n")
        handle.write(f"- **consistency_score**: {float(metrics['consistency_score']):.2f}\n")
        handle.write(f"- **overall_survival**: {bool(metrics['overall_survival'])}\n")
        handle.write(f"- **breached**: {bool(metrics['breached'])}\n")

        handle.write("\n## Execution Assumptions\n\n")
        for assumption in assumptions:
            handle.write(f"- {assumption}\n")

        handle.write("\n## Portfolio Metrics\n\n")
        metrics_frame = pd.DataFrame(
            [
                {
                    "closed_positions": int(metrics["closed_positions"]),
                    "total_fragments": int(metrics["total_trades"]),
                    "fragment_win_rate": float(metrics["win_rate"]),
                    "position_win_rate": float(metrics["position_win_rate"]),
                    "expectancy_per_fragment": float(metrics["expectancy"]),
                    "profit_factor": float(metrics["profit_factor"]) if math.isfinite(float(metrics["profit_factor"])) else "inf",
                    "cagr": float(metrics["cagr"]),
                    "daily_sharpe": float(metrics["daily_sharpe"]),
                    "daily_sortino": float(metrics["daily_sortino"]),
                    "calmar": float(metrics["calmar"]),
                    "max_concurrent_observed": int(metrics["max_concurrent_observed"]),
                    "signal_conflicts": int(metrics["signal_conflicts"]),
                    "internal_pair_conflicts": int(metrics["internal_pair_conflicts"]),
                }
            ]
        )
        handle.write(markdown_table(metrics_frame))

        handle.write("\n## Long vs Short Contribution\n\n")
        side_frame = pd.DataFrame(
            [
                {
                    "side": "long",
                    "fragments": int(metrics["long_total_trades"]),
                    "positions": int(metrics["long_closed_positions"]),
                    "total_profit": float(metrics["long_total_profit"]),
                },
                {
                    "side": "short",
                    "fragments": int(metrics["short_total_trades"]),
                    "positions": int(metrics["short_closed_positions"]),
                    "total_profit": float(metrics["short_total_profit"]),
                },
            ]
        )
        handle.write(markdown_table(side_frame))

        handle.write("\n## Final Pairs Traded\n\n")
        pair_display = pair_rows_df[
            [
                "shortlist_priority",
                "param_id",
                "long_param_id",
                "short_param_id",
                "expectancy",
                "composite_score",
            ]
        ].copy()
        handle.write(markdown_table(pair_display))

        handle.write("\n## Realized Pair Contribution\n\n")
        handle.write(markdown_table(pair_stats_df.head(10)))

        handle.write("\n## Realized Symbol Contribution\n\n")
        handle.write(markdown_table(symbol_stats_df.head(10)))

        handle.write("\n## Monthly Return Snapshot\n\n")
        handle.write(markdown_table(monthly_returns_df.tail(12)))


def write_report(
    report_path: str,
    metrics: Dict[str, object],
    positions_df: pd.DataFrame,
    fragments_df: pd.DataFrame,
    pair_stats_df: pd.DataFrame,
    symbol_stats_df: pd.DataFrame,
    monthly_returns_df: pd.DataFrame,
) -> None:
    """Write the more detailed markdown report for the final deployment portfolio."""
    top_positions = positions_df.sort_values("realized_pnl", ascending=False).head(10) if not positions_df.empty else positions_df
    worst_positions = positions_df.sort_values("realized_pnl", ascending=True).head(10) if not positions_df.empty else positions_df
    recent_fragments = fragments_df.sort_values(["exit_dt", "trade_id"], ascending=[False, False]).head(20) if not fragments_df.empty else fragments_df

    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write("# Backtrader final portfolio report\n\n")
        handle.write("This report reflects the exact 5-pair deployment portfolio traded as one Maven account.\n\n")

        handle.write("## Core Metrics\n\n")
        core_frame = pd.DataFrame(
            [
                {
                    "ending_equity": float(metrics["ending_equity"]),
                    "total_profit": float(metrics["total_profit"]),
                    "total_return_pct": float(metrics["total_return"]) * 100.0,
                    "max_dd_pct": float(metrics["max_dd_pct"]),
                    "consistency_score": float(metrics["consistency_score"]),
                    "position_win_rate": float(metrics["position_win_rate"]),
                    "avg_position_pnl": float(metrics["avg_position_pnl"]),
                    "best_position_pnl": float(metrics["best_position_pnl"]),
                    "worst_position_pnl": float(metrics["worst_position_pnl"]),
                    "avg_holding_days": float(metrics["avg_holding_days"]),
                    "max_consecutive_position_wins": int(metrics["max_consecutive_position_wins"]),
                    "max_consecutive_position_losses": int(metrics["max_consecutive_position_losses"]),
                }
            ]
        )
        handle.write(markdown_table(core_frame))

        handle.write("\n## Pair Contribution\n\n")
        handle.write(markdown_table(pair_stats_df))

        handle.write("\n## Symbol Contribution\n\n")
        handle.write(markdown_table(symbol_stats_df))

        handle.write("\n## Monthly Returns\n\n")
        handle.write(markdown_table(monthly_returns_df))

        handle.write("\n## Top 10 Positions\n\n")
        handle.write(markdown_table(top_positions))

        handle.write("\n## Worst 10 Positions\n\n")
        handle.write(markdown_table(worst_positions))

        handle.write("\n## Recent 20 Exit Fragments\n\n")
        handle.write(markdown_table(recent_fragments))


def parse_args() -> argparse.Namespace:
    """Define the CLI surface for the exact final-portfolio run."""
    parser = argparse.ArgumentParser(description="Chronological Backtrader validation for the exact final TRADE_ORACLE deployment portfolio.")
    parser.add_argument("--shortlist", default=DEFAULT_FINAL_SHORTLIST, help="Path to the combined final shortlist CSV.")
    parser.add_argument("--ranking", default=DEFAULT_SURVIVOR_RANKING, help="Path to the combined survivor ranking CSV.")
    parser.add_argument("--daily-data", default=DEFAULT_DAILY_PATH, help="Path to the daily parquet file.")
    parser.add_argument("--intraday-data", default=DEFAULT_INTRADAY_PATH, help="Path to the 4H parquet file.")
    parser.add_argument("--output-prefix", default=DEFAULT_OUTPUT_PREFIX, help="Prefix for output files. Example: results/backtrader_final_portfolio")
    parser.add_argument("--top-n", type=int, default=5, help="How many final pairs to activate from the shortlist.")
    return parser.parse_args()


def run_final_portfolio(
    final_pairs: List[CombinedCandidateConfig],
    pair_rows_df: pd.DataFrame,
    catalog: MarketDataCatalog,
) -> Tuple[Dict[str, object], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run the final deployment portfolio inside one Cerebro instance."""
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(INITIAL_BALANCE)

    feed_map = catalog.add_candidate_feeds(cerebro, prefer_intraday=True)
    pair_rows = pair_rows_df.to_dict(orient="records")

    cerebro.addstrategy(MavenFinalPortfolioStrategy, final_pairs=final_pairs, pair_rows=pair_rows, feed_map=feed_map)
    results = cerebro.run(runonce=False, stdstats=False, quicknotify=False)
    strategy: MavenFinalPortfolioStrategy = results[0]

    metrics = strategy.build_metrics()
    fragments_df = pd.DataFrame(strategy.closed_fragments)
    positions_df = pd.DataFrame(strategy.closed_positions_log)
    equity_df = pd.DataFrame(strategy.equity_timeline)
    return metrics, fragments_df, positions_df, equity_df


def infer_data_window(catalog: MarketDataCatalog) -> Tuple[pd.Timestamp, pd.Timestamp]:
    """Infer the true historical window from the loaded market data."""
    start_candidates: List[pd.Timestamp] = []
    end_candidates: List[pd.Timestamp] = []

    for symbol in WATCHLIST:
        daily_frame = catalog.daily_frames[symbol]
        exec_frame = catalog.intraday_frames.get(symbol, daily_frame)
        start_candidates.append(pd.Timestamp(daily_frame.index[0]))
        end_candidates.append(pd.Timestamp(exec_frame.index[-1]))

    return min(start_candidates), max(end_candidates)


def main() -> None:
    """Main entry point used by `python scripts/backtrader_evaluate_final_portfolio.py`."""
    args = parse_args()

    final_pairs, pair_rows_df = resolve_final_pairs(
        shortlist_path=args.shortlist,
        ranking_path=args.ranking,
        top_n=args.top_n,
    )
    catalog = MarketDataCatalog(daily_path=args.daily_data, intraday_path=args.intraday_data)
    raw_start_ts, raw_end_ts = infer_data_window(catalog)

    metrics, fragments_df, positions_df, equity_df = run_final_portfolio(
        final_pairs=final_pairs,
        pair_rows_df=pair_rows_df,
        catalog=catalog,
    )
    metrics, monthly_returns_df = compute_additional_metrics(metrics, positions_df=positions_df, equity_df=equity_df)

    if equity_df.empty:
        effective_start_ts = raw_start_ts
        effective_end_ts = raw_end_ts
    else:
        effective_start_ts = pd.to_datetime(equity_df["timestamp"]).min()
        effective_end_ts = pd.to_datetime(equity_df["timestamp"]).max()

    pair_stats_df = build_pair_stats(positions_df=positions_df, pair_rows_df=pair_rows_df)
    symbol_stats_df = build_symbol_stats(positions_df=positions_df)

    metrics["raw_data_start"] = raw_start_ts.strftime("%Y-%m-%d %H:%M")
    metrics["raw_data_end"] = raw_end_ts.strftime("%Y-%m-%d %H:%M")
    metrics["backtest_start"] = effective_start_ts.strftime("%Y-%m-%d %H:%M")
    metrics["backtest_end"] = effective_end_ts.strftime("%Y-%m-%d %H:%M")
    metrics["data_mode_used"] = "1D + 4H mixed execution"

    results_csv = f"{args.output_prefix}_results.csv"
    trades_csv = f"{args.output_prefix}_trades.csv"
    positions_csv = f"{args.output_prefix}_positions.csv"
    pair_stats_csv = f"{args.output_prefix}_pair_stats.csv"
    symbol_stats_csv = f"{args.output_prefix}_symbol_stats.csv"
    equity_curve_csv = f"{args.output_prefix}_equity_curve.csv"
    monthly_returns_csv = f"{args.output_prefix}_monthly_returns.csv"
    summary_md = f"{args.output_prefix}_summary.md"
    report_md = f"{args.output_prefix}_report.md"

    pd.DataFrame([metrics]).to_csv(results_csv, index=False)
    fragments_df.to_csv(trades_csv, index=False)
    positions_df.to_csv(positions_csv, index=False)
    pair_stats_df.to_csv(pair_stats_csv, index=False)
    symbol_stats_df.to_csv(symbol_stats_csv, index=False)
    equity_df.to_csv(equity_curve_csv, index=False)
    monthly_returns_df.to_csv(monthly_returns_csv, index=False)

    assumptions = [
        "The exact final strategy is modeled as the 5 shortlisted combined pairs traded together inside one shared Maven account.",
        "Only one net position is allowed per symbol at a time.",
        "If multiple same-side pairs trigger on the same symbol and bar, they collapse into one live-style trade anchored to the highest-priority shortlisted pair.",
        "If long and short pairs disagree on the same symbol and bar, the trade is skipped rather than resolved heuristically.",
        "Risk sizing, 4-trade cap, floating-aware 3% trailing drawdown, leverage cap, and fractional scale-outs follow the existing Maven Backtrader engine exactly.",
        "Because the portfolio uses the full shared watchlist, the effective simulation starts when the latest-starting symbol plus indicator warmup becomes tradable. In the current dataset that pushes the effective start to 2024-10-21.",
    ]

    write_summary(
        summary_path=summary_md,
        metrics=metrics,
        pair_rows_df=pair_rows_df,
        pair_stats_df=pair_stats_df,
        symbol_stats_df=symbol_stats_df,
        monthly_returns_df=monthly_returns_df,
        start_ts=raw_start_ts,
        end_ts=raw_end_ts,
        catalog=catalog,
        assumptions=assumptions,
    )
    write_report(
        report_path=report_md,
        metrics=metrics,
        positions_df=positions_df,
        fragments_df=fragments_df,
        pair_stats_df=pair_stats_df,
        symbol_stats_df=symbol_stats_df,
        monthly_returns_df=monthly_returns_df,
    )

    print(f"Final portfolio results: {results_csv}")
    print(f"Final portfolio summary: {summary_md}")
    print(f"Final portfolio report: {report_md}")
    print(f"Closed positions: {int(metrics['closed_positions'])}")
    print(f"Ending equity: {float(metrics['ending_equity']):.2f}")
    print(f"Total return: {float(metrics['total_return']) * 100.0:.2f}%")
    print(f"Max drawdown: {float(metrics['max_dd_pct']):.2f}%")


if __name__ == "__main__":
    main()
