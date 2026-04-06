"""
Chronological Backtrader validation for the near-3-year final TRADE_ORACLE deployment portfolio.

This evaluator replays the exact 5 shortlisted combined pairs inside one shared
Maven account while improving realism in three places:
- symbols become tradable independently when their own history is ready,
- shortlisted pairs may hold independent same-symbol same-side positions, and
- deterministic execution frictions model fees, spread, slippage, latency,
  rejected entries, and partial fills.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
from dataclasses import dataclass
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
from backtrader_evaluate_final_portfolio import (
    build_pair_stats,
    build_symbol_stats,
    compute_additional_metrics,
    infer_data_window,
    markdown_table,
    resolve_final_pairs,
)


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

DEFAULT_FINAL_SHORTLIST = os.path.join(RESULTS_DIR, "backtrader_combined_final_shortlist.csv")
DEFAULT_SURVIVOR_RANKING = os.path.join(RESULTS_DIR, "backtrader_combined_survivor_ranking.csv")
DEFAULT_OUTPUT_PREFIX = os.path.join(RESULTS_DIR, "backtrader_final_portfolio_full")
DEFAULT_PRIOR_NETTED_RESULTS = os.path.join(RESULTS_DIR, "backtrader_final_portfolio_results.csv")

FRICTIONLESS_PRESET_NAME = "frictionless_reference"
BASELINE_PRESET_NAME = "baseline"
STRESS_PRESET_NAME = "stress"
OFFICIAL_REFERENCE_PRESET = BASELINE_PRESET_NAME

MAJOR_SYMBOLS = {"BTC/USDT", "ETH/USDT"}
MEME_OR_NEWER_SYMBOLS = {"DOGE/USDT", "TON/USDT"}


@dataclass(frozen=True)
class ExecutionFrictionPreset:
    """Deterministic execution-friction assumptions for one portfolio rerun."""

    name: str
    fee_bps: float
    major_spread_bps: float
    liquid_alt_spread_bps: float
    meme_alt_spread_bps: float
    major_entry_slippage_bps: float
    liquid_alt_entry_slippage_bps: float
    meme_alt_entry_slippage_bps: float
    stop_slippage_multiplier: float
    extra_latency_one_rate: float
    extra_latency_two_rate: float
    rejection_rate: float
    partial_fill_rate: float
    partial_fill_min_ratio: float
    partial_fill_max_ratio: float


FRICTION_PRESETS: Dict[str, ExecutionFrictionPreset] = {
    FRICTIONLESS_PRESET_NAME: ExecutionFrictionPreset(
        name=FRICTIONLESS_PRESET_NAME,
        fee_bps=0.0,
        major_spread_bps=0.0,
        liquid_alt_spread_bps=0.0,
        meme_alt_spread_bps=0.0,
        major_entry_slippage_bps=0.0,
        liquid_alt_entry_slippage_bps=0.0,
        meme_alt_entry_slippage_bps=0.0,
        stop_slippage_multiplier=0.0,
        extra_latency_one_rate=0.0,
        extra_latency_two_rate=0.0,
        rejection_rate=0.0,
        partial_fill_rate=0.0,
        partial_fill_min_ratio=1.0,
        partial_fill_max_ratio=1.0,
    ),
    BASELINE_PRESET_NAME: ExecutionFrictionPreset(
        name=BASELINE_PRESET_NAME,
        fee_bps=5.0,
        major_spread_bps=4.0,
        liquid_alt_spread_bps=8.0,
        meme_alt_spread_bps=12.0,
        major_entry_slippage_bps=1.0,
        liquid_alt_entry_slippage_bps=3.0,
        meme_alt_entry_slippage_bps=5.0,
        stop_slippage_multiplier=2.0,
        extra_latency_one_rate=0.10,
        extra_latency_two_rate=0.0,
        rejection_rate=0.015,
        partial_fill_rate=0.08,
        partial_fill_min_ratio=0.60,
        partial_fill_max_ratio=0.90,
    ),
    STRESS_PRESET_NAME: ExecutionFrictionPreset(
        name=STRESS_PRESET_NAME,
        fee_bps=10.0,
        major_spread_bps=10.0,
        liquid_alt_spread_bps=16.0,
        meme_alt_spread_bps=24.0,
        major_entry_slippage_bps=3.0,
        liquid_alt_entry_slippage_bps=6.0,
        meme_alt_entry_slippage_bps=10.0,
        stop_slippage_multiplier=2.0,
        extra_latency_one_rate=0.20,
        extra_latency_two_rate=0.05,
        rejection_rate=0.04,
        partial_fill_rate=0.15,
        partial_fill_min_ratio=0.35,
        partial_fill_max_ratio=0.70,
    ),
}


def parse_args() -> argparse.Namespace:
    """Define the CLI surface for the full final-portfolio run."""
    parser = argparse.ArgumentParser(description="Near-3-year Backtrader validation for the exact final TRADE_ORACLE deployment portfolio.")
    parser.add_argument("--shortlist", default=DEFAULT_FINAL_SHORTLIST, help="Path to the combined final shortlist CSV.")
    parser.add_argument("--ranking", default=DEFAULT_SURVIVOR_RANKING, help="Path to the combined survivor ranking CSV.")
    parser.add_argument("--daily-data", default=DEFAULT_DAILY_PATH, help="Path to the daily parquet file.")
    parser.add_argument("--intraday-data", default=DEFAULT_INTRADAY_PATH, help="Path to the 4H parquet file.")
    parser.add_argument("--output-prefix", default=DEFAULT_OUTPUT_PREFIX, help="Prefix for output files. Example: results/backtrader_final_portfolio_full")
    parser.add_argument("--top-n", type=int, default=5, help="How many final pairs to activate from the shortlist.")
    parser.add_argument(
        "--friction-mode",
        default="both",
        choices=["baseline", "stress", "both"],
        help="Which deterministic execution-friction scenario(s) to run.",
    )
    return parser.parse_args()


def bps_to_decimal(value_bps: float) -> float:
    """Convert basis points into a decimal fraction."""
    return float(value_bps) / 10000.0


def classify_symbol(symbol: str) -> str:
    """Assign each symbol to the friction tier used by the deterministic presets."""
    if symbol in MAJOR_SYMBOLS:
        return "major"
    if symbol in MEME_OR_NEWER_SYMBOLS:
        return "meme_or_newer"
    return "liquid_alt"


def stable_fraction(*parts: object) -> float:
    """Return a deterministic pseudo-random fraction in [0, 1)."""
    payload = "||".join(str(part) for part in parts).encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    numerator = int.from_bytes(digest[:8], byteorder="big", signed=False)
    return numerator / float(2**64)


def stable_roll(probability: float, *parts: object) -> bool:
    """Return a deterministic Bernoulli draw for the requested probability."""
    if probability <= 0.0:
        return False
    if probability >= 1.0:
        return True
    return stable_fraction(*parts) < probability


def stable_uniform(low: float, high: float, *parts: object) -> float:
    """Return a deterministic uniform draw on the closed interval [low, high]."""
    if high <= low:
        return float(low)
    return float(low) + ((float(high) - float(low)) * stable_fraction(*parts))


def timestamp_key(value: object) -> str:
    """Normalize timestamps into a stable string for deterministic hashing."""
    if value is None:
        return "none"
    return pd.Timestamp(value).isoformat()


def compute_months_covered(start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> int:
    """Return the inclusive number of calendar months covered by the effective window."""
    start_period = pd.Timestamp(start_ts).to_period("M")
    end_period = pd.Timestamp(end_ts).to_period("M")
    return int((end_period.year - start_period.year) * 12 + (end_period.month - start_period.month) + 1)


def preset_output_prefix(base_prefix: str, preset_name: str) -> str:
    """Build the per-preset output prefix."""
    return f"{base_prefix}_{preset_name}"


def load_prior_netted_results(path: str) -> Optional[pd.Series]:
    """Load the previously generated netted frictionless portfolio result when available."""
    if not os.path.exists(path):
        return None
    frame = pd.read_csv(path)
    if frame.empty:
        return None
    return frame.iloc[0].copy()


class MavenFinalPortfolioFullStrategy(bt.Strategy):
    """Trade the final 5 shortlisted combined pairs under one shared Maven account."""

    params = (
        ("final_pairs", None),
        ("pair_rows", None),
        ("feed_map", None),
        ("friction_preset", None),
    )

    def __init__(self) -> None:
        self.final_pairs: List[CombinedCandidateConfig] = list(self.p.final_pairs or [])
        self.pair_rows: List[Dict[str, object]] = list(self.p.pair_rows or [])
        self.feed_map: Dict[str, Dict[str, str]] = self.p.feed_map
        self.friction_preset: ExecutionFrictionPreset = self.p.friction_preset

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

        self.trade_counter = 0
        self.closed_positions = 0
        self.portfolio_start_ts: Optional[pd.Timestamp] = None

        self.trade_events: List[Dict[str, object]] = []
        self.closed_positions_log: List[Dict[str, object]] = []
        self.equity_timeline: List[Dict[str, object]] = []
        self.symbol_activation_rows: List[Dict[str, object]] = []

        self.same_symbol_opposite_conflicts = 0
        self.same_pair_duplicate_blocks = 0
        self.stacked_same_side_entries = 0
        self.entry_rejections = 0
        self.partial_fill_events = 0
        self.extra_latency_events = 0
        self.internal_pair_conflicts = 0

        self.side_fragment_counts: Dict[str, int] = {"long": 0, "short": 0}
        self.side_closed_positions: Dict[str, int] = {"long": 0, "short": 0}
        self.side_total_profit: Dict[str, float] = {"long": 0.0, "short": 0.0}

        self.asset_states: Dict[str, Dict[str, object]] = {}
        for symbol, mapping in self.feed_map.items():
            signal_data = self.getdatabyname(mapping["signal_name"])
            exec_data = self.getdatabyname(mapping["exec_name"])

            daily_requirements: List[int] = []
            exec_requirements: List[int] = []
            pair_blocks: Dict[str, Dict[str, object]] = {}
            for pair in self.final_pairs:
                pair_meta = self.pair_lookup[pair.param_id]
                pair_blocks[pair.param_id] = {
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

                for cfg in [pair.long_candidate, pair.short_candidate]:
                    daily_requirements.append(max(cfg.sma, cfg.ema, FIB_LOOKBACK, cfg.rw_lookback, ATR_PERIOD) + 1)
                    exec_requirements.append(max(1, int(cfg.confirm_ema_period)) if cfg.confirm_enabled else 1)

            self.asset_states[symbol] = {
                "symbol": symbol,
                "data_mode": mapping["data_mode"],
                "exec_data": exec_data,
                "signal_data": signal_data,
                "last_exec_len": 0,
                "last_signal_len": 0,
                "pending_entries": {},
                "positions": {},
                "activation_ts": None,
                "dynamic_added": False,
                "required_daily_bars": max(daily_requirements) if daily_requirements else 1,
                "required_exec_bars": max(exec_requirements) if exec_requirements else 1,
                "atr": bt.indicators.AverageTrueRange(signal_data, period=ATR_PERIOD),
                "high30": bt.indicators.Highest(signal_data.high, period=FIB_LOOKBACK),
                "low30": bt.indicators.Lowest(signal_data.low, period=FIB_LOOKBACK),
                "pair_blocks": pair_blocks,
            }

    def _iter_open_positions(self):
        for state in self.asset_states.values():
            for pair_id, position in state["positions"].items():
                yield state, pair_id, position

    def _active_positions(self) -> int:
        return sum(len(state["positions"]) for state in self.asset_states.values())

    def _mark_price(self, state: Dict[str, object], mark: str, side: str) -> float:
        data = state["exec_data"]
        if mark == "best":
            return float(data.high[0]) if side == "long" else float(data.low[0])
        if mark == "worst":
            return float(data.low[0]) if side == "long" else float(data.high[0])
        return float(data.close[0])

    def _open_notional(self, mark: str = "close") -> float:
        notional = 0.0
        for state, _, position in self._iter_open_positions():
            price = self._mark_price(state, mark=mark, side=str(position["side"]))
            notional += float(position["remaining_size"]) * price
        return float(notional)

    def _portfolio_equity(self, mark: str = "close") -> float:
        equity = self.sim_cash
        for state, _, position in self._iter_open_positions():
            side = str(position["side"])
            current_price = self._mark_price(state, mark=mark, side=side)
            entry_price = float(position["entry_fill_price"])
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

    def _symbol_ready(self, state: Dict[str, object]) -> bool:
        return bool(
            len(state["signal_data"]) >= int(state["required_daily_bars"])
            and len(state["exec_data"]) >= int(state["required_exec_bars"])
        )

    def _refresh_symbol_activation(self, state: Dict[str, object]) -> None:
        if state["activation_ts"] is not None:
            return
        if not self._symbol_ready(state):
            return

        activation_ts = max(
            pd.Timestamp(bt.num2date(state["signal_data"].datetime[0])),
            pd.Timestamp(bt.num2date(state["exec_data"].datetime[0])),
        )
        state["activation_ts"] = activation_ts
        if self.portfolio_start_ts is None or activation_ts < self.portfolio_start_ts:
            self.portfolio_start_ts = activation_ts

        state["dynamic_added"] = bool(self.portfolio_start_ts is not None and activation_ts > self.portfolio_start_ts)
        self.symbol_activation_rows.append(
            {
                "symbol": str(state["symbol"]),
                "activation_ts": activation_ts,
                "dynamic_added": bool(state["dynamic_added"]),
                "data_mode": str(state["data_mode"]),
            }
        )

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

    def _get_spread_bps(self, symbol: str) -> float:
        tier = classify_symbol(symbol)
        if tier == "major":
            return float(self.friction_preset.major_spread_bps)
        if tier == "meme_or_newer":
            return float(self.friction_preset.meme_alt_spread_bps)
        return float(self.friction_preset.liquid_alt_spread_bps)

    def _get_entry_slippage_bps(self, symbol: str) -> float:
        tier = classify_symbol(symbol)
        if tier == "major":
            return float(self.friction_preset.major_entry_slippage_bps)
        if tier == "meme_or_newer":
            return float(self.friction_preset.meme_alt_entry_slippage_bps)
        return float(self.friction_preset.liquid_alt_entry_slippage_bps)

    def _compute_extra_latency_bars(self, symbol: str, pair_id: str, side: str, scheduled_from: pd.Timestamp) -> int:
        if stable_roll(
            float(self.friction_preset.extra_latency_two_rate),
            symbol,
            pair_id,
            side,
            timestamp_key(scheduled_from),
            "latency_two",
            self.friction_preset.name,
        ):
            return 2
        if stable_roll(
            float(self.friction_preset.extra_latency_one_rate),
            symbol,
            pair_id,
            side,
            timestamp_key(scheduled_from),
            "latency_one",
            self.friction_preset.name,
        ):
            return 1
        return 0

    def _preview_entry_execution(
        self,
        symbol: str,
        side: str,
        ref_price: float,
    ) -> Dict[str, float]:
        spread_bps = self._get_spread_bps(symbol)
        entry_slip_bps = self._get_entry_slippage_bps(symbol)

        half_spread = bps_to_decimal(spread_bps / 2.0)
        entry_slip = bps_to_decimal(entry_slip_bps)
        if side == "long":
            fill_price = ref_price * (1.0 + half_spread + entry_slip)
        else:
            fill_price = ref_price * (1.0 - half_spread - entry_slip)

        return {
            "ref_price": float(ref_price),
            "fill_price": float(fill_price),
            "half_spread": float(half_spread),
            "entry_slip": float(entry_slip),
            "spread_cost_per_unit": float(ref_price * half_spread),
            "slippage_cost_per_unit": float(ref_price * entry_slip),
            "fee_rate": bps_to_decimal(self.friction_preset.fee_bps),
        }

    def _preview_exit_execution(
        self,
        symbol: str,
        side: str,
        ref_price: float,
        reason: str,
    ) -> Dict[str, float]:
        spread_bps = self._get_spread_bps(symbol)
        base_slippage_bps = self._get_entry_slippage_bps(symbol)
        if reason in {"stop_loss", "account_breach_liquidation", "final_bar_close"}:
            exit_slippage_bps = base_slippage_bps * float(self.friction_preset.stop_slippage_multiplier)
        else:
            exit_slippage_bps = base_slippage_bps

        half_spread = bps_to_decimal(spread_bps / 2.0)
        exit_slip = bps_to_decimal(exit_slippage_bps)
        if side == "long":
            fill_price = ref_price * (1.0 - half_spread - exit_slip)
        else:
            fill_price = ref_price * (1.0 + half_spread + exit_slip)

        return {
            "ref_price": float(ref_price),
            "fill_price": float(fill_price),
            "half_spread": float(half_spread),
            "exit_slip": float(exit_slip),
            "spread_cost_per_unit": float(ref_price * half_spread),
            "slippage_cost_per_unit": float(ref_price * exit_slip),
            "fee_rate": bps_to_decimal(self.friction_preset.fee_bps),
        }

    def _estimate_all_in_risk(
        self,
        symbol: str,
        pair_id: str,
        side: str,
        scheduled_from: pd.Timestamp,
        entry_ref_price: float,
        atr_value: float,
    ) -> Dict[str, float]:
        entry_execution = self._preview_entry_execution(symbol=symbol, side=side, ref_price=entry_ref_price)
        entry_fill_price = float(entry_execution["fill_price"])
        stop_distance = float(atr_value) * STOP_LOSS_ATR_MULTIPLIER
        if side == "long":
            stop_ref_price = entry_fill_price - stop_distance
        else:
            stop_ref_price = entry_fill_price + stop_distance

        stop_execution = self._preview_exit_execution(symbol=symbol, side=side, ref_price=stop_ref_price, reason="stop_loss")
        stop_fill_price = float(stop_execution["fill_price"])
        entry_fee_per_unit = entry_fill_price * float(entry_execution["fee_rate"])
        stop_fee_per_unit = stop_fill_price * float(stop_execution["fee_rate"])
        if side == "long":
            price_loss_per_unit = entry_fill_price - stop_fill_price
        else:
            price_loss_per_unit = stop_fill_price - entry_fill_price

        all_in_risk_per_unit = price_loss_per_unit + entry_fee_per_unit + stop_fee_per_unit
        return {
            "entry_fill_price": entry_fill_price,
            "entry_fee_rate": float(entry_execution["fee_rate"]),
            "stop_distance": float(stop_distance),
            "stop_ref_price": float(stop_ref_price),
            "stop_fill_price": float(stop_fill_price),
            "all_in_risk_per_unit": float(all_in_risk_per_unit),
            "entry_spread_cost_per_unit": float(entry_execution["spread_cost_per_unit"]),
            "entry_slippage_cost_per_unit": float(entry_execution["slippage_cost_per_unit"]),
        }

    def _symbol_open_side(self, state: Dict[str, object]) -> Optional[str]:
        sides = {str(position["side"]) for position in state["positions"].values()}
        if not sides:
            return None
        if len(sides) == 1:
            return next(iter(sides))
        return "conflict"

    def _symbol_pending_sides(self, state: Dict[str, object]) -> List[str]:
        return sorted({str(pending["side"]) for pending in state["pending_entries"].values()})

    def _signal_sort_key(self, row: Dict[str, object]) -> Tuple[object, ...]:
        return (
            int(row["shortlist_priority"]),
            -float(row["pair_expectancy"]),
            str(row["pair_id"]),
        )

    def _collect_symbol_signal_candidates(self, state: Dict[str, object]) -> List[Dict[str, object]]:
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
                        "pair_id": str(pair_id),
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
                        "pair_id": str(pair_id),
                        "side": "short",
                        "atr": float(short_payload["atr"]),
                        "signal_close": float(short_payload["signal_close"]),
                        "shortlist_priority": int(pair_meta["shortlist_priority"]),
                        "pair_expectancy": float(pair_meta["expectancy"]),
                        "pair_composite_score": float(pair_meta["composite_score"]),
                    }
                )

        if long_candidates and short_candidates:
            self.same_symbol_opposite_conflicts += int(len(long_candidates) + len(short_candidates))
            return []

        chosen_side = long_candidates or short_candidates
        if not chosen_side:
            return []
        return sorted(chosen_side, key=self._signal_sort_key)

    def _schedule_entries_if_needed(self, state: Dict[str, object]) -> None:
        if self.account_locked:
            return
        if not self._symbol_ready(state):
            return

        signal_candidates = self._collect_symbol_signal_candidates(state)
        if not signal_candidates:
            return

        signal_timestamp = pd.Timestamp(bt.num2date(state["signal_data"].datetime[0]))
        current_exec_len = len(state["exec_data"])
        open_side = self._symbol_open_side(state)
        pending_sides = self._symbol_pending_sides(state)

        for candidate in signal_candidates:
            pair_id = str(candidate["pair_id"])
            side = str(candidate["side"])

            if pair_id in state["positions"] or pair_id in state["pending_entries"]:
                self.same_pair_duplicate_blocks += 1
                continue

            if open_side not in {None, side} and open_side != "conflict":
                self.same_symbol_opposite_conflicts += 1
                continue
            if any(pending_side != side for pending_side in pending_sides):
                self.same_symbol_opposite_conflicts += 1
                continue

            extra_latency_bars = self._compute_extra_latency_bars(
                symbol=str(state["symbol"]),
                pair_id=pair_id,
                side=side,
                scheduled_from=signal_timestamp,
            )
            if extra_latency_bars > 0:
                self.extra_latency_events += 1

            state["pending_entries"][pair_id] = {
                "pair_id": pair_id,
                "side": side,
                "atr": float(candidate["atr"]),
                "signal_close": float(candidate["signal_close"]),
                "scheduled_from": signal_timestamp,
                "target_exec_len": int(current_exec_len + 1 + extra_latency_bars),
                "latency_bars": int(extra_latency_bars),
                "shortlist_priority": int(candidate["shortlist_priority"]),
                "pair_expectancy": float(candidate["pair_expectancy"]),
                "pair_composite_score": float(candidate["pair_composite_score"]),
            }
            pending_sides.append(side)

    def _log_rejected_entry(
        self,
        state: Dict[str, object],
        pending: Dict[str, object],
        entry_ref_price: float,
        reason: str,
    ) -> None:
        self.trade_events.append(
            {
                "trade_id": None,
                "event_kind": "entry_rejected",
                "source_pair_id": str(pending["pair_id"]),
                "support_pair_ids": str(pending["pair_id"]),
                "support_pair_count": 1,
                "support_pair_expectancy_mean": float(pending["pair_expectancy"]),
                "side": str(pending["side"]),
                "symbol": str(state["symbol"]),
                "signal_dt": pd.Timestamp(pending["scheduled_from"]),
                "entry_dt": pd.Timestamp(bt.num2date(state["exec_data"].datetime[0])),
                "exit_dt": pd.NaT,
                "entry_ref_price": float(entry_ref_price),
                "entry_fill_price": float("nan"),
                "exit_ref_price": float("nan"),
                "exit_fill_price": float("nan"),
                "size": 0.0,
                "gross_price_pnl": 0.0,
                "entry_fee_allocated": 0.0,
                "exit_fee": 0.0,
                "spread_cost": 0.0,
                "slippage_cost": 0.0,
                "pnl": 0.0,
                "reason": reason,
                "latency_bars": int(pending["latency_bars"]),
                "partial_fill_ratio": float("nan"),
                "rejected_entry_flag": True,
                "friction_preset": str(self.friction_preset.name),
            }
        )

    def _try_open_pending_entry(self, state: Dict[str, object], pair_id: str) -> None:
        pending = state["pending_entries"].pop(pair_id, None)
        if not pending:
            return
        if self.account_locked:
            return
        if not self._symbol_ready(state):
            return
        if self._active_positions() >= MAX_CONCURRENT_TRADES:
            return

        open_side = self._symbol_open_side(state)
        if pair_id in state["positions"]:
            self.same_pair_duplicate_blocks += 1
            return
        if open_side not in {None, str(pending["side"])} and open_side != "conflict":
            self.same_symbol_opposite_conflicts += 1
            return

        entry_ref_price = float(state["exec_data"].open[0])
        atr_value = float(pending["atr"])
        if entry_ref_price <= 0.0 or atr_value <= 0.0:
            return

        if stable_roll(
            float(self.friction_preset.rejection_rate),
            str(state["symbol"]),
            str(pair_id),
            str(pending["side"]),
            timestamp_key(pending["scheduled_from"]),
            "entry_reject",
            self.friction_preset.name,
        ):
            self.entry_rejections += 1
            self._log_rejected_entry(state=state, pending=pending, entry_ref_price=entry_ref_price, reason="entry_rejected")
            return

        risk_preview = self._estimate_all_in_risk(
            symbol=str(state["symbol"]),
            pair_id=str(pair_id),
            side=str(pending["side"]),
            scheduled_from=pd.Timestamp(pending["scheduled_from"]),
            entry_ref_price=entry_ref_price,
            atr_value=atr_value,
        )
        all_in_risk_per_unit = float(risk_preview["all_in_risk_per_unit"])
        entry_fill_price = float(risk_preview["entry_fill_price"])
        if all_in_risk_per_unit <= 0.0 or entry_fill_price <= 0.0:
            return

        current_equity = self._portfolio_equity(mark="close")
        max_notional = max(0.0, current_equity * MAX_CRYPTO_LEVERAGE)
        available_notional = max(0.0, max_notional - self._open_notional(mark="close"))

        raw_size = RISK_PER_TRADE_USD / all_in_risk_per_unit
        leverage_capped_size = available_notional / entry_fill_price if entry_fill_price > 0.0 else 0.0
        size = min(raw_size, leverage_capped_size)
        if size <= 0.0:
            return

        partial_fill_ratio = 1.0
        if stable_roll(
            float(self.friction_preset.partial_fill_rate),
            str(state["symbol"]),
            str(pair_id),
            str(pending["side"]),
            timestamp_key(pending["scheduled_from"]),
            "partial_fill",
            self.friction_preset.name,
        ):
            partial_fill_ratio = stable_uniform(
                float(self.friction_preset.partial_fill_min_ratio),
                float(self.friction_preset.partial_fill_max_ratio),
                str(state["symbol"]),
                str(pair_id),
                str(pending["side"]),
                timestamp_key(pending["scheduled_from"]),
                "partial_fill_ratio",
                self.friction_preset.name,
            )
            self.partial_fill_events += 1

        size = float(size * partial_fill_ratio)
        if size <= 0.0:
            return

        self.trade_counter += 1
        side = str(pending["side"])
        stop_distance = float(risk_preview["stop_distance"])
        stop_ref_price = float(risk_preview["stop_ref_price"])
        stop_fill_price = float(risk_preview["stop_fill_price"])
        entry_fee_total = float(entry_fill_price * size * risk_preview["entry_fee_rate"])
        entry_spread_cost_total = float(risk_preview["entry_spread_cost_per_unit"] * size)
        entry_slippage_cost_total = float(risk_preview["entry_slippage_cost_per_unit"] * size)
        self.sim_cash -= entry_fee_total

        if self._symbol_open_side(state) == side:
            self.stacked_same_side_entries += 1

        position = {
            "trade_id": int(self.trade_counter),
            "source_pair_id": str(pair_id),
            "support_pair_ids": [str(pair_id)],
            "support_pair_count": 1,
            "support_pair_expectancy_mean": float(pending["pair_expectancy"]),
            "shortlist_priority": int(pending["shortlist_priority"]),
            "side": side,
            "symbol": str(state["symbol"]),
            "signal_dt": pd.Timestamp(pending["scheduled_from"]),
            "entry_dt": pd.Timestamp(bt.num2date(state["exec_data"].datetime[0])),
            "entry_ref_price": float(entry_ref_price),
            "entry_fill_price": float(entry_fill_price),
            "remaining_size": float(size),
            "initial_size": float(size),
            "tp1_done": False,
            "initial_stop_distance": float(stop_distance),
            "initial_atr": float(atr_value),
            "entry_fee_total": float(entry_fee_total),
            "entry_spread_cost_total": float(entry_spread_cost_total),
            "entry_slippage_cost_total": float(entry_slippage_cost_total),
            "exit_fee_total": 0.0,
            "spread_cost_total": float(entry_spread_cost_total),
            "slippage_cost_total": float(entry_slippage_cost_total),
            "gross_price_pnl": 0.0,
            "realized_pnl": 0.0,
            "fragment_count": 0,
            "partial_fill_ratio": float(partial_fill_ratio),
            "latency_bars": int(pending["latency_bars"]),
            "friction_preset": str(self.friction_preset.name),
            "final_exit_ref_price": float("nan"),
            "final_exit_fill_price": float("nan"),
            "final_reason": "",
            "stop_price": float(stop_ref_price),
            "initial_stop_price": float(stop_ref_price),
            "stop_fill_price_preview": float(stop_fill_price),
        }

        if side == "long":
            position["tp1_price"] = float(entry_fill_price + (atr_value * TP1_ATR_MULTIPLIER))
            position["tp2_price"] = float(entry_fill_price + (atr_value * TP2_ATR_MULTIPLIER))
        else:
            position["tp1_price"] = float(entry_fill_price - (atr_value * TP1_ATR_MULTIPLIER))
            position["tp2_price"] = float(entry_fill_price - (atr_value * TP2_ATR_MULTIPLIER))

        state["positions"][pair_id] = position
        self.max_positions_seen = max(self.max_positions_seen, self._active_positions())

        self.trade_events.append(
            {
                "trade_id": int(position["trade_id"]),
                "event_kind": "entry_filled",
                "source_pair_id": str(pair_id),
                "support_pair_ids": str(pair_id),
                "support_pair_count": 1,
                "support_pair_expectancy_mean": float(pending["pair_expectancy"]),
                "side": side,
                "symbol": str(state["symbol"]),
                "signal_dt": pd.Timestamp(pending["scheduled_from"]),
                "entry_dt": pd.Timestamp(position["entry_dt"]),
                "exit_dt": pd.NaT,
                "entry_ref_price": float(entry_ref_price),
                "entry_fill_price": float(entry_fill_price),
                "exit_ref_price": float("nan"),
                "exit_fill_price": float("nan"),
                "size": float(size),
                "gross_price_pnl": 0.0,
                "entry_fee_allocated": float(entry_fee_total),
                "exit_fee": 0.0,
                "spread_cost": float(entry_spread_cost_total),
                "slippage_cost": float(entry_slippage_cost_total),
                "pnl": float(-entry_fee_total),
                "reason": "entry_filled",
                "latency_bars": int(pending["latency_bars"]),
                "partial_fill_ratio": float(partial_fill_ratio),
                "rejected_entry_flag": False,
                "friction_preset": str(self.friction_preset.name),
            }
        )

    def _close_fragment(
        self,
        state: Dict[str, object],
        pair_id: str,
        size_to_close: float,
        exit_ref_price: float,
        reason: str,
        force_close: bool = False,
    ) -> None:
        position = state["positions"].get(pair_id)
        if not position or size_to_close <= 0.0:
            return

        side = str(position["side"])
        size_to_close = min(size_to_close, float(position["remaining_size"]))
        exit_execution = self._preview_exit_execution(
            symbol=str(state["symbol"]),
            side=side,
            ref_price=float(exit_ref_price),
            reason=reason,
        )
        exit_fill_price = float(exit_execution["fill_price"])
        entry_fill_price = float(position["entry_fill_price"])
        if side == "long":
            gross_price_pnl = (exit_fill_price - entry_fill_price) * size_to_close
        else:
            gross_price_pnl = (entry_fill_price - exit_fill_price) * size_to_close

        exit_fee = float(exit_fill_price * size_to_close * exit_execution["fee_rate"])
        entry_fee_alloc = float(position["entry_fee_total"]) * (size_to_close / float(position["initial_size"]))
        spread_cost = float(exit_execution["spread_cost_per_unit"] * size_to_close)
        slippage_cost = float(exit_execution["slippage_cost_per_unit"] * size_to_close)
        net_fragment_pnl = float(gross_price_pnl - exit_fee - entry_fee_alloc)

        self.sim_cash += float(gross_price_pnl - exit_fee)
        self.side_total_profit[side] += net_fragment_pnl
        self.side_fragment_counts[side] += 1

        position["remaining_size"] = float(position["remaining_size"]) - size_to_close
        position["gross_price_pnl"] = float(position["gross_price_pnl"]) + float(gross_price_pnl)
        position["realized_pnl"] = float(position["realized_pnl"]) + net_fragment_pnl
        position["exit_fee_total"] = float(position["exit_fee_total"]) + exit_fee
        position["spread_cost_total"] = float(position["spread_cost_total"]) + spread_cost
        position["slippage_cost_total"] = float(position["slippage_cost_total"]) + slippage_cost
        position["fragment_count"] = int(position["fragment_count"]) + 1
        position["final_exit_ref_price"] = float(exit_ref_price)
        position["final_exit_fill_price"] = float(exit_fill_price)
        position["final_reason"] = str(reason)

        self.trade_events.append(
            {
                "trade_id": int(position["trade_id"]),
                "event_kind": "exit_fragment",
                "source_pair_id": str(position["source_pair_id"]),
                "support_pair_ids": "|".join(position["support_pair_ids"]),
                "support_pair_count": int(position["support_pair_count"]),
                "support_pair_expectancy_mean": float(position["support_pair_expectancy_mean"]),
                "side": side,
                "symbol": str(state["symbol"]),
                "signal_dt": pd.Timestamp(position["signal_dt"]),
                "entry_dt": pd.Timestamp(position["entry_dt"]),
                "exit_dt": pd.Timestamp(bt.num2date(state["exec_data"].datetime[0])),
                "entry_ref_price": float(position["entry_ref_price"]),
                "entry_fill_price": float(position["entry_fill_price"]),
                "exit_ref_price": float(exit_ref_price),
                "exit_fill_price": float(exit_fill_price),
                "size": float(size_to_close),
                "gross_price_pnl": float(gross_price_pnl),
                "entry_fee_allocated": float(entry_fee_alloc),
                "exit_fee": float(exit_fee),
                "spread_cost": float(spread_cost),
                "slippage_cost": float(slippage_cost),
                "pnl": float(net_fragment_pnl),
                "reason": str(reason),
                "latency_bars": int(position["latency_bars"]),
                "partial_fill_ratio": float(position["partial_fill_ratio"]),
                "rejected_entry_flag": False,
                "friction_preset": str(position["friction_preset"]),
            }
        )

        if force_close or float(position["remaining_size"]) <= 1e-12:
            exit_dt = pd.Timestamp(bt.num2date(state["exec_data"].datetime[0]))
            holding_days = (exit_dt - pd.Timestamp(position["entry_dt"])).total_seconds() / 86400.0
            self.closed_positions_log.append(
                {
                    "trade_id": int(position["trade_id"]),
                    "source_pair_id": str(position["source_pair_id"]),
                    "support_pair_ids": "|".join(position["support_pair_ids"]),
                    "support_pair_count": int(position["support_pair_count"]),
                    "support_pair_expectancy_mean": float(position["support_pair_expectancy_mean"]),
                    "side": side,
                    "symbol": str(state["symbol"]),
                    "signal_dt": pd.Timestamp(position["signal_dt"]),
                    "entry_dt": pd.Timestamp(position["entry_dt"]),
                    "exit_dt": exit_dt,
                    "entry_ref_price": float(position["entry_ref_price"]),
                    "entry_fill_price": float(position["entry_fill_price"]),
                    "exit_ref_price": float(position["final_exit_ref_price"]),
                    "exit_fill_price": float(position["final_exit_fill_price"]),
                    "initial_size": float(position["initial_size"]),
                    "initial_atr": float(position["initial_atr"]),
                    "initial_stop_price": float(position["initial_stop_price"]),
                    "tp1_price": float(position["tp1_price"]),
                    "tp2_price": float(position["tp2_price"]),
                    "gross_price_pnl": float(position["gross_price_pnl"]),
                    "fee_paid_entry": float(position["entry_fee_total"]),
                    "fee_paid_exit": float(position["exit_fee_total"]),
                    "spread_cost": float(position["spread_cost_total"]),
                    "slippage_cost": float(position["slippage_cost_total"]),
                    "realized_pnl": float(position["realized_pnl"]),
                    "fragment_count": int(position["fragment_count"]),
                    "holding_days": float(holding_days),
                    "final_reason": str(position["final_reason"]),
                    "winning_position": bool(float(position["realized_pnl"]) > 0.0),
                    "partial_fill_ratio": float(position["partial_fill_ratio"]),
                    "latency_bars": int(position["latency_bars"]),
                    "rejected_entry_flag": False,
                    "friction_preset": str(position["friction_preset"]),
                }
            )
            del state["positions"][pair_id]
            self.closed_positions += 1
            self.side_closed_positions[side] += 1

    def _manage_long_position(self, state: Dict[str, object], pair_id: str) -> None:
        position = state["positions"].get(pair_id)
        if not position:
            return

        bar_high = float(state["exec_data"].high[0])
        bar_low = float(state["exec_data"].low[0])
        stop_price = float(position["stop_price"])
        tp1_price = float(position["tp1_price"])
        tp2_price = float(position["tp2_price"])
        remaining_size = float(position["remaining_size"])

        if bar_low <= stop_price:
            self._close_fragment(state, pair_id, remaining_size, stop_price, reason="stop_loss")
            return

        if (not position["tp1_done"]) and bar_high >= tp2_price:
            half_size = remaining_size * 0.5
            self._close_fragment(state, pair_id, half_size, tp1_price, reason="tp1_scale_out")
            position = state["positions"].get(pair_id)
            if position is not None:
                position["tp1_done"] = True
                position["stop_price"] = float(position["entry_fill_price"])
                self._close_fragment(state, pair_id, float(position["remaining_size"]), tp2_price, reason="tp2_final")
            return

        if (not position["tp1_done"]) and bar_high >= tp1_price:
            half_size = remaining_size * 0.5
            self._close_fragment(state, pair_id, half_size, tp1_price, reason="tp1_scale_out")
            position = state["positions"].get(pair_id)
            if position is not None:
                position["tp1_done"] = True
                position["stop_price"] = float(position["entry_fill_price"])
            return

        position = state["positions"].get(pair_id)
        if position is not None and bool(position["tp1_done"]) and bar_high >= tp2_price:
            self._close_fragment(state, pair_id, float(position["remaining_size"]), tp2_price, reason="tp2_final")

    def _manage_short_position(self, state: Dict[str, object], pair_id: str) -> None:
        position = state["positions"].get(pair_id)
        if not position:
            return

        bar_high = float(state["exec_data"].high[0])
        bar_low = float(state["exec_data"].low[0])
        stop_price = float(position["stop_price"])
        tp1_price = float(position["tp1_price"])
        tp2_price = float(position["tp2_price"])
        remaining_size = float(position["remaining_size"])

        if bar_high >= stop_price:
            self._close_fragment(state, pair_id, remaining_size, stop_price, reason="stop_loss")
            return

        if (not position["tp1_done"]) and bar_low <= tp2_price:
            half_size = remaining_size * 0.5
            self._close_fragment(state, pair_id, half_size, tp1_price, reason="tp1_scale_out")
            position = state["positions"].get(pair_id)
            if position is not None:
                position["tp1_done"] = True
                position["stop_price"] = float(position["entry_fill_price"])
                self._close_fragment(state, pair_id, float(position["remaining_size"]), tp2_price, reason="tp2_final")
            return

        if (not position["tp1_done"]) and bar_low <= tp1_price:
            half_size = remaining_size * 0.5
            self._close_fragment(state, pair_id, half_size, tp1_price, reason="tp1_scale_out")
            position = state["positions"].get(pair_id)
            if position is not None:
                position["tp1_done"] = True
                position["stop_price"] = float(position["entry_fill_price"])
            return

        position = state["positions"].get(pair_id)
        if position is not None and bool(position["tp1_done"]) and bar_low <= tp2_price:
            self._close_fragment(state, pair_id, float(position["remaining_size"]), tp2_price, reason="tp2_final")

    def _manage_open_positions(self) -> None:
        open_snapshot = [(state, str(pair_id)) for state, pair_id, _ in self._iter_open_positions()]
        for state, pair_id in open_snapshot:
            position = state["positions"].get(pair_id)
            if not position:
                continue
            if str(position["side"]) == "long":
                self._manage_long_position(state, pair_id)
            else:
                self._manage_short_position(state, pair_id)

    def _force_liquidate_all(self, reason: str) -> None:
        open_snapshot = [(state, str(pair_id), float(position["remaining_size"])) for state, pair_id, position in self._iter_open_positions()]
        for state, pair_id, remaining_size in open_snapshot:
            self._close_fragment(state, pair_id, remaining_size, float(state["exec_data"].close[0]), reason, force_close=True)
        for state in self.asset_states.values():
            state["pending_entries"] = {}

    def _record_equity_snapshot(self) -> None:
        if self.portfolio_start_ts is None:
            return
        timestamp = pd.Timestamp(bt.num2date(self.datetime[0]))
        if timestamp < self.portfolio_start_ts:
            return
        self.equity_timeline.append(
            {
                "timestamp": timestamp,
                "equity": float(self._portfolio_equity(mark="close")),
                "cash": float(self.sim_cash),
                "open_positions": int(self._active_positions()),
                "friction_preset": str(self.friction_preset.name),
            }
        )

    def _process(self) -> None:
        for state in self.asset_states.values():
            self._refresh_symbol_activation(state)

        any_exec_advanced = False
        ready_entry_attempts: List[Tuple[Dict[str, object], str, Dict[str, object]]] = []
        for state in self.asset_states.values():
            exec_len = len(state["exec_data"])
            if exec_len != state["last_exec_len"]:
                state["last_exec_len"] = exec_len
                any_exec_advanced = True
                for pair_id, pending in list(state["pending_entries"].items()):
                    if exec_len >= int(pending["target_exec_len"]):
                        ready_entry_attempts.append((state, str(pair_id), dict(pending)))

        if ready_entry_attempts:
            ready_entry_attempts = sorted(
                ready_entry_attempts,
                key=lambda item: (
                    pd.Timestamp(item[2]["scheduled_from"]),
                    int(item[2]["shortlist_priority"]),
                    -float(item[2]["pair_expectancy"]),
                    str(item[0]["symbol"]),
                    str(item[1]),
                ),
            )
            for state, pair_id, _ in ready_entry_attempts:
                self._try_open_pending_entry(state, pair_id)

        if any_exec_advanced:
            self._update_drawdown_state()
            if self.account_locked:
                self._force_liquidate_all(reason="account_breach_liquidation")
            else:
                self._manage_open_positions()
            self._record_equity_snapshot()

        for state in self.asset_states.values():
            signal_len = len(state["signal_data"])
            if signal_len != state["last_signal_len"]:
                state["last_signal_len"] = signal_len
                self._schedule_entries_if_needed(state)

    def prenext(self) -> None:
        self._process()

    def nextstart(self) -> None:
        self._process()

    def next(self) -> None:
        self._process()

    def stop(self) -> None:
        self._force_liquidate_all(reason="final_bar_close")
        self._record_equity_snapshot()

    def build_metrics(self) -> Dict[str, float]:
        exit_fragments = [
            event
            for event in self.trade_events
            if str(event.get("event_kind", "")) == "exit_fragment"
        ]
        positive_fragments = [float(event["pnl"]) for event in exit_fragments if float(event["pnl"]) > 0.0]
        total_trades = int(len(exit_fragments))
        total_profit = float(self.sim_cash - INITIAL_BALANCE)
        winning_trades = int(sum(1 for event in exit_fragments if float(event["pnl"]) > 0.0))
        win_rate = (winning_trades / total_trades) if total_trades > 0 else 0.0
        expectancy = (total_profit / total_trades) if total_trades > 0 else 0.0
        total_return = (total_profit / INITIAL_BALANCE) if INITIAL_BALANCE > 0 else 0.0

        if total_profit > 0.0 and positive_fragments:
            consistency_score = (max(positive_fragments) / total_profit) * 100.0
        else:
            consistency_score = 999.0

        overall_survival = bool((not self.breached) and (consistency_score <= CONSISTENCY_LIMIT_PCT) and (total_profit > 0.0))
        return {
            "friction_preset": str(self.friction_preset.name),
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
            "same_symbol_opposite_conflicts": int(self.same_symbol_opposite_conflicts),
            "same_pair_duplicate_blocks": int(self.same_pair_duplicate_blocks),
            "stacked_same_side_entries": int(self.stacked_same_side_entries),
            "internal_pair_conflicts": int(self.internal_pair_conflicts),
            "entry_rejections": int(self.entry_rejections),
            "partial_fill_events": int(self.partial_fill_events),
            "extra_latency_events": int(self.extra_latency_events),
            "long_total_trades": int(self.side_fragment_counts["long"]),
            "short_total_trades": int(self.side_fragment_counts["short"]),
            "long_closed_positions": int(self.side_closed_positions["long"]),
            "short_closed_positions": int(self.side_closed_positions["short"]),
            "long_total_profit": float(self.side_total_profit["long"]),
            "short_total_profit": float(self.side_total_profit["short"]),
        }


def safe_timestamp(value: object) -> pd.Timestamp:
    """Convert a scalar into pandas Timestamp while preserving missing values."""
    if value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value):
        return pd.NaT
    return pd.Timestamp(value)


def run_final_portfolio_full(
    final_pairs: List[CombinedCandidateConfig],
    pair_rows_df: pd.DataFrame,
    catalog: MarketDataCatalog,
    friction_preset: ExecutionFrictionPreset,
) -> Tuple[Dict[str, object], pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run one full portfolio scenario inside a fresh Cerebro instance."""
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(INITIAL_BALANCE)

    feed_map = catalog.add_candidate_feeds(cerebro, prefer_intraday=True)
    pair_rows = pair_rows_df.to_dict(orient="records")

    cerebro.addstrategy(
        MavenFinalPortfolioFullStrategy,
        final_pairs=final_pairs,
        pair_rows=pair_rows,
        feed_map=feed_map,
        friction_preset=friction_preset,
    )
    results = cerebro.run(runonce=False, stdstats=False, quicknotify=False)
    strategy: MavenFinalPortfolioFullStrategy = results[0]

    metrics = strategy.build_metrics()
    trades_df = pd.DataFrame(strategy.trade_events)
    positions_df = pd.DataFrame(strategy.closed_positions_log)
    equity_df = pd.DataFrame(strategy.equity_timeline)
    activation_df = pd.DataFrame(strategy.symbol_activation_rows)
    return metrics, trades_df, positions_df, equity_df, activation_df


def build_symbol_activation_coverage(
    coverage_df: pd.DataFrame,
    activation_df: pd.DataFrame,
    portfolio_start_ts: pd.Timestamp,
) -> pd.DataFrame:
    """Merge raw data coverage with dynamic activation timestamps."""
    merged = coverage_df.copy()
    if activation_df.empty:
        merged["activation_ts"] = pd.NaT
        merged["dynamic_added"] = False
        merged["activated"] = False
        return merged

    activation_clean = activation_df.copy()
    activation_clean["activation_ts"] = pd.to_datetime(activation_clean["activation_ts"])
    activation_clean = activation_clean.sort_values(["activation_ts", "symbol"]).drop_duplicates(subset=["symbol"], keep="first")
    merged = merged.merge(
        activation_clean[["symbol", "activation_ts", "dynamic_added"]],
        on="symbol",
        how="left",
    )
    merged["activated"] = merged["activation_ts"].notna()
    merged["dynamic_added"] = merged["dynamic_added"].fillna(False).astype(bool)
    if pd.notna(portfolio_start_ts):
        merged["dynamic_added"] = merged["activation_ts"].apply(
            lambda value: bool(pd.notna(value) and pd.Timestamp(value) > pd.Timestamp(portfolio_start_ts))
        )
    return merged


def enrich_metrics(
    metrics: Dict[str, object],
    positions_df: pd.DataFrame,
    equity_df: pd.DataFrame,
    coverage_df: pd.DataFrame,
    prior_netted_results: Optional[pd.Series],
    frictionless_metrics: Optional[Dict[str, object]],
) -> Tuple[Dict[str, object], pd.DataFrame]:
    """Attach derived metrics, effective window fields, and comparison deltas."""
    effective_start = pd.NaT
    effective_end = pd.NaT
    if not equity_df.empty:
        effective_start = pd.Timestamp(pd.to_datetime(equity_df["timestamp"]).min())
        effective_end = pd.Timestamp(pd.to_datetime(equity_df["timestamp"]).max())

    enriched = dict(metrics)
    enriched["backtest_start"] = "" if pd.isna(effective_start) else effective_start.strftime("%Y-%m-%d %H:%M")
    enriched["backtest_end"] = "" if pd.isna(effective_end) else effective_end.strftime("%Y-%m-%d %H:%M")
    enriched["true_months_window"] = 0 if pd.isna(effective_start) or pd.isna(effective_end) else compute_months_covered(effective_start, effective_end)
    enriched["dynamic_symbol_count"] = int(coverage_df["dynamic_added"].sum()) if "dynamic_added" in coverage_df.columns else 0
    enriched["activated_symbol_count"] = int(coverage_df["activated"].sum()) if "activated" in coverage_df.columns else 0

    enriched, monthly_returns_df = compute_additional_metrics(enriched, positions_df, equity_df)
    enriched["stacking_profit_delta_vs_netted"] = (
        float(enriched["total_profit"]) - float(prior_netted_results.get("total_profit", 0.0))
        if prior_netted_results is not None
        else 0.0
    )
    enriched["friction_profit_delta_vs_reference"] = (
        float(enriched["total_profit"]) - float(frictionless_metrics["total_profit"])
        if frictionless_metrics is not None
        else 0.0
    )
    return enriched, monthly_returns_df


def write_scenario_outputs(
    output_prefix: str,
    metrics: Dict[str, object],
    pair_rows_df: pd.DataFrame,
    positions_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    equity_df: pd.DataFrame,
    monthly_returns_df: pd.DataFrame,
    pair_stats_df: pd.DataFrame,
    symbol_stats_df: pd.DataFrame,
    coverage_df: pd.DataFrame,
    assumptions: List[str],
    raw_start: pd.Timestamp,
    raw_end: pd.Timestamp,
    prior_netted_results: Optional[pd.Series],
    frictionless_metrics: Optional[Dict[str, object]],
) -> None:
    """Write the per-scenario companion markdown and CSV files."""
    positions_df.to_csv(f"{output_prefix}_positions.csv", index=False)
    trades_df.to_csv(f"{output_prefix}_trades.csv", index=False)
    equity_df.to_csv(f"{output_prefix}_equity_curve.csv", index=False)
    monthly_returns_df.to_csv(f"{output_prefix}_monthly_returns.csv", index=False)
    pair_stats_df.to_csv(f"{output_prefix}_pair_stats.csv", index=False)
    symbol_stats_df.to_csv(f"{output_prefix}_symbol_stats.csv", index=False)
    pd.DataFrame([metrics]).to_csv(f"{output_prefix}_results.csv", index=False)

    summary_path = f"{output_prefix}_summary.md"
    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write("# Backtrader final portfolio full summary\n\n")
        handle.write(f"- **friction_preset**: {metrics['friction_preset']}\n")
        handle.write(f"- **raw_data_start**: {raw_start.strftime('%Y-%m-%d %H:%M')}\n")
        handle.write(f"- **raw_data_end**: {raw_end.strftime('%Y-%m-%d %H:%M')}\n")
        handle.write(f"- **effective_backtest_start**: {metrics['backtest_start']}\n")
        handle.write(f"- **effective_backtest_end**: {metrics['backtest_end']}\n")
        handle.write(f"- **true_months_traded_window**: {int(metrics['true_months_window'])}\n")
        handle.write(f"- **monthly_return_observations**: {int(metrics['months_traded'])}\n")
        handle.write(f"- **dynamically_added_symbols**: {int(metrics['dynamic_symbol_count'])}\n")
        handle.write(f"- **ending_equity**: {float(metrics['ending_equity']):.2f}\n")
        handle.write(f"- **total_profit**: {float(metrics['total_profit']):.2f}\n")
        handle.write(f"- **total_return_pct**: {float(metrics['total_return']) * 100.0:.2f}\n")
        handle.write(f"- **max_dd_pct**: {float(metrics['max_dd_pct']):.2f}\n")
        handle.write(f"- **consistency_score**: {float(metrics['consistency_score']):.2f}\n")
        handle.write(f"- **overall_survival**: {bool(metrics['overall_survival'])}\n")
        handle.write(f"- **breached**: {bool(metrics['breached'])}\n")
        handle.write(f"- **same_symbol_stacking_delta_vs_netted_profit**: {float(metrics['stacking_profit_delta_vs_netted']):.2f}\n")
        handle.write(f"- **friction_delta_vs_frictionless_profit**: {float(metrics['friction_profit_delta_vs_reference']):.2f}\n")

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
                    "same_symbol_opposite_conflicts": int(metrics["same_symbol_opposite_conflicts"]),
                    "same_pair_duplicate_blocks": int(metrics["same_pair_duplicate_blocks"]),
                    "stacked_same_side_entries": int(metrics["stacked_same_side_entries"]),
                    "entry_rejections": int(metrics["entry_rejections"]),
                    "partial_fill_events": int(metrics["partial_fill_events"]),
                    "extra_latency_events": int(metrics["extra_latency_events"]),
                }
            ]
        )
        handle.write(markdown_table(metrics_frame))

        handle.write("\n## Dynamic Symbol Activation\n\n")
        activation_display = coverage_df[
            [
                "symbol",
                "chosen_exec_mode",
                "daily_start",
                "intraday_start",
                "activation_ts",
                "dynamic_added",
            ]
        ].copy()
        handle.write(markdown_table(activation_display))

        handle.write("\n## Pair Contribution\n\n")
        handle.write(markdown_table(pair_stats_df.head(10)))

        handle.write("\n## Symbol Contribution\n\n")
        handle.write(markdown_table(symbol_stats_df.head(10)))

        handle.write("\n## Monthly Returns\n\n")
        handle.write(markdown_table(monthly_returns_df.tail(18)))

        if prior_netted_results is not None:
            handle.write("\n## Prior Netted Comparison\n\n")
            prior_frame = pd.DataFrame(
                [
                    {
                        "prior_netted_total_profit": float(prior_netted_results.get("total_profit", 0.0)),
                        "current_total_profit": float(metrics["total_profit"]),
                        "stacking_profit_delta": float(metrics["stacking_profit_delta_vs_netted"]),
                    }
                ]
            )
            handle.write(markdown_table(prior_frame))

        if frictionless_metrics is not None and str(metrics["friction_preset"]) != FRICTIONLESS_PRESET_NAME:
            handle.write("\n## Frictionless Reference Comparison\n\n")
            reference_frame = pd.DataFrame(
                [
                    {
                        "frictionless_reference_profit": float(frictionless_metrics["total_profit"]),
                        "current_profit": float(metrics["total_profit"]),
                        "friction_delta": float(metrics["friction_profit_delta_vs_reference"]),
                    }
                ]
            )
            handle.write(markdown_table(reference_frame))

    top_positions = positions_df.sort_values("realized_pnl", ascending=False).head(10) if not positions_df.empty else positions_df
    worst_positions = positions_df.sort_values("realized_pnl", ascending=True).head(10) if not positions_df.empty else positions_df
    recent_trade_events = trades_df.sort_values(["entry_dt", "event_kind"], ascending=[False, True]).head(25) if not trades_df.empty else trades_df

    report_path = f"{output_prefix}_report.md"
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write("# Backtrader final portfolio full report\n\n")
        handle.write("This scenario replays the exact 5-pair deployment portfolio with dynamic symbol onboarding, pair-level slots, and deterministic execution friction.\n\n")

        handle.write("## Core Metrics\n\n")
        core_frame = pd.DataFrame(
            [
                {
                    "friction_preset": str(metrics["friction_preset"]),
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
                    "true_months_window": int(metrics["true_months_window"]),
                }
            ]
        )
        handle.write(markdown_table(core_frame))

        handle.write("\n## Coverage And Dynamic Activation\n\n")
        coverage_display = coverage_df[
            [
                "symbol",
                "daily_start",
                "daily_end",
                "intraday_start",
                "intraday_end",
                "chosen_exec_mode",
                "activation_ts",
                "dynamic_added",
            ]
        ].copy()
        handle.write(markdown_table(coverage_display))

        handle.write("\n## Pair Contribution\n\n")
        handle.write(markdown_table(pair_stats_df))

        handle.write("\n## Symbol Contribution\n\n")
        handle.write(markdown_table(symbol_stats_df))

        handle.write("\n## Monthly Returns\n\n")
        handle.write(markdown_table(monthly_returns_df))

        handle.write("\n## Top Positions\n\n")
        handle.write(markdown_table(top_positions))

        handle.write("\n## Worst Positions\n\n")
        handle.write(markdown_table(worst_positions))

        handle.write("\n## Recent Trade Events\n\n")
        handle.write(markdown_table(recent_trade_events))


def write_top_level_summary(
    summary_path: str,
    summary_df: pd.DataFrame,
    pair_rows_df: pd.DataFrame,
    assumptions: List[str],
    raw_start: pd.Timestamp,
    raw_end: pd.Timestamp,
) -> None:
    """Write the consolidated baseline/stress comparison summary."""
    compare_cols = [
        "friction_preset",
        "backtest_start",
        "backtest_end",
        "true_months_window",
        "ending_equity",
        "total_profit",
        "total_return",
        "max_dd_pct",
        "consistency_score",
        "overall_survival",
        "stacked_same_side_entries",
        "entry_rejections",
        "partial_fill_events",
        "extra_latency_events",
    ]
    compare_frame = summary_df[compare_cols].copy() if not summary_df.empty else pd.DataFrame(columns=compare_cols)
    if not compare_frame.empty:
        compare_frame["total_return_pct"] = compare_frame["total_return"] * 100.0
        compare_frame = compare_frame.drop(columns=["total_return"])

    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write("# Backtrader final portfolio full summary\n\n")
        handle.write(f"- **raw_data_start**: {raw_start.strftime('%Y-%m-%d %H:%M')}\n")
        handle.write(f"- **raw_data_end**: {raw_end.strftime('%Y-%m-%d %H:%M')}\n")
        handle.write(f"- **official_reference_preset**: {OFFICIAL_REFERENCE_PRESET}\n")
        handle.write("- **dynamic_symbol_onboarding**: enabled\n")
        handle.write("- **pair_level_same_symbol_stacking**: enabled\n")
        handle.write("- **protective_exit_rejections**: disabled\n")

        handle.write("\n## Execution Assumptions\n\n")
        for assumption in assumptions:
            handle.write(f"- {assumption}\n")

        handle.write("\n## Scenario Comparison\n\n")
        handle.write(markdown_table(compare_frame))

        handle.write("\n## Final Pairs Active\n\n")
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

        baseline_row = summary_df.loc[summary_df["friction_preset"] == BASELINE_PRESET_NAME]
        stress_row = summary_df.loc[summary_df["friction_preset"] == STRESS_PRESET_NAME]
        if not baseline_row.empty and not stress_row.empty:
            baseline = baseline_row.iloc[0]
            stress = stress_row.iloc[0]
            handle.write("\n## Baseline Vs Stress\n\n")
            handle.write(
                f"Baseline total profit is `{float(baseline['total_profit']):.2f}` versus stress `{float(stress['total_profit']):.2f}`. "
                f"Baseline max drawdown is `{float(baseline['max_dd_pct']):.2f}%` versus stress `{float(stress['max_dd_pct']):.2f}%`.\n"
            )
        handle.write("\nBaseline is the official deployment-grade reference; stress is the downside robustness check.\n")


def write_top_level_report(
    report_path: str,
    summary_df: pd.DataFrame,
    combined_positions_df: pd.DataFrame,
    combined_trades_df: pd.DataFrame,
    combined_pair_stats_df: pd.DataFrame,
    combined_symbol_stats_df: pd.DataFrame,
    combined_monthly_returns_df: pd.DataFrame,
    combined_coverage_df: pd.DataFrame,
) -> None:
    """Write the consolidated multi-scenario report."""
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write("# Backtrader final portfolio full report\n\n")
        handle.write("This report consolidates the frictionless reference, baseline, and stress reruns for the exact 5-pair TRADE_ORACLE deployment portfolio.\n\n")

        handle.write("## Scenario Metrics\n\n")
        handle.write(markdown_table(summary_df))

        handle.write("\n## Coverage By Scenario\n\n")
        handle.write(markdown_table(combined_coverage_df))

        handle.write("\n## Pair Stats By Scenario\n\n")
        handle.write(markdown_table(combined_pair_stats_df))

        handle.write("\n## Symbol Stats By Scenario\n\n")
        handle.write(markdown_table(combined_symbol_stats_df))

        handle.write("\n## Monthly Returns By Scenario\n\n")
        handle.write(markdown_table(combined_monthly_returns_df))

        handle.write("\n## Top Positions Across Scenarios\n\n")
        top_positions = combined_positions_df.sort_values("realized_pnl", ascending=False).head(20) if not combined_positions_df.empty else combined_positions_df
        handle.write(markdown_table(top_positions))

        handle.write("\n## Recent Trade Events Across Scenarios\n\n")
        recent_trades = combined_trades_df.sort_values(["entry_dt", "event_kind"], ascending=[False, True]).head(30) if not combined_trades_df.empty else combined_trades_df
        handle.write(markdown_table(recent_trades))


def main() -> None:
    """Run the full near-3-year portfolio rerun under deterministic friction scenarios."""
    args = parse_args()

    final_pairs, pair_rows_df = resolve_final_pairs(
        shortlist_path=args.shortlist,
        ranking_path=args.ranking,
        top_n=args.top_n,
    )
    catalog = MarketDataCatalog(daily_path=args.daily_data, intraday_path=args.intraday_data)
    raw_start, raw_end = infer_data_window(catalog)
    raw_coverage_df = catalog.describe_symbol_coverage(prefer_intraday=True)
    prior_netted_results = load_prior_netted_results(DEFAULT_PRIOR_NETTED_RESULTS)

    requested_names = [BASELINE_PRESET_NAME, STRESS_PRESET_NAME] if args.friction_mode == "both" else [str(args.friction_mode)]
    scenario_names = [FRICTIONLESS_PRESET_NAME] + requested_names

    assumptions = [
        "Exact strategy is the locked 5-pair deployment shortlist from backtrader_combined_final_shortlist.csv.",
        "Effective portfolio start is the first timestamp where any symbol becomes trade-ready after its own warmup.",
        "Short-history symbols such as TON/USDT are added dynamically when their own data becomes ready.",
        "Same-symbol same-side signals from different shortlisted pairs may coexist as independent positions.",
        "Opposite-side self-hedging on the same symbol is blocked across the shared account.",
        "Deterministic execution frictions model fees, spread, slippage, latency, rejected entries, and partial fills.",
        "Protective exits are never rejected; only new entries can be rejected or partially filled.",
        "Risk sizing uses All-In $10: theoretical worst-case loss including fees, spread, and slippage stays at or below about $10 before leverage truncation.",
    ]

    scenario_payloads: Dict[str, Dict[str, object]] = {}
    frictionless_metrics: Optional[Dict[str, object]] = None

    for preset_name in scenario_names:
        preset = FRICTION_PRESETS[preset_name]
        metrics, trades_df, positions_df, equity_df, activation_df = run_final_portfolio_full(
            final_pairs=final_pairs,
            pair_rows_df=pair_rows_df,
            catalog=catalog,
            friction_preset=preset,
        )

        coverage_df = build_symbol_activation_coverage(
            coverage_df=raw_coverage_df,
            activation_df=activation_df,
            portfolio_start_ts=safe_timestamp(equity_df["timestamp"].min() if not equity_df.empty else pd.NaT),
        )

        pair_stats_df = build_pair_stats(positions_df, pair_rows_df)
        symbol_stats_df = build_symbol_stats(positions_df)
        if preset_name == FRICTIONLESS_PRESET_NAME:
            enriched_metrics, monthly_returns_df = enrich_metrics(
                metrics=metrics,
                positions_df=positions_df,
                equity_df=equity_df,
                coverage_df=coverage_df,
                prior_netted_results=prior_netted_results,
                frictionless_metrics=None,
            )
            frictionless_metrics = dict(enriched_metrics)
        else:
            enriched_metrics, monthly_returns_df = enrich_metrics(
                metrics=metrics,
                positions_df=positions_df,
                equity_df=equity_df,
                coverage_df=coverage_df,
                prior_netted_results=prior_netted_results,
                frictionless_metrics=frictionless_metrics,
            )

        scenario_payloads[preset_name] = {
            "metrics": enriched_metrics,
            "trades_df": trades_df,
            "positions_df": positions_df,
            "equity_df": equity_df,
            "monthly_returns_df": monthly_returns_df,
            "pair_stats_df": pair_stats_df,
            "symbol_stats_df": symbol_stats_df,
            "coverage_df": coverage_df.assign(friction_preset=preset_name),
        }

    for preset_name in requested_names:
        payload = scenario_payloads[preset_name]
        write_scenario_outputs(
            output_prefix=preset_output_prefix(args.output_prefix, preset_name),
            metrics=payload["metrics"],
            pair_rows_df=pair_rows_df,
            positions_df=payload["positions_df"],
            trades_df=payload["trades_df"],
            equity_df=payload["equity_df"],
            monthly_returns_df=payload["monthly_returns_df"],
            pair_stats_df=payload["pair_stats_df"],
            symbol_stats_df=payload["symbol_stats_df"],
            coverage_df=payload["coverage_df"],
            assumptions=assumptions,
            raw_start=raw_start,
            raw_end=raw_end,
            prior_netted_results=prior_netted_results,
            frictionless_metrics=scenario_payloads.get(FRICTIONLESS_PRESET_NAME, {}).get("metrics"),
        )

    combined_results_df = pd.DataFrame([scenario_payloads[name]["metrics"] for name in scenario_names])
    combined_positions_df = pd.concat([scenario_payloads[name]["positions_df"] for name in scenario_names], ignore_index=True)
    combined_trades_df = pd.concat([scenario_payloads[name]["trades_df"] for name in scenario_names], ignore_index=True)
    combined_equity_df = pd.concat([scenario_payloads[name]["equity_df"] for name in scenario_names], ignore_index=True)
    combined_monthly_df = pd.concat(
        [scenario_payloads[name]["monthly_returns_df"].assign(friction_preset=name) for name in scenario_names],
        ignore_index=True,
    )
    combined_pair_stats_df = pd.concat(
        [scenario_payloads[name]["pair_stats_df"].assign(friction_preset=name) for name in scenario_names],
        ignore_index=True,
    )
    combined_symbol_stats_df = pd.concat(
        [scenario_payloads[name]["symbol_stats_df"].assign(friction_preset=name) for name in scenario_names],
        ignore_index=True,
    )
    combined_coverage_df = pd.concat([scenario_payloads[name]["coverage_df"] for name in scenario_names], ignore_index=True)

    combined_results_df.to_csv(f"{args.output_prefix}_results.csv", index=False)
    combined_positions_df.to_csv(f"{args.output_prefix}_positions.csv", index=False)
    combined_trades_df.to_csv(f"{args.output_prefix}_trades.csv", index=False)
    combined_equity_df.to_csv(f"{args.output_prefix}_equity_curve.csv", index=False)
    combined_monthly_df.to_csv(f"{args.output_prefix}_monthly_returns.csv", index=False)
    combined_pair_stats_df.to_csv(f"{args.output_prefix}_pair_stats.csv", index=False)
    combined_symbol_stats_df.to_csv(f"{args.output_prefix}_symbol_stats.csv", index=False)

    summary_compare_df = combined_results_df.loc[combined_results_df["friction_preset"].isin(requested_names)].copy()
    write_top_level_summary(
        summary_path=f"{args.output_prefix}_summary.md",
        summary_df=summary_compare_df,
        pair_rows_df=pair_rows_df,
        assumptions=assumptions,
        raw_start=raw_start,
        raw_end=raw_end,
    )
    write_top_level_report(
        report_path=f"{args.output_prefix}_report.md",
        summary_df=combined_results_df,
        combined_positions_df=combined_positions_df,
        combined_trades_df=combined_trades_df,
        combined_pair_stats_df=combined_pair_stats_df,
        combined_symbol_stats_df=combined_symbol_stats_df,
        combined_monthly_returns_df=combined_monthly_df,
        combined_coverage_df=combined_coverage_df,
    )


if __name__ == "__main__":
    main()
