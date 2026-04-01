"""
Chronological Backtrader validation for the TRADE_ORACLE shortlist.

This evaluator is intentionally backward-compatible with both:
- the original Daily-only shortlist, and
- the newer Daily + 4H confirmation candidate files.

Recommended full run:
    python scripts/backtrader_evaluate.py

Helpful smoke test:
    python scripts/backtrader_evaluate.py --limit 2 --output-prefix results/backtrader_validation_smoke
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

try:
    from config import settings
except Exception:
    settings = None


# ==============================================================================
# PATHS AND GLOBAL DEFAULTS
# ==============================================================================

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")
DATA_DIR = os.path.join(ROOT_DIR, "data")

DEFAULT_CANDIDATES_PATH = os.path.join(RESULTS_DIR, "daily_wider_v2_backtrader_shortlist.csv")
DEFAULT_DAILY_PATH = os.path.join(DATA_DIR, "market_data_1D.parquet")
DEFAULT_INTRADAY_PATH = os.path.join(DATA_DIR, "market_data_4H.parquet")
DEFAULT_OUTPUT_PREFIX = os.path.join(RESULTS_DIR, "backtrader_validation")


# ==============================================================================
# MAVEN / STRATEGY CONSTANTS
# ==============================================================================

INITIAL_BALANCE = float(getattr(settings, "INITIAL_BALANCE", 5000.0))
RISK_PER_TRADE_USD = float(getattr(settings, "RISK_AMOUNT_USD", 10.0))
MAX_CONCURRENT_TRADES = int(getattr(settings, "MAX_CONCURRENT_TRADES", 4))
MAX_TRAILING_DRAWDOWN_PCT = float(getattr(settings, "MAX_TRAILING_DRAWDOWN_PCT", 0.03))
MAX_CRYPTO_LEVERAGE = float(getattr(settings, "MAX_CRYPTO_LEVERAGE", 2.0))
TP1_ATR_MULTIPLIER = float(getattr(settings, "TP1_ATR_MULTIPLIER", 2.0))
TP2_ATR_MULTIPLIER = float(getattr(settings, "TP2_ATR_MULTIPLIER", 3.5))
STOP_LOSS_ATR_MULTIPLIER = float(getattr(settings, "STOP_LOSS_ATR_MULTIPLIER", 1.5))
WATCHLIST = list(
    getattr(
        settings,
        "WATCHLIST",
        ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "TON/USDT", "ADA/USDT", "BNB/USDT"],
    )
)

ATR_PERIOD = 14
EMA_PERIOD = 20
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
class CandidateConfig:
    """A typed container for one row from the shortlist CSV."""

    source_rank: int
    source_symbol: str
    sma: int
    ema: int
    fib_floor: float
    fib_band: float
    rw: float
    eb: float
    rw_lookback: int
    param_id: str
    confirm_enabled: bool
    confirm_ema_period: int
    confirm_min_distance: float
    confirm_mode: str

    @classmethod
    def from_row(cls, row: pd.Series) -> "CandidateConfig":
        """
        Build a stable candidate object from a pandas row.

        The loader accepts both the original Daily shortlist schema and the newer
        Daily + 4H confirmation schema so we can reuse one evaluator file.
        """
        rank = int(first_present(row, ["combined_rank", "rank", "backtrader_rank"], 0))
        source_symbol = str(first_present(row, ["source_symbol", "symbol"], "UNKNOWN"))
        param_id = first_present(row, ["param_id"], None)
        if param_id is None:
            param_id = f"cand_{rank:03d}_{source_symbol.replace('/', '_')}"

        confirm_enabled = parse_boolish(first_present(row, ["confirm_enabled"], False), default=False)
        confirm_ema_period = int(first_present(row, ["confirm_ema_period"], 20))
        confirm_min_distance = float(first_present(row, ["confirm_min_distance"], 0.0))
        confirm_mode = str(
            first_present(
                row,
                ["confirm_mode"],
                "close_above_ema" if confirm_enabled else "disabled",
            )
        )

        return cls(
            source_rank=rank,
            source_symbol=source_symbol,
            sma=int(row["sma"]),
            ema=int(row["ema"]),
            fib_floor=float(row["fib_floor"]),
            fib_band=float(row["fib_band"]),
            rw=float(row["rw"]),
            eb=float(row["eb"]),
            rw_lookback=int(row["rw_lookback"]),
            param_id=param_id,
            confirm_enabled=confirm_enabled,
            confirm_ema_period=confirm_ema_period,
            confirm_min_distance=confirm_min_distance,
            confirm_mode=confirm_mode,
        )


class OraclePandasData(bt.feeds.PandasData):
    """Minimal pandas-backed OHLCV feed."""

    params = (
        ("datetime", None),
        ("open", "open"),
        ("high", "high"),
        ("low", "low"),
        ("close", "close"),
        ("volume", "volume"),
        ("openinterest", -1),
    )


class MarketDataCatalog:
    """
    Loads the reusable market datasets once and hands Backtrader fresh feed objects.
    """

    def __init__(self, daily_path: str, intraday_path: Optional[str]) -> None:
        self.daily_path = daily_path
        self.intraday_path = intraday_path

        self.daily_frames = self._load_by_symbol(daily_path)
        self.intraday_frames = self._load_by_symbol(intraday_path) if intraday_path and os.path.exists(intraday_path) else {}

        self.available_daily_symbols = sorted(self.daily_frames.keys())
        self.available_intraday_symbols = sorted(self.intraday_frames.keys())

        missing_watchlist = [symbol for symbol in WATCHLIST if symbol not in self.daily_frames]
        if missing_watchlist:
            raise ValueError(f"Daily data is missing required watchlist symbols: {missing_watchlist}")

    def _load_by_symbol(self, path: Optional[str]) -> Dict[str, pd.DataFrame]:
        """Load a parquet file once and split it into one DataFrame per symbol."""
        if not path:
            return {}
        if not os.path.exists(path):
            raise FileNotFoundError(f"Market data file not found: {path}")

        df = pd.read_parquet(path)
        if "symbol" not in df.columns or "timestamp" not in df.columns:
            raise ValueError(f"Expected `symbol` and `timestamp` columns in {path}")

        frames: Dict[str, pd.DataFrame] = {}
        for symbol in sorted(df["symbol"].astype(str).unique().tolist()):
            frame = (
                df.loc[df["symbol"] == symbol, ["timestamp", "open", "high", "low", "close", "volume"]]
                .copy()
                .sort_values("timestamp")
                .set_index("timestamp")
            )
            frames[symbol] = frame
        return frames

    def add_candidate_feeds(self, cerebro: bt.Cerebro, prefer_intraday: bool = True) -> Dict[str, Dict[str, str]]:
        """
        Add one execution feed and one Daily signal feed per symbol.

        We intentionally load the Daily signal feed explicitly from the Daily parquet
        rather than resampling inside Backtrader. That is a little more verbose, but
        it is materially more robust on mixed-timeframe portfolios.
        """
        feed_map: Dict[str, Dict[str, str]] = {}
        for symbol in WATCHLIST:
            exec_name = f"{symbol}__exec"
            signal_name = f"{symbol}__signal"
            signal_feed = OraclePandasData(dataname=self.daily_frames[symbol].copy())
            cerebro.adddata(signal_feed, name=signal_name)

            if prefer_intraday and symbol in self.intraday_frames:
                exec_feed = OraclePandasData(dataname=self.intraday_frames[symbol].copy())
                cerebro.adddata(exec_feed, name=exec_name)
                feed_map[symbol] = {"exec_name": exec_name, "signal_name": signal_name, "data_mode": "4H->1D"}
            else:
                exec_feed = OraclePandasData(dataname=self.daily_frames[symbol].copy())
                cerebro.adddata(exec_feed, name=exec_name)
                feed_map[symbol] = {"exec_name": exec_name, "signal_name": signal_name, "data_mode": "1D"}

        return feed_map

    def describe_modes(self) -> Dict[str, int]:
        """Return a small summary for the markdown report."""
        intraday_count = len([symbol for symbol in WATCHLIST if symbol in self.intraday_frames])
        daily_only_count = len(WATCHLIST) - intraday_count
        return {"intraday_symbols": intraday_count, "daily_fallback_symbols": daily_only_count}


class MavenCandidateStrategy(bt.Strategy):
    """
    One complete chronological evaluation of one candidate parameter set.

    The strategy intentionally does its own portfolio accounting instead of relying on
    Backtrader's broker/order bookkeeping. That gives us direct control over:
    - fractional scale-outs,
    - fixed-dollar risk sizing,
    - mixed timeframe feeds,
    - conservative floating-PnL drawdown snapshots, and
    - consistency-rule accounting at the fragment level.
    """

    params = (
        ("candidate", None),
        ("feed_map", None),
    )

    def __init__(self) -> None:
        self.candidate: CandidateConfig = self.p.candidate
        self.feed_map: Dict[str, Dict[str, str]] = self.p.feed_map

        # These are the mutable portfolio state variables that the analyzer will read.
        self.sim_cash = INITIAL_BALANCE
        self.peak_equity = INITIAL_BALANCE
        self.max_drawdown_dollars = 0.0
        self.max_drawdown_pct = 0.0
        self.breached = False
        self.account_locked = False
        self.max_positions_seen = 0

        # The realized PnL fragments are the objects we use for win rate, expectancy,
        # and the prop-firm consistency calculation.
        self.closed_fragments: List[Dict[str, object]] = []
        self.closed_positions = 0
        self.trade_counter = 0

        # Each symbol gets its own execution feed, signal feed, indicators, and trade state.
        self.asset_states: Dict[str, Dict[str, object]] = {}
        for symbol, mapping in self.feed_map.items():
            signal_data = self.getdatabyname(mapping["signal_name"])
            exec_data = self.getdatabyname(mapping["exec_name"])
            state = {
                "symbol": symbol,
                "data_mode": mapping["data_mode"],
                "exec_data": exec_data,
                "signal_data": signal_data,
                "last_exec_len": 0,
                "last_signal_len": 0,
                "pending_entry": None,
                "position": None,
                # The signal indicators deliberately mirror the discovery-phase logic.
                "sma": bt.indicators.SimpleMovingAverage(signal_data.close, period=self.candidate.sma),
                "ema": bt.indicators.ExponentialMovingAverage(signal_data.close, period=EMA_PERIOD),
                "atr": bt.indicators.AverageTrueRange(signal_data, period=ATR_PERIOD),
                "high30": bt.indicators.Highest(signal_data.high, period=FIB_LOOKBACK),
                "low30": bt.indicators.Lowest(signal_data.low, period=FIB_LOOKBACK),
                # The confirmation EMA lives on the execution feed so it naturally uses
                # real 4H data where available and Daily fallback otherwise.
                "confirm_ema": (
                    bt.indicators.ExponentialMovingAverage(exec_data.close, period=self.candidate.confirm_ema_period)
                    if self.candidate.confirm_enabled
                    else None
                ),
            }
            self.asset_states[symbol] = state

    def _active_positions(self) -> int:
        """Count open positions across the full portfolio."""
        return sum(1 for state in self.asset_states.values() if state["position"] is not None)

    def _mark_price(self, state: Dict[str, object], mark: str) -> float:
        """Resolve the requested mark price from the current execution bar."""
        data = state["exec_data"]
        if mark == "high":
            return float(data.high[0])
        if mark == "low":
            return float(data.low[0])
        return float(data.close[0])

    def _open_notional(self, mark: str = "close") -> float:
        """Estimate the gross notional currently deployed across all open positions."""
        notional = 0.0
        for state in self.asset_states.values():
            position = state["position"]
            if not position:
                continue
            price = self._mark_price(state, mark)
            notional += float(position["remaining_size"]) * price
        return notional

    def _portfolio_equity(self, mark: str = "close") -> float:
        """
        Compute portfolio equity using the requested mark price for each open position.
        """

        equity = self.sim_cash
        for state in self.asset_states.values():
            position = state["position"]
            if not position:
                continue
            current_price = self._mark_price(state, mark)
            equity += (current_price - float(position["entry_price"])) * float(position["remaining_size"])
        return float(equity)

    def _update_drawdown_state(self) -> None:
        """
        Update the account watermark and trailing-drawdown state.

        The sequencing is intentionally conservative:
        1. Mark open positions to the bar high and update the peak watermark.
        2. Mark open positions to the bar low and measure drawdown from that peak.
        """

        high_equity = self._portfolio_equity(mark="high")
        low_equity = self._portfolio_equity(mark="low")

        if high_equity > self.peak_equity:
            self.peak_equity = high_equity

        drawdown_dollars = max(0.0, self.peak_equity - low_equity)
        drawdown_pct = (drawdown_dollars / self.peak_equity) if self.peak_equity > 0 else 0.0

        if drawdown_dollars > self.max_drawdown_dollars:
            self.max_drawdown_dollars = drawdown_dollars
        if drawdown_pct > self.max_drawdown_pct:
            self.max_drawdown_pct = drawdown_pct

        if drawdown_pct >= MAX_TRAILING_DRAWDOWN_PCT:
            self.breached = True
            self.account_locked = True

    def _force_liquidate_all(self, reason: str) -> None:
        """Immediately close every open position at the current close after a breach."""
        for state in self.asset_states.values():
            position = state["position"]
            if not position:
                continue
            exit_price = float(state["exec_data"].close[0])
            self._close_fragment(state, float(position["remaining_size"]), exit_price, reason, force_close=True)

    def _signal_is_ready(self, state: Dict[str, object]) -> bool:
        """Backtrader indicators become valid only after enough bars have accumulated."""
        signal_data = state["signal_data"]
        min_required = max(self.candidate.sma, FIB_LOOKBACK, self.candidate.rw_lookback, ATR_PERIOD) + 1
        if len(signal_data) < min_required:
            return False

        if not self.candidate.confirm_enabled:
            return True

        exec_data = state["exec_data"]
        return len(exec_data) >= max(1, self.candidate.confirm_ema_period)

    def _confirmation_is_valid(self, state: Dict[str, object]) -> bool:
        """
        Check the optional execution-time confirmation filter.

        Current confirmation logic is intentionally simple:
        - execution close must be above the execution EMA
        - the distance above EMA must meet the configured minimum threshold
        """

        if not self.candidate.confirm_enabled:
            return True

        exec_data = state["exec_data"]
        confirm_ema = state["confirm_ema"]
        if confirm_ema is None:
            return False

        exec_close = float(exec_data.close[0])
        ema_value = float(confirm_ema[0])

        if any(math.isnan(value) for value in [exec_close, ema_value]):
            return False
        if exec_close <= 0.0 or ema_value <= 0.0:
            return False

        confirm_distance = (exec_close - ema_value) / ema_value
        return bool(exec_close > ema_value and confirm_distance >= self.candidate.confirm_min_distance)

    def _signal_is_valid(self, state: Dict[str, object]) -> Optional[Dict[str, float]]:
        """
        Mirror the discovery-phase confluence logic exactly.

        Current discovery logic is long-oriented:
        - price above SMA
        - retracement inside the configured fib zone
        - close near EMA within the configured buffer
        - relative weakness threshold satisfied over the configured lookback
        """

        if not self._signal_is_ready(state):
            return None

        signal_data = state["signal_data"]
        close = float(signal_data.close[0])
        sma = float(state["sma"][0])
        ema = float(state["ema"][0])
        atr = float(state["atr"][0])
        high30 = float(state["high30"][0])
        low30 = float(state["low30"][0])

        if any(math.isnan(value) for value in [close, sma, ema, atr, high30, low30]):
            return None
        if close <= 0.0 or atr <= 0.0 or high30 <= low30:
            return None

        prev_close = float(signal_data.close[-self.candidate.rw_lookback])
        if prev_close <= 0.0:
            return None

        retracement = (high30 - close) / (high30 - low30)
        rw_value = (prev_close - close) / prev_close
        ema_distance = abs(close - ema) / close

        is_valid = (
            close > sma
            and self.candidate.fib_floor <= retracement <= self.candidate.fib_band
            and ema_distance <= self.candidate.eb
            and rw_value >= self.candidate.rw
        )

        if not is_valid:
            return None

        if not self._confirmation_is_valid(state):
            return None

        return {
            "atr": atr,
            "signal_close": close,
            "retracement": retracement,
            "rw_value": rw_value,
        }

    def _schedule_entry_if_needed(self, state: Dict[str, object]) -> None:
        """
        Create a pending entry when a new daily signal appears.

        Entries are intentionally delayed to the next execution-bar open, which avoids
        using same-bar close information for same-bar fills.
        """

        if self.account_locked:
            return
        if state["position"] is not None or state["pending_entry"] is not None:
            return

        signal_payload = self._signal_is_valid(state)
        if not signal_payload:
            return

        state["pending_entry"] = {
            "atr": float(signal_payload["atr"]),
            "scheduled_from": bt.num2date(state["signal_data"].datetime[0]),
            "signal_close": float(signal_payload["signal_close"]),
        }

    def _try_open_pending_entry(self, state: Dict[str, object]) -> None:
        """
        Open a pending position at the next execution-bar open if portfolio rules allow it.
        """

        pending = state["pending_entry"]
        if not pending:
            return

        # We only keep the signal alive for the first eligible execution bar.
        state["pending_entry"] = None

        if self.account_locked:
            return
        if self._active_positions() >= MAX_CONCURRENT_TRADES:
            return

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
        state["position"] = {
            "trade_id": self.trade_counter,
            "entry_dt": bt.num2date(state["exec_data"].datetime[0]),
            "entry_price": entry_price,
            "remaining_size": size,
            "initial_size": size,
            "stop_price": entry_price - stop_distance,
            "tp1_price": entry_price + (atr * TP1_ATR_MULTIPLIER),
            "tp2_price": entry_price + (atr * TP2_ATR_MULTIPLIER),
            "tp1_done": False,
        }

        self.max_positions_seen = max(self.max_positions_seen, self._active_positions())

    def _close_fragment(
        self,
        state: Dict[str, object],
        size_to_close: float,
        exit_price: float,
        reason: str,
        force_close: bool = False,
    ) -> None:
        """
        Realize one exit fragment and update all performance ledgers.
        """

        position = state["position"]
        if not position or size_to_close <= 0.0:
            return

        size_to_close = min(size_to_close, float(position["remaining_size"]))
        entry_price = float(position["entry_price"])
        pnl = (exit_price - entry_price) * size_to_close
        self.sim_cash += pnl

        fragment = {
            "trade_id": int(position["trade_id"]),
            "symbol": str(state["symbol"]),
            "entry_dt": position["entry_dt"],
            "exit_dt": bt.num2date(state["exec_data"].datetime[0]),
            "entry_price": entry_price,
            "exit_price": float(exit_price),
            "size": float(size_to_close),
            "pnl": float(pnl),
            "reason": reason,
        }
        self.closed_fragments.append(fragment)

        position["remaining_size"] = float(position["remaining_size"]) - size_to_close
        if force_close or position["remaining_size"] <= 1e-12:
            state["position"] = None
            self.closed_positions += 1

    def _manage_open_position(self, state: Dict[str, object]) -> None:
        """
        Manage one open position using the current execution bar.

        Conservative bar-ordering assumptions:
        - A stop hit takes priority over target hits if both are touched in the same bar.
        - If TP2 is reached before TP1 has been marked, we still fragment the exit into
          a 50% TP1 fill and a 50% TP2 fill, because the market necessarily passed TP1.
        """

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

    def next(self) -> None:
        """
        Advance the portfolio state one Backtrader event at a time.
        """

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
        """Close any leftover positions at the final close so metrics are complete."""
        for state in self.asset_states.values():
            if state["position"] is None:
                continue
            exit_price = float(state["exec_data"].close[0])
            self._close_fragment(state, float(state["position"]["remaining_size"]), exit_price, reason="final_bar_close", force_close=True)

    def build_metrics(self) -> Dict[str, float]:
        """Return the final strategy metrics in one normalized dictionary."""
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
        close_equity = self._portfolio_equity(mark="close")

        return {
            "total_trades": int(total_trades),
            "closed_positions": int(self.closed_positions),
            "win_rate": float(win_rate),
            "expectancy": float(expectancy),
            "total_profit": float(total_profit),
            "total_return": float(total_return),
            "ending_equity": float(close_equity),
            "peak_equity": float(self.peak_equity),
            "max_dd_dollars": float(self.max_drawdown_dollars),
            "max_dd_pct": float(self.max_drawdown_pct * 100.0),
            "breached": bool(self.breached),
            "consistency_score": float(consistency_score),
            "overall_survival": bool(overall_survival),
            "max_concurrent_observed": int(self.max_positions_seen),
        }


class MavenComplianceAnalyzer(bt.Analyzer):
    """
    Passive analyzer that snapshots the strategy's compliance state during the run.
    """

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


def load_candidates(path: str) -> List[CandidateConfig]:
    """Read the shortlist CSV and convert each row into a typed candidate object."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Candidate file not found: {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError("Candidate file is empty.")
    return [CandidateConfig.from_row(row) for _, row in df.iterrows()]


def run_one_candidate(candidate: CandidateConfig, catalog: MarketDataCatalog, prefer_intraday: bool) -> Dict[str, object]:
    """
    Run one candidate in its own Cerebro instance and return a flat result row.
    """

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(INITIAL_BALANCE)

    feed_map = catalog.add_candidate_feeds(cerebro, prefer_intraday=prefer_intraday)
    data_modes = sorted(set(mapping["data_mode"] for mapping in feed_map.values()))

    cerebro.addstrategy(MavenCandidateStrategy, candidate=candidate, feed_map=feed_map)
    cerebro.addanalyzer(MavenComplianceAnalyzer, _name="maven")

    # `runonce=False` keeps the mixed timeframe updates predictable for this custom logic.
    results = cerebro.run(runonce=False, stdstats=False, quicknotify=False)
    strategy = results[0]
    analysis = strategy.analyzers.maven.get_analysis()

    row = {
        "rank": int(candidate.source_rank),
        "param_id": candidate.param_id,
        "source_symbol": candidate.source_symbol,
        "sma": int(candidate.sma),
        "ema": int(candidate.ema),
        "fib_floor": float(candidate.fib_floor),
        "fib_band": float(candidate.fib_band),
        "rw": float(candidate.rw),
        "eb": float(candidate.eb),
        "rw_lookback": int(candidate.rw_lookback),
        "confirm_enabled": bool(candidate.confirm_enabled),
        "confirm_mode": str(candidate.confirm_mode),
        "confirm_ema_period": int(candidate.confirm_ema_period),
        "confirm_min_distance": float(candidate.confirm_min_distance),
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
    """Write a markdown summary with the key run stats and the top survivors."""
    survivors = results_df.loc[results_df["overall_survival"]].copy()
    top_survivors = survivors.head(10)
    mode_info = catalog.describe_modes()
    has_confirmation = bool(
        "confirm_enabled" in results_df.columns
        and results_df["confirm_enabled"].fillna(False).astype(bool).any()
    )

    def _markdown_table(frame: pd.DataFrame) -> str:
        """Render a tiny markdown table without needing the optional `tabulate` package."""
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
        handle.write("# Backtrader validation summary\n\n")
        handle.write(f"- **source_candidates_file**: {candidates_path}\n")
        handle.write(f"- **candidates_evaluated**: {len(results_df)}\n")
        handle.write(f"- **survivors**: {len(survivors)}\n")
        handle.write(f"- **breached_accounts**: {int(results_df['breached'].sum())}\n")
        handle.write(f"- **median_max_dd_pct**: {results_df['max_dd_pct'].median():.2f}\n")
        handle.write(f"- **median_consistency_score**: {results_df['consistency_score'].median():.2f}\n")
        handle.write(f"- **best_expectancy**: {results_df['expectancy'].max():.2f}\n")
        handle.write(f"- **best_total_return_pct**: {results_df['total_return'].max() * 100.0:.2f}\n")
        if has_confirmation:
            handle.write("- **confirmation_filter**: enabled for this candidate set\n")
        handle.write("\n## Data Coverage Notes\n\n")
        handle.write(f"- **4H execution + Daily signals available**: {mode_info['intraday_symbols']} symbols\n")
        handle.write(f"- **Daily fallback symbols**: {mode_info['daily_fallback_symbols']} symbols\n")
        handle.write("- Mixed-timeframe validation is therefore partially intraday-aware, not fully intraday for the whole watchlist.\n")

        handle.write("\n## Top 10 Surviving Candidates\n\n")
        if top_survivors.empty:
            handle.write("No candidates survived the current compliance filters.\n")
        else:
            cols = [
                "rank",
                "param_id",
                "source_symbol",
            ]
            if has_confirmation:
                cols.extend(["confirm_ema_period", "confirm_min_distance"])
            cols.extend(
                [
                "total_trades",
                "win_rate",
                "expectancy",
                "max_dd_pct",
                "consistency_score",
                "overall_survival",
                ]
            )
            handle.write(_markdown_table(top_survivors[cols]))
            handle.write("\n")


def evaluate_candidates(
    candidates: List[CandidateConfig],
    catalog: MarketDataCatalog,
    output_csv: str,
    summary_md: str,
    candidates_path: str,
    prefer_intraday: bool,
    flush_every: int,
) -> pd.DataFrame:
    """
    Evaluate every candidate and write incremental results as we go.
    """

    partial_rows: List[Dict[str, object]] = []
    all_rows: List[Dict[str, object]] = []

    if os.path.exists(output_csv):
        os.remove(output_csv)

    progress = tqdm(candidates, desc="Backtrader validation", unit="candidate")
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
                "source_symbol": candidate.source_symbol,
                "sma": int(candidate.sma),
                "ema": int(candidate.ema),
                "fib_floor": float(candidate.fib_floor),
                "fib_band": float(candidate.fib_band),
                "rw": float(candidate.rw),
                "eb": float(candidate.eb),
                "rw_lookback": int(candidate.rw_lookback),
                "confirm_enabled": bool(candidate.confirm_enabled),
                "confirm_mode": str(candidate.confirm_mode),
                "confirm_ema_period": int(candidate.confirm_ema_period),
                "confirm_min_distance": float(candidate.confirm_min_distance),
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
    """Define the CLI surface for normal runs and smaller smoke checks."""
    parser = argparse.ArgumentParser(description="Chronological Backtrader validation for the TRADE_ORACLE shortlist.")
    parser.add_argument("--candidates", default=DEFAULT_CANDIDATES_PATH, help="Path to the shortlist CSV.")
    parser.add_argument("--daily-data", default=DEFAULT_DAILY_PATH, help="Path to the daily parquet file.")
    parser.add_argument(
        "--intraday-data",
        default=DEFAULT_INTRADAY_PATH,
        help="Path to the 4H parquet file used when intraday execution is available.",
    )
    parser.add_argument(
        "--output-prefix",
        default=DEFAULT_OUTPUT_PREFIX,
        help="Prefix for output files. Example: results/backtrader_validation",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional cap for smoke tests.")
    parser.add_argument("--start-rank", type=int, default=None, help="Optional inclusive shortlist rank lower bound.")
    parser.add_argument("--end-rank", type=int, default=None, help="Optional inclusive shortlist rank upper bound.")
    parser.add_argument(
        "--no-intraday",
        action="store_true",
        help="Force Daily-only validation even if 4H data exists.",
    )
    parser.add_argument(
        "--flush-every",
        type=int,
        default=10,
        help="Write partial CSV progress every N candidates.",
    )
    return parser.parse_args()


def select_candidates(candidates: List[CandidateConfig], args: argparse.Namespace) -> List[CandidateConfig]:
    """Apply rank-range filters and optional limits from the CLI."""
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
    """Main entry point used by `python scripts/backtrader_evaluate.py`."""
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
    print(f"Candidates evaluated: {len(results_df)}")
    print(f"Survivors: {survivors}")


if __name__ == "__main__":
    main()
