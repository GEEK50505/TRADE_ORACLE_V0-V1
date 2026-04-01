"""
Targeted short-side 4H confirmation sweep for the validated short survivors.

This script mirrors the structure of `vectorbt_4h_confirmation_sweep.py`, but it
uses the short-side survivor pool and a short-side 4H confirmation filter.

Why this script exists:
- The long side already passed through a Daily + 4H confirmation phase.
- The short side has only been validated on the Daily layer so far.
- This step keeps the methodology symmetric by adding the same style of targeted
  4H quality gate on top of the already-surviving short candidates.

Important implementation notes:
- The 4H layer is a confirmation filter only. It can block a Daily short entry,
  but it never creates entries on its own.
- The base parameter sets come from the short survivor ranking file rather than
  from a fresh full-grid sweep.
- By default the script uses only the top 20 short survivors. That keeps the
  combined search compact enough for a normal laptop while still covering the
  strongest short-side neighborhoods.
- When true 4H data exists for a symbol, the confirmation rule uses the latest
  same-day 4H bar.
- When 4H data is missing for a symbol in this workspace, the script falls back
  to a daily EMA proxy using the same confirmation parameters. That matches the
  mixed-feed fallback philosophy already used in the Backtrader validators.

Short confirmation rule:
- execution close must be below the 4H EMA
- the distance below that EMA must meet the configured minimum threshold

Outputs:
- results/short_4h_sweep_results.csv
- results/short_plus_4h_candidates.csv
- results/short_4h_optimization_summary.md

Recommended full run:
    python scripts/vectorbt_short_4h_confirmation_sweep.py

Helpful smaller run:
    python scripts/vectorbt_short_4h_confirmation_sweep.py --top-n-base 10
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    from config import settings
except Exception:
    settings = None


# ==============================================================================
# PATHS AND CONSTANTS
# ==============================================================================

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")
DATA_DIR = os.path.join(ROOT_DIR, "data")

DEFAULT_SURVIVOR_PATH = os.path.join(RESULTS_DIR, "backtrader_short_survivor_ranking.csv")
DEFAULT_DAILY_PATH = os.path.join(DATA_DIR, "market_data_1D.parquet")
DEFAULT_4H_PATH = os.path.join(DATA_DIR, "market_data_4H.parquet")
DEFAULT_RESULTS_CSV = os.path.join(RESULTS_DIR, "short_4h_sweep_results.csv")
DEFAULT_CANDIDATES_CSV = os.path.join(RESULTS_DIR, "short_plus_4h_candidates.csv")
DEFAULT_SUMMARY_MD = os.path.join(RESULTS_DIR, "short_4h_optimization_summary.md")

WATCHLIST = list(
    getattr(
        settings,
        "WATCHLIST",
        ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "TON/USDT", "ADA/USDT", "BNB/USDT"],
    )
)

INIT_CASH = 10_000.0
FEE = 0.0005
FIB_LOOKBACK = 30

# This is the exact targeted confirmation grid requested for the short side.
CONFIRM_EMA_PERIODS = [15, 20, 25, 30]
CONFIRM_MIN_DISTANCES = [0.0, 0.004, 0.008]


# ==============================================================================
# SMALL DATA CONTAINERS
# ==============================================================================


@dataclass(frozen=True)
class ShortSurvivor:
    """A typed view of one short survivor used as the Daily base layer."""

    analysis_rank: int
    base_rank: int
    param_id: str
    source_symbol: str
    side: str
    sma: int
    ema: int
    fib_floor: float
    fib_band: float
    rw: float
    eb: float
    rw_lookback: int

    @classmethod
    def from_row(cls, row: pd.Series) -> "ShortSurvivor":
        """Convert one ranking row into a strongly-typed short survivor object."""
        return cls(
            analysis_rank=int(row["analysis_rank"]),
            base_rank=int(row["rank"]),
            param_id=str(row["param_id"]),
            source_symbol=str(row["source_symbol"]),
            side=str(row.get("side", "short")).lower(),
            sma=int(row["sma"]),
            ema=int(row["ema"]),
            fib_floor=float(row["fib_floor"]),
            fib_band=float(row["fib_band"]),
            rw=float(row["rw"]),
            eb=float(row["eb"]),
            rw_lookback=int(row["rw_lookback"]),
        )


@dataclass(frozen=True)
class ConfirmCombo:
    """One short-side 4H confirmation parameter tuple."""

    ema_period: int
    min_distance: float

    @property
    def combo_id(self) -> str:
        """Stable identifier used in combined candidate ids."""
        return f"ema{self.ema_period}_dist{self.min_distance:.3f}"


# ==============================================================================
# SMALL HELPERS
# ==============================================================================


def ensure_results_dir() -> None:
    """Create the results folder if it does not already exist."""
    os.makedirs(RESULTS_DIR, exist_ok=True)


def rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    """Simple rolling SMA helper used to mirror the Daily discovery logic."""
    out = np.full(values.shape[0], np.nan, dtype=np.float64)
    if window <= 0 or values.size == 0 or window > values.size:
        return out
    kernel = np.ones(window, dtype=np.float64) / float(window)
    out[window - 1 :] = np.convolve(values.astype(np.float64), kernel, mode="valid")
    return out


def ema(values: np.ndarray, window: int) -> np.ndarray:
    """Simple EMA helper used in both the Daily and 4H layers."""
    out = np.full(values.shape[0], np.nan, dtype=np.float64)
    if values.size == 0:
        return out
    alpha = 2.0 / (window + 1.0)
    out[0] = values[0]
    for idx in range(1, values.shape[0]):
        out[idx] = alpha * values[idx] + (1.0 - alpha) * out[idx - 1]
    return out


def rolling_max(values: np.ndarray, window: int) -> np.ndarray:
    """Rolling maximum helper for the short bounce-zone calculation."""
    return pd.Series(values).rolling(window=window, min_periods=1).max().to_numpy(dtype=np.float64, copy=False)


def rolling_min(values: np.ndarray, window: int) -> np.ndarray:
    """Rolling minimum helper for the short bounce-zone calculation."""
    return pd.Series(values).rolling(window=window, min_periods=1).min().to_numpy(dtype=np.float64, copy=False)


def trade_pnls(close: np.ndarray, entries: np.ndarray, exits: np.ndarray) -> List[float]:
    """
    Generate the closed-trade PnL list for one symbol using short-side math.

    This keeps the 4H confirmation stage aligned with the lightweight discovery
    accounting used by the other vectorized scripts.
    """

    trade_list: List[float] = []
    in_position = False
    entry_price = 0.0

    for idx in range(close.shape[0]):
        if entries[idx] and not in_position:
            entry_price = float(close[idx])
            in_position = True

        if exits[idx] and in_position:
            exit_price = float(close[idx])
            pnl_pct = (entry_price - exit_price) / entry_price - (2.0 * FEE)
            trade_list.append(INIT_CASH * pnl_pct)
            in_position = False

    if in_position:
        exit_price = float(close[-1])
        pnl_pct = (entry_price - exit_price) / entry_price - (2.0 * FEE)
        trade_list.append(INIT_CASH * pnl_pct)

    return trade_list


def load_survivors(path: str, top_n_base: int) -> List[ShortSurvivor]:
    """
    Load the ranked short survivors and keep only the strongest base rows.

    The ranking file is already sorted by composite score, so taking the first
    N rows gives us the intended targeted base set for the 4H layer.
    """

    if not os.path.exists(path):
        raise FileNotFoundError(f"Short survivor file not found: {path}")

    df = pd.read_csv(path)
    if df.empty:
        raise ValueError("Short survivor file is empty.")

    df = df.sort_values(by=["analysis_rank"]).reset_index(drop=True)
    df = df.head(max(1, int(top_n_base))).copy()
    return [ShortSurvivor.from_row(row) for _, row in df.iterrows()]


def load_market_by_symbol(path: str) -> Dict[str, pd.DataFrame]:
    """Load one parquet file and split it into one DataFrame per symbol."""
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


# ==============================================================================
# DAILY ENTRY / EXIT LOGIC
# ==============================================================================


def build_daily_entries_exits(df_daily: pd.DataFrame, candidate: ShortSurvivor) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Recreate the exact Daily short-only signal logic from `vectorbt_short_sweep.py`.

    This ensures the 4H layer remains a true confirmation filter rather than a
    second independent short strategy.
    """

    close = df_daily["close"].to_numpy(dtype=np.float64, copy=True)
    high = df_daily["high"].to_numpy(dtype=np.float64, copy=True)
    low = df_daily["low"].to_numpy(dtype=np.float64, copy=True)

    sma_values = rolling_mean(close, candidate.sma)
    ema_values = ema(close, candidate.ema)
    high30 = rolling_max(high, FIB_LOOKBACK)
    low30 = rolling_min(low, FIB_LOOKBACK)

    downside_momentum = np.zeros(close.shape[0], dtype=np.float64)
    if candidate.rw_lookback < close.shape[0]:
        prev = close[:-candidate.rw_lookback]
        curr = close[candidate.rw_lookback :]
        valid = prev != 0.0
        out = np.zeros(prev.shape[0], dtype=np.float64)
        out[valid] = (prev[valid] - curr[valid]) / prev[valid]
        downside_momentum[candidate.rw_lookback :] = out

    bounce_retracement = np.zeros(close.shape[0], dtype=np.float64)
    denom = high30 - low30
    valid = denom != 0.0
    bounce_retracement[valid] = (close[valid] - low30[valid]) / denom[valid]

    ema_distance = np.zeros(close.shape[0], dtype=np.float64)
    valid_close = close != 0.0
    ema_distance[valid_close] = np.abs(close[valid_close] - ema_values[valid_close]) / close[valid_close]

    entries = (
        (~np.isnan(sma_values))
        & (close < sma_values)
        & (bounce_retracement >= candidate.fib_floor)
        & (bounce_retracement <= candidate.fib_band)
        & (ema_distance <= candidate.eb)
        & (downside_momentum >= candidate.rw)
    )
    exits = (~np.isnan(ema_values)) & (close > ema_values)

    return close, entries.astype(bool), exits.astype(bool)


# ==============================================================================
# 4H CONFIRMATION LOGIC
# ==============================================================================


def build_confirmation_series(
    symbol: str,
    daily_index: pd.DatetimeIndex,
    daily_frames: Dict[str, pd.DataFrame],
    intraday_frames: Dict[str, pd.DataFrame],
    combo: ConfirmCombo,
) -> Tuple[np.ndarray, str]:
    """
    Build a daily-aligned short confirmation mask for one symbol.

    Return value:
    - boolean array aligned to the daily bars
    - string describing whether the filter used true 4H data or a daily fallback
    """

    if symbol in intraday_frames:
        intraday = intraday_frames[symbol]
        close_4h = intraday["close"].to_numpy(dtype=np.float64, copy=True)
        ema_4h = ema(close_4h, combo.ema_period)

        distance = np.full(close_4h.shape[0], -np.inf, dtype=np.float64)
        valid = ema_4h > 0.0
        distance[valid] = (ema_4h[valid] - close_4h[valid]) / ema_4h[valid]

        confirm_4h = (~np.isnan(ema_4h)) & (close_4h < ema_4h) & (distance >= combo.min_distance)

        # Reduce the intraday stream to one daily confirmation value using the
        # final 4H bar from each day, which mirrors the long-side methodology.
        daily_confirm = intraday.copy()
        daily_confirm["confirm"] = confirm_4h.astype(bool)
        daily_confirm["day"] = daily_confirm.index.normalize()
        reduced = daily_confirm.groupby("day")["confirm"].last()

        aligned = reduced.reindex(daily_index.normalize()).fillna(False).to_numpy(dtype=bool)
        return aligned, "4H"

    # If 4H data is missing for the symbol, fall back to a Daily EMA proxy.
    daily = daily_frames[symbol]
    close_daily = daily["close"].to_numpy(dtype=np.float64, copy=True)
    ema_daily = ema(close_daily, combo.ema_period)

    distance = np.full(close_daily.shape[0], -np.inf, dtype=np.float64)
    valid = ema_daily > 0.0
    distance[valid] = (ema_daily[valid] - close_daily[valid]) / ema_daily[valid]

    confirm_daily = (~np.isnan(ema_daily)) & (close_daily < ema_daily) & (distance >= combo.min_distance)
    return confirm_daily.astype(bool), "1D_fallback"


# ==============================================================================
# COMBINED EVALUATION
# ==============================================================================


def evaluate_candidate_combo(
    candidate: ShortSurvivor,
    combo: ConfirmCombo,
    daily_frames: Dict[str, pd.DataFrame],
    intraday_frames: Dict[str, pd.DataFrame],
) -> Dict[str, object]:
    """
    Evaluate one short survivor combined with one short-side 4H confirmation combo.

    The metrics are aggregated across the full watchlist so the ranking lines up
    with the later portfolio-wide Backtrader validation stage.
    """

    all_trade_pnls: List[float] = []
    used_modes: List[str] = []

    for symbol in WATCHLIST:
        if symbol not in daily_frames:
            continue

        df_daily = daily_frames[symbol]
        close, daily_entries, daily_exits = build_daily_entries_exits(df_daily, candidate)
        confirm_mask, mode = build_confirmation_series(
            symbol=symbol,
            daily_index=df_daily.index,
            daily_frames=daily_frames,
            intraday_frames=intraday_frames,
            combo=combo,
        )

        combined_entries = daily_entries & confirm_mask
        all_trade_pnls.extend(trade_pnls(close, combined_entries, daily_exits))
        used_modes.append(mode)

    total_trades = len(all_trade_pnls)
    total_profit = float(sum(all_trade_pnls))
    wins = int(sum(1 for pnl in all_trade_pnls if pnl > 0.0))
    win_rate = (wins / total_trades) if total_trades > 0 else 0.0
    expectancy = (total_profit / total_trades) if total_trades > 0 else 0.0
    total_return = total_profit / INIT_CASH if INIT_CASH > 0 else 0.0

    return {
        "base_analysis_rank": int(candidate.analysis_rank),
        "base_rank": int(candidate.base_rank),
        "daily_param_id": candidate.param_id,
        "source_symbol": candidate.source_symbol,
        "side": "short",
        "sma": int(candidate.sma),
        "ema": int(candidate.ema),
        "fib_floor": float(candidate.fib_floor),
        "fib_band": float(candidate.fib_band),
        "rw": float(candidate.rw),
        "eb": float(candidate.eb),
        "rw_lookback": int(candidate.rw_lookback),
        "confirm_enabled": True,
        "confirm_ema_period": int(combo.ema_period),
        "confirm_min_distance": float(combo.min_distance),
        "confirm_mode": "close_below_ema",
        "assets_with_real_4h": int(sum(1 for mode in used_modes if mode == "4H")),
        "assets_with_daily_fallback": int(sum(1 for mode in used_modes if mode == "1D_fallback")),
        "total_trades": int(total_trades),
        "win_rate": float(win_rate),
        "expectancy": float(expectancy),
        "total_profit": float(total_profit),
        "total_return": float(total_return),
    }


def build_candidate_export(results_df: pd.DataFrame, candidate_limit: int | None) -> pd.DataFrame:
    """
    Build the Backtrader-ready candidate export from the full ranked sweep table.

    We keep the full result table separately so research notes can inspect all
    combos, while this export contains the exact columns needed for validation.
    """

    candidate_df = results_df[
        [
            "combined_rank",
            "param_id",
            "daily_param_id",
            "source_symbol",
            "side",
            "sma",
            "ema",
            "fib_floor",
            "fib_band",
            "rw",
            "eb",
            "rw_lookback",
            "confirm_enabled",
            "confirm_mode",
            "confirm_ema_period",
            "confirm_min_distance",
            "total_trades",
            "win_rate",
            "expectancy",
            "total_profit",
            "total_return",
        ]
    ].copy()

    if candidate_limit is not None:
        candidate_df = candidate_df.head(max(1, int(candidate_limit))).copy()

    return candidate_df.reset_index(drop=True)


def write_summary(
    summary_path: str,
    results_df: pd.DataFrame,
    candidate_df: pd.DataFrame,
    survivors: Sequence[ShortSurvivor],
) -> None:
    """Write a compact markdown summary for the short-side 4H confirmation sweep."""
    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write("# Short Daily + 4H confirmation sweep summary\n\n")
        handle.write(f"- **base_short_survivors_used**: {len(survivors)}\n")
        handle.write(f"- **confirm_ema_periods**: {CONFIRM_EMA_PERIODS}\n")
        handle.write(f"- **confirm_min_distances**: {CONFIRM_MIN_DISTANCES}\n")
        handle.write(f"- **full_combined_rows**: {len(results_df)}\n")
        handle.write(f"- **backtrader_candidate_rows**: {len(candidate_df)}\n")
        handle.write(f"- **best_expectancy**: {results_df['expectancy'].max():.4f}\n")
        handle.write(f"- **best_win_rate**: {results_df['win_rate'].max():.4f}\n")
        handle.write(f"- **best_total_trades**: {int(results_df['total_trades'].max())}\n")
        handle.write("\n## Method Notes\n\n")
        handle.write("- The Daily short layer is unchanged from the validated short discovery phase.\n")
        handle.write("- The 4H layer is confirmation-only: execution close must be below the 4H EMA and far enough below it to clear the minimum distance threshold.\n")
        handle.write("- No fresh full-grid search was performed; this pass only combines the strongest short survivors with a compact 4H confirmation grid.\n")
        handle.write("\n## Top 10 Combined Short Candidates\n\n")

        top = results_df.head(10).copy()
        columns = [
            "param_id",
            "source_symbol",
            "confirm_ema_period",
            "confirm_min_distance",
            "total_trades",
            "win_rate",
            "expectancy",
            "total_return",
        ]
        handle.write("| " + " | ".join(columns) + " |\n")
        handle.write("| " + " | ".join(["---"] * len(columns)) + " |\n")
        for _, row in top[columns].iterrows():
            handle.write("| " + " | ".join(str(row[column]) for column in columns) + " |\n")


def parse_args() -> argparse.Namespace:
    """Expose the script inputs and outputs for reuse."""
    parser = argparse.ArgumentParser(description="Targeted short-side 4H confirmation sweep for short survivors.")
    parser.add_argument("--survivors", default=DEFAULT_SURVIVOR_PATH, help="Path to the short survivor ranking CSV.")
    parser.add_argument("--daily-data", default=DEFAULT_DAILY_PATH, help="Path to the daily market parquet.")
    parser.add_argument("--intraday-data", default=DEFAULT_4H_PATH, help="Path to the 4H market parquet.")
    parser.add_argument("--results-csv", default=DEFAULT_RESULTS_CSV, help="Path for the full ranked sweep results.")
    parser.add_argument("--candidates-csv", default=DEFAULT_CANDIDATES_CSV, help="Path for the Backtrader-ready candidate export.")
    parser.add_argument("--summary-md", default=DEFAULT_SUMMARY_MD, help="Path for the markdown summary.")
    parser.add_argument(
        "--top-n-base",
        type=int,
        default=20,
        help="How many ranked short survivors to use as the Daily base set.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=None,
        help="Optional cap on the exported Backtrader candidate rows. Default keeps all combined rows.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the full short Daily + 4H confirmation sweep."""
    args = parse_args()
    ensure_results_dir()

    survivors = load_survivors(args.survivors, top_n_base=args.top_n_base)
    daily_frames = load_market_by_symbol(args.daily_data)
    intraday_frames = load_market_by_symbol(args.intraday_data)

    combos = [ConfirmCombo(period, distance) for period in CONFIRM_EMA_PERIODS for distance in CONFIRM_MIN_DISTANCES]
    rows: List[Dict[str, object]] = []

    for candidate in survivors:
        for combo in combos:
            rows.append(
                evaluate_candidate_combo(
                    candidate=candidate,
                    combo=combo,
                    daily_frames=daily_frames,
                    intraday_frames=intraday_frames,
                )
            )

    results_df = pd.DataFrame(rows)
    results_df = results_df.sort_values(
        by=["expectancy", "win_rate", "total_trades", "total_return"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    results_df.insert(0, "combined_rank", range(1, len(results_df) + 1))
    results_df["param_id"] = results_df.apply(
        lambda row: f"{row['daily_param_id']}__4h_ema{int(row['confirm_ema_period'])}_dist{float(row['confirm_min_distance']):.3f}",
        axis=1,
    )

    candidate_df = build_candidate_export(results_df, candidate_limit=args.candidate_limit)

    results_df.to_csv(args.results_csv, index=False)
    candidate_df.to_csv(args.candidates_csv, index=False)
    write_summary(args.summary_md, results_df, candidate_df, survivors)

    print(f"Short base survivors loaded: {len(survivors)}")
    print(f"4H confirmation combos tested: {len(combos)}")
    print(f"Full combined rows written: {len(results_df)}")
    print(f"Backtrader candidate rows written: {len(candidate_df)}")
    print(f"Results CSV: {args.results_csv}")
    print(f"Candidates CSV: {args.candidates_csv}")
    print(f"Summary MD: {args.summary_md}")


if __name__ == "__main__":
    main()
