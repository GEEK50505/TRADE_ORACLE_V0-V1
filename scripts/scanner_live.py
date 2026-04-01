"""
Production live scanner for the final TRADE_ORACLE combined strategy set.

This scanner does not optimize anything. It only evaluates the exact final
combined pairs that survived the full Backtrader validation pipeline and checks
whether any long or short setups are valid right now on the latest available
Daily + 4H data.

Recommended usage:
    python scripts/scanner_live.py --live

Helpful dry run:
    python scripts/scanner_live.py --test
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import UTC, datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from backtrader_evaluate import (
    RISK_PER_TRADE_USD,
    STOP_LOSS_ATR_MULTIPLIER,
    TP1_ATR_MULTIPLIER,
    TP2_ATR_MULTIPLIER,
)
from backtrader_evaluate_combined import (
    ATR_PERIOD,
    DEFAULT_DAILY_PATH,
    DEFAULT_INTRADAY_PATH,
    FIB_LOOKBACK,
    CombinedCandidateConfig,
    MarketDataCatalog,
)


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

DEFAULT_FINAL_SHORTLIST = os.path.join(RESULTS_DIR, "backtrader_combined_final_shortlist.csv")
DEFAULT_SURVIVOR_RANKING = os.path.join(RESULTS_DIR, "backtrader_combined_survivor_ranking.csv")
DEFAULT_JSON_OUTPUT = os.path.join(RESULTS_DIR, "scanner_live_setups.json")


def parse_args() -> argparse.Namespace:
    """Define the CLI surface for the live scanner."""
    parser = argparse.ArgumentParser(description="TRADE_ORACLE live scanner for the final 5 combined pairs.")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--live", action="store_true", help="Run the scanner in live mode against all 5 final pairs.")
    mode_group.add_argument("--test", action="store_true", help="Run the scanner in test mode using the same local data.")
    parser.add_argument("--shortlist", default=DEFAULT_FINAL_SHORTLIST, help="Path to the combined final shortlist CSV.")
    parser.add_argument("--ranking", default=DEFAULT_SURVIVOR_RANKING, help="Path to the combined survivor ranking CSV.")
    parser.add_argument("--daily-data", default=DEFAULT_DAILY_PATH, help="Path to the daily parquet file.")
    parser.add_argument("--intraday-data", default=DEFAULT_INTRADAY_PATH, help="Path to the 4H parquet file.")
    parser.add_argument("--json-output", default=None, help="Optional path for JSON output. Example: results/scanner_live_setups.json")
    parser.add_argument("--top-n", type=int, default=5, help="How many final pairs to activate from the shortlist.")
    return parser.parse_args()


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
    """
    Resolve the compact final shortlist into the full combined candidate objects.

    The final shortlist intentionally contains only presentation-friendly columns,
    so we use the combined survivor ranking as the source of truth for the full
    long/short parameter blocks.
    """

    shortlist_df = load_csv(shortlist_path).copy()
    ranking_df = load_csv(ranking_path).copy()

    shortlist_df = shortlist_df.sort_values("shortlist_priority").head(max(1, int(top_n))).reset_index(drop=True)
    ranking_lookup = {
        str(row["param_id"]): row
        for _, row in ranking_df.iterrows()
    }

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


def rolling_mean(series: pd.Series, window: int) -> pd.Series:
    """Simple rolling mean with full-window readiness."""
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    """EMA with the same recursive shape used elsewhere in the repo."""
    return series.ewm(span=window, adjust=False).mean()


def rolling_max(series: pd.Series, window: int) -> pd.Series:
    """Rolling max with full-window readiness."""
    return series.rolling(window=window, min_periods=window).max()


def rolling_min(series: pd.Series, window: int) -> pd.Series:
    """Rolling min with full-window readiness."""
    return series.rolling(window=window, min_periods=window).min()


def true_range(frame: pd.DataFrame) -> pd.Series:
    """Build the True Range series used by the ATR calculation."""
    prev_close = frame["close"].shift(1)
    high_low = frame["high"] - frame["low"]
    high_prev = (frame["high"] - prev_close).abs()
    low_prev = (frame["low"] - prev_close).abs()
    return pd.concat([high_low, high_prev, low_prev], axis=1).max(axis=1)


def atr_wilder(frame: pd.DataFrame, period: int) -> pd.Series:
    """Wilder-smoothed ATR, matching Backtrader's ATR family closely."""
    tr = true_range(frame)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def latest_signal_snapshot(signal_frame: pd.DataFrame, side: str, cfg) -> Optional[Dict[str, object]]:
    """
    Evaluate the exact long or short signal confluence on the latest daily bar.

    This intentionally mirrors the logic in `MavenCombinedCandidateStrategy`.
    """

    min_required = max(cfg.sma, cfg.ema, FIB_LOOKBACK, cfg.rw_lookback, ATR_PERIOD) + 1
    if len(signal_frame) < min_required:
        return None

    working = signal_frame.copy()
    working["sma_calc"] = rolling_mean(working["close"], cfg.sma)
    working["ema_calc"] = ema(working["close"], cfg.ema)
    working["atr_calc"] = atr_wilder(working, ATR_PERIOD)
    working["high30_calc"] = rolling_max(working["high"], FIB_LOOKBACK)
    working["low30_calc"] = rolling_min(working["low"], FIB_LOOKBACK)
    working["prev_close_calc"] = working["close"].shift(cfg.rw_lookback)

    latest = working.iloc[-1]
    close = float(latest["close"])
    sma = float(latest["sma_calc"])
    ema_value = float(latest["ema_calc"])
    atr_value = float(latest["atr_calc"])
    high30 = float(latest["high30_calc"])
    low30 = float(latest["low30_calc"])
    prev_close = float(latest["prev_close_calc"])

    if any(math.isnan(value) for value in [close, sma, ema_value, atr_value, high30, low30, prev_close]):
        return None
    if close <= 0.0 or atr_value <= 0.0 or high30 <= low30 or prev_close <= 0.0:
        return None

    ema_distance = abs(close - ema_value) / close

    if side == "long":
        retracement = (high30 - close) / (high30 - low30)
        rw_value = (prev_close - close) / prev_close
        is_valid = (
            close > sma
            and cfg.fib_floor <= retracement <= cfg.fib_band
            and ema_distance <= cfg.eb
            and rw_value >= cfg.rw
        )
        summary = (
            f"close {close:.4f} > SMA {sma:.4f}; "
            f"retracement {retracement:.4f} in [{cfg.fib_floor:.3f}, {cfg.fib_band:.3f}]; "
            f"EMA distance {ema_distance:.4f} <= {cfg.eb:.4f}; "
            f"RW {rw_value:.4f} >= {cfg.rw:.4f}"
        )
        metric_payload = {
            "retracement": float(retracement),
            "rw_value": float(rw_value),
        }
    else:
        bounce_retracement = (close - low30) / (high30 - low30)
        downside_momentum = (prev_close - close) / prev_close
        is_valid = (
            close < sma
            and cfg.fib_floor <= bounce_retracement <= cfg.fib_band
            and ema_distance <= cfg.eb
            and downside_momentum >= cfg.rw
        )
        summary = (
            f"close {close:.4f} < SMA {sma:.4f}; "
            f"bounce retracement {bounce_retracement:.4f} in [{cfg.fib_floor:.3f}, {cfg.fib_band:.3f}]; "
            f"EMA distance {ema_distance:.4f} <= {cfg.eb:.4f}; "
            f"downside momentum {downside_momentum:.4f} >= {cfg.rw:.4f}"
        )
        metric_payload = {
            "bounce_retracement": float(bounce_retracement),
            "downside_momentum": float(downside_momentum),
        }

    if not is_valid:
        return None

    return {
        "signal_timestamp": pd.Timestamp(latest.name),
        "signal_close": close,
        "sma": sma,
        "ema_value": ema_value,
        "ema_distance": float(ema_distance),
        "atr": atr_value,
        "summary": summary,
        **metric_payload,
    }


def latest_confirmation_snapshot(exec_frame: pd.DataFrame, side: str, cfg) -> Optional[Dict[str, object]]:
    """Evaluate the exact 4H confirmation filter on the latest execution bar."""
    if len(exec_frame) < max(1, int(cfg.confirm_ema_period)):
        return None

    working = exec_frame.copy()
    working["confirm_ema_calc"] = ema(working["close"], cfg.confirm_ema_period)
    latest = working.iloc[-1]

    exec_close = float(latest["close"])
    ema_value = float(latest["confirm_ema_calc"])
    if any(math.isnan(value) for value in [exec_close, ema_value]):
        return None
    if exec_close <= 0.0 or ema_value <= 0.0:
        return None

    if side == "long":
        confirm_distance = (exec_close - ema_value) / ema_value
        is_valid = bool(exec_close > ema_value and confirm_distance >= cfg.confirm_min_distance)
        summary = (
            f"4H confirm close {exec_close:.4f} > EMA {ema_value:.4f}; "
            f"distance {confirm_distance:.4f} >= {cfg.confirm_min_distance:.4f}"
        )
    else:
        confirm_distance = (ema_value - exec_close) / ema_value
        is_valid = bool(exec_close < ema_value and confirm_distance >= cfg.confirm_min_distance)
        summary = (
            f"4H confirm close {exec_close:.4f} < EMA {ema_value:.4f}; "
            f"distance {confirm_distance:.4f} >= {cfg.confirm_min_distance:.4f}"
        )

    if not is_valid:
        return None

    return {
        "exec_timestamp": pd.Timestamp(latest.name),
        "current_price": exec_close,
        "confirm_ema": ema_value,
        "confirm_distance": float(confirm_distance),
        "summary": summary,
    }


def build_trade_levels(current_price: float, atr_value: float, side: str) -> Dict[str, float]:
    """Convert the ATR snapshot into stop/target prices for the scanner output."""
    stop_distance = atr_value * STOP_LOSS_ATR_MULTIPLIER
    if side == "long":
        return {
            "stop_price": current_price - stop_distance,
            "tp1_price": current_price + (atr_value * TP1_ATR_MULTIPLIER),
            "tp2_price": current_price + (atr_value * TP2_ATR_MULTIPLIER),
        }

    return {
        "stop_price": current_price + stop_distance,
        "tp1_price": current_price - (atr_value * TP1_ATR_MULTIPLIER),
        "tp2_price": current_price - (atr_value * TP2_ATR_MULTIPLIER),
    }


def evaluate_symbol_side(
    pair_row: pd.Series,
    symbol: str,
    side: str,
    signal_frame: pd.DataFrame,
    exec_frame: pd.DataFrame,
):
    """Evaluate one symbol for one side of one final combined pair."""
    cfg = pair_row["candidate"].long_candidate if side == "long" else pair_row["candidate"].short_candidate
    signal_snapshot = latest_signal_snapshot(signal_frame=signal_frame, side=side, cfg=cfg)
    if signal_snapshot is None:
        return None

    confirmation_snapshot = latest_confirmation_snapshot(exec_frame=exec_frame, side=side, cfg=cfg)
    if confirmation_snapshot is None:
        return None

    trade_levels = build_trade_levels(
        current_price=float(confirmation_snapshot["current_price"]),
        atr_value=float(signal_snapshot["atr"]),
        side=side,
    )

    reason = f"{signal_snapshot['summary']}; {confirmation_snapshot['summary']}"
    return {
        "pair_id": str(pair_row["param_id"]),
        "symbol": symbol,
        "side": side,
        "current_price": float(confirmation_snapshot["current_price"]),
        "signal_strength": float(pair_row["expectancy"]),
        "pair_expectancy": float(pair_row["expectancy"]),
        "pair_composite_score": float(pair_row["composite_score"]),
        "atr": float(signal_snapshot["atr"]),
        "stop_price": float(trade_levels["stop_price"]),
        "tp1_price": float(trade_levels["tp1_price"]),
        "tp2_price": float(trade_levels["tp2_price"]),
        "risk_per_trade": float(RISK_PER_TRADE_USD),
        "reason": reason,
        "signal_timestamp": signal_snapshot["signal_timestamp"].isoformat(),
        "execution_timestamp": confirmation_snapshot["exec_timestamp"].isoformat(),
        "shortlist_priority": int(pair_row["shortlist_priority"]),
        "shortlist_role": str(pair_row.get("shortlist_role", "unspecified")),
        "long_param_id": str(pair_row["long_param_id"]),
        "short_param_id": str(pair_row["short_param_id"]),
    }


def scan_live_pairs(final_pairs: List[CombinedCandidateConfig], resolved_df: pd.DataFrame, catalog: MarketDataCatalog) -> List[Dict[str, object]]:
    """Scan the latest Daily + 4H bars for all active final pairs."""
    setups: List[Dict[str, object]] = []

    for index, candidate in enumerate(final_pairs):
        pair_row = resolved_df.iloc[index].copy()
        pair_row["candidate"] = candidate

        for symbol in sorted(catalog.daily_frames.keys()):
            signal_frame = catalog.daily_frames[symbol].copy()
            exec_frame = catalog.intraday_frames.get(symbol, catalog.daily_frames[symbol]).copy()

            long_setup = evaluate_symbol_side(
                pair_row=pair_row,
                symbol=symbol,
                side="long",
                signal_frame=signal_frame,
                exec_frame=exec_frame,
            )
            short_setup = evaluate_symbol_side(
                pair_row=pair_row,
                symbol=symbol,
                side="short",
                signal_frame=signal_frame,
                exec_frame=exec_frame,
            )

            if long_setup and short_setup:
                # This mirrors the combined Backtrader rule: do not choose a side
                # heuristically when both directions trigger on the same symbol.
                continue

            if long_setup:
                setups.append(long_setup)
            elif short_setup:
                setups.append(short_setup)

    setups.sort(
        key=lambda row: (
            int(row["shortlist_priority"]),
            -float(row["signal_strength"]),
            row["symbol"],
            row["side"],
        )
    )
    return setups


def build_header(mode: str, active_pairs: int, catalog: MarketDataCatalog) -> str:
    """Build the scanner header string using the latest available execution timestamp."""
    latest_ts: Optional[pd.Timestamp] = None
    for symbol in catalog.daily_frames.keys():
        exec_frame = catalog.intraday_frames.get(symbol, catalog.daily_frames[symbol])
        current_ts = pd.Timestamp(exec_frame.index[-1])
        if latest_ts is None or current_ts > latest_ts:
            latest_ts = current_ts

    if latest_ts is None:
        latest_label = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    else:
        latest_label = latest_ts.strftime("%Y-%m-%d %H:%M")

    mode_label = "LIVE" if mode == "live" else "TEST"
    return f"TRADE_ORACLE {mode_label} SCANNER — {latest_label} — {active_pairs} final pairs active"


def print_setups_table(setups: List[Dict[str, object]]) -> None:
    """Print the active setups in a compact human-readable table."""
    if not setups:
        print("No valid setups right now.")
        return

    display_df = pd.DataFrame(setups)[
        [
            "pair_id",
            "symbol",
            "side",
            "current_price",
            "signal_strength",
            "atr",
            "stop_price",
            "tp1_price",
            "tp2_price",
            "risk_per_trade",
            "reason",
        ]
    ].copy()

    for column in [
        "current_price",
        "signal_strength",
        "atr",
        "stop_price",
        "tp1_price",
        "tp2_price",
        "risk_per_trade",
    ]:
        display_df[column] = display_df[column].map(lambda value: f"{float(value):.4f}" if column != "risk_per_trade" else f"{float(value):.2f}")

    print(display_df.to_string(index=False))


def maybe_write_json(setups: List[Dict[str, object]], output_path: Optional[str]) -> None:
    """Write optional JSON output for downstream automation or MT5 bridging."""
    if not output_path:
        return

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(setups, handle, indent=2)

    print(f"\nJSON output written to: {output_path}")


def main() -> None:
    """Main entry point used by `python scripts/scanner_live.py`."""
    args = parse_args()
    mode = "test" if args.test else "live"

    final_pairs, resolved_df = resolve_final_pairs(
        shortlist_path=args.shortlist,
        ranking_path=args.ranking,
        top_n=args.top_n,
    )

    catalog = MarketDataCatalog(daily_path=args.daily_data, intraday_path=args.intraday_data)
    header = build_header(mode=mode, active_pairs=len(final_pairs), catalog=catalog)

    print(header)
    print("-" * len(header))

    setups = scan_live_pairs(final_pairs=final_pairs, resolved_df=resolved_df, catalog=catalog)
    print(f"Valid setups found: {len(setups)}\n")
    print_setups_table(setups)

    json_output = args.json_output
    if json_output is None and mode == "live":
        json_output = DEFAULT_JSON_OUTPUT
    maybe_write_json(setups=setups, output_path=json_output)


if __name__ == "__main__":
    main()
