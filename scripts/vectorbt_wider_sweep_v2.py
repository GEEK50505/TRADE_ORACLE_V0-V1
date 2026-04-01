"""
Sub-Phase 2: Wider Daily Parameter Relaxation v2

This script is the next daily-only sweep for the TRADE_ORACLE optimization loop.
It is designed to widen the search surface aggressively, lower the temporary
selection gates, and generate a larger candidate pool for Backtrader validation.
For this pass, success is defined as producing 100+ relaxed candidates.

Why this is a standalone v2 script:
- The latest daily run produced 156,800 rows with 0 passes even under softer gates.
- In this workspace, `import vectorbt` is currently stalling, so this script uses a
  fast `numba`-accelerated chunk engine instead of depending on that import.
- The signal logic intentionally stays close to the current daily sweep so the
  results remain comparable to prior outputs.

Important implementation note:
- Your new spec names a single "Fibonacci Band" range.
- The current sweep family uses a retracement zone rather than a single fib pair.
- To keep the logic compatible while honoring your requested ladder, this v2 pass
  interprets `fib_band` as the upper edge of the accepted retracement zone:
      0.236 <= retracement <= fib_band

Requested ranges used in this script:
- SMA window: 30 to 90, step 5
- Relative weakness threshold: 0.002 to 0.055, step 0.003
- Fibonacci band: 0.236 to 0.786, step 0.05
- EMA buffer: 0.003 to 0.070, step 0.005
- Relative weakness lookback: 8, 10, 12, 14, 18, 21, 25

Temporary relaxed gates used in this script:
- total_trades >= 12
- win_rate >= 0.35
- expectancy >= 1.00

Outputs:
- results/daily_wider_v2_sweep_results.csv
- results/daily_wider_v2_candidates.csv
- results/daily_wider_v2_top_candidates.csv
- results/daily_wider_v2_optimization_summary.md
- results/daily_wider_v2_chunk_<SYMBOL>_<N>.parquet

Recommended full run:
    python scripts/vectorbt_wider_sweep_v2.py

Quick smoke test:
    python scripts/vectorbt_wider_sweep_v2.py --symbol BTC/USDT --chunk-size 2000 --max-chunks 1
"""

from __future__ import annotations

import argparse
import gc
import itertools
import math
import os
import time
from dataclasses import dataclass
from typing import Iterable, List, Sequence

import numpy as np
import pandas as pd

try:
    from numba import njit, prange

    NUMBA_AVAILABLE = True
except Exception:
    NUMBA_AVAILABLE = False


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

DEFAULT_MARKET_PATH = os.path.join(ROOT_DIR, "data", "market_data_1D.parquet")
DEFAULT_RESULTS_PREFIX = os.path.join(RESULTS_DIR, "daily_wider_v2")

DEFAULT_SYMBOLS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "XRP/USDT",
    "DOGE/USDT",
    "AVAX/USDT",
    "LINK/USDT",
    "TON/USDT",
    "ADA/USDT",
    "BNB/USDT",
]

EMA_WINDOW = 20
ROLLING_EXTREMA_WINDOW = 30
FIB_FLOOR = 0.236
INIT_CASH = 10_000.0
FEE = 0.0005

MIN_TRADES_GATE = 12
MIN_WIN_RATE_GATE = 0.35
MIN_EXPECTANCY_GATE = 1.0
TARGET_CANDIDATES = 100


def build_threshold_ladder(start: float, stop: float, step: float) -> List[float]:
    values = []
    current = start
    while current <= stop + 1e-12:
        values.append(round(current, 6))
        current += step
    if not math.isclose(values[-1], stop, abs_tol=1e-9):
        values.append(round(stop, 6))
    return values


SMA_WINDOWS = list(range(30, 91, 5))
RW_THRESHOLDS = build_threshold_ladder(0.002, 0.055, 0.003)
FIB_BANDS = build_threshold_ladder(0.236, 0.786, 0.05)
EMA_BUFFERS = build_threshold_ladder(0.003, 0.070, 0.005)
RW_LOOKBACKS = [8, 10, 12, 14, 18, 21, 25]


@dataclass(frozen=True)
class ParamCombo:
    sma: int
    rw: float
    fib_band: float
    ema_buffer: float
    rw_lookback: int
    sma_idx: int
    rw_idx: int
    fib_idx: int
    ema_idx: int


def build_param_grid() -> List[ParamCombo]:
    rw_pairs = list(itertools.product(range(len(RW_LOOKBACKS)), range(len(RW_THRESHOLDS))))
    combos: List[ParamCombo] = []
    for sma_idx, sma in enumerate(SMA_WINDOWS):
        for fib_idx, fib_band in enumerate(FIB_BANDS):
            for ema_idx, ema_buffer in enumerate(EMA_BUFFERS):
                for rw_idx, (lb_idx, thr_idx) in enumerate(rw_pairs):
                    combos.append(
                        ParamCombo(
                            sma=sma,
                            rw=RW_THRESHOLDS[thr_idx],
                            fib_band=fib_band,
                            ema_buffer=ema_buffer,
                            rw_lookback=RW_LOOKBACKS[lb_idx],
                            sma_idx=sma_idx,
                            rw_idx=rw_idx,
                            fib_idx=fib_idx,
                            ema_idx=ema_idx,
                        )
                    )
    return combos


PARAM_GRID = build_param_grid()
COMBOS_PER_SYMBOL = len(PARAM_GRID)
TOTAL_COMBOS_ALL_SYMBOLS = COMBOS_PER_SYMBOL * len(DEFAULT_SYMBOLS)


def ensure_results_dir() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)


def sanitize_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")


def rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    out = np.full(values.shape[0], np.nan, dtype=np.float32)
    if window <= 0 or values.size == 0 or window > values.size:
        return out
    kernel = np.ones(window, dtype=np.float32) / float(window)
    out[window - 1 :] = np.convolve(values.astype(np.float32), kernel, mode="valid")
    return out


def ema(values: np.ndarray, window: int) -> np.ndarray:
    out = np.full(values.shape[0], np.nan, dtype=np.float32)
    if values.size == 0:
        return out
    alpha = 2.0 / (window + 1.0)
    out[0] = values[0]
    for i in range(1, values.shape[0]):
        out[i] = alpha * values[i] + (1.0 - alpha) * out[i - 1]
    return out


def rolling_max(values: np.ndarray, window: int) -> np.ndarray:
    series = pd.Series(values)
    return (
        series.rolling(window=window, min_periods=1).max().to_numpy(dtype=np.float32, copy=False)
    )


def rolling_min(values: np.ndarray, window: int) -> np.ndarray:
    series = pd.Series(values)
    return (
        series.rolling(window=window, min_periods=1).min().to_numpy(dtype=np.float32, copy=False)
    )


def build_feature_masks(
    df_sym: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    close = df_sym["close"].to_numpy(dtype=np.float32, copy=True)
    high = df_sym["high"].to_numpy(dtype=np.float32, copy=True)
    low = df_sym["low"].to_numpy(dtype=np.float32, copy=True)

    ema20 = (
        df_sym["ema20"].to_numpy(dtype=np.float32, copy=True)
        if "ema20" in df_sym.columns
        else ema(close, EMA_WINDOW)
    )
    high30 = (
        df_sym["high30"].to_numpy(dtype=np.float32, copy=True)
        if "high30" in df_sym.columns
        else rolling_max(high, ROLLING_EXTREMA_WINDOW)
    )
    low30 = (
        df_sym["low30"].to_numpy(dtype=np.float32, copy=True)
        if "low30" in df_sym.columns
        else rolling_min(low, ROLLING_EXTREMA_WINDOW)
    )

    sma_masks = np.zeros((close.shape[0], len(SMA_WINDOWS)), dtype=np.bool_)
    for idx, window in enumerate(SMA_WINDOWS):
        sma_values = rolling_mean(close, window)
        sma_masks[:, idx] = np.logical_and(~np.isnan(sma_values), close > sma_values)

    rw_pairs = list(itertools.product(RW_LOOKBACKS, RW_THRESHOLDS))
    rw_masks = np.zeros((close.shape[0], len(rw_pairs)), dtype=np.bool_)
    for idx, (lookback, threshold) in enumerate(rw_pairs):
        rw = np.zeros(close.shape[0], dtype=np.float32)
        prev = close[:-lookback]
        curr = close[lookback:]
        valid = prev != 0.0
        out = np.zeros(prev.shape[0], dtype=np.float32)
        out[valid] = (prev[valid] - curr[valid]) / prev[valid]
        rw[lookback:] = out
        rw_masks[:, idx] = rw >= threshold

    retracement = np.zeros(close.shape[0], dtype=np.float32)
    denom = high30 - low30
    valid = denom != 0.0
    retracement[valid] = (high30[valid] - close[valid]) / denom[valid]
    retracement = np.where(np.isfinite(retracement), retracement, 0.0).astype(np.float32, copy=False)

    fib_masks = np.zeros((close.shape[0], len(FIB_BANDS)), dtype=np.bool_)
    for idx, fib_band in enumerate(FIB_BANDS):
        fib_masks[:, idx] = np.logical_and(retracement >= FIB_FLOOR, retracement <= fib_band)

    ema_distance = np.zeros(close.shape[0], dtype=np.float32)
    valid_close = close != 0.0
    ema_distance[valid_close] = np.abs(close[valid_close] - ema20[valid_close]) / close[valid_close]
    ema_distance = np.where(np.isfinite(ema_distance), ema_distance, 0.0).astype(np.float32, copy=False)

    ema_masks = np.zeros((close.shape[0], len(EMA_BUFFERS)), dtype=np.bool_)
    for idx, ema_buffer in enumerate(EMA_BUFFERS):
        ema_masks[:, idx] = ema_distance <= ema_buffer

    exits = np.logical_and(~np.isnan(ema20), close < ema20)
    return close, sma_masks, rw_masks, fib_masks, ema_masks, exits


if NUMBA_AVAILABLE:

    @njit(parallel=True, cache=True)
    def backtest_chunk(close: np.ndarray, entries: np.ndarray, exits: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        n_rows, n_cols = entries.shape
        total_returns = np.zeros(n_cols, dtype=np.float64)
        total_trades = np.zeros(n_cols, dtype=np.int64)
        win_rates = np.zeros(n_cols, dtype=np.float64)
        expectancy = np.zeros(n_cols, dtype=np.float64)

        for col in prange(n_cols):
            in_position = False
            entry_price = 0.0
            pnl_sum = 0.0
            wins = 0
            trades = 0

            for row in range(n_rows):
                if entries[row, col] and not in_position:
                    entry_price = float(close[row])
                    in_position = True

                if exits[row] and in_position:
                    exit_price = float(close[row])
                    pnl_pct = (exit_price - entry_price) / entry_price - (2.0 * FEE)
                    pnl = INIT_CASH * pnl_pct
                    pnl_sum += pnl
                    if pnl > 0.0:
                        wins += 1
                    trades += 1
                    in_position = False

            if in_position:
                exit_price = float(close[n_rows - 1])
                pnl_pct = (exit_price - entry_price) / entry_price - (2.0 * FEE)
                pnl = INIT_CASH * pnl_pct
                pnl_sum += pnl
                if pnl > 0.0:
                    wins += 1
                trades += 1

            total_trades[col] = trades
            if trades > 0:
                win_rates[col] = wins / trades
                expectancy[col] = pnl_sum / trades
                total_returns[col] = pnl_sum / INIT_CASH

        return total_returns, total_trades, win_rates, expectancy

else:

    def backtest_chunk(close: np.ndarray, entries: np.ndarray, exits: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        n_rows, n_cols = entries.shape
        total_returns = np.zeros(n_cols, dtype=np.float64)
        total_trades = np.zeros(n_cols, dtype=np.int64)
        win_rates = np.zeros(n_cols, dtype=np.float64)
        expectancy = np.zeros(n_cols, dtype=np.float64)

        for col in range(n_cols):
            in_position = False
            entry_price = 0.0
            pnl_sum = 0.0
            wins = 0
            trades = 0

            for row in range(n_rows):
                if entries[row, col] and not in_position:
                    entry_price = float(close[row])
                    in_position = True

                if exits[row] and in_position:
                    exit_price = float(close[row])
                    pnl_pct = (exit_price - entry_price) / entry_price - (2.0 * FEE)
                    pnl = INIT_CASH * pnl_pct
                    pnl_sum += pnl
                    if pnl > 0.0:
                        wins += 1
                    trades += 1
                    in_position = False

            if in_position:
                exit_price = float(close[-1])
                pnl_pct = (exit_price - entry_price) / entry_price - (2.0 * FEE)
                pnl = INIT_CASH * pnl_pct
                pnl_sum += pnl
                if pnl > 0.0:
                    wins += 1
                trades += 1

            total_trades[col] = trades
            if trades > 0:
                win_rates[col] = wins / trades
                expectancy[col] = pnl_sum / trades
                total_returns[col] = pnl_sum / INIT_CASH

        return total_returns, total_trades, win_rates, expectancy


def build_entry_matrix(
    sma_masks: np.ndarray,
    rw_masks: np.ndarray,
    fib_masks: np.ndarray,
    ema_masks: np.ndarray,
    chunk: Sequence[ParamCombo],
) -> np.ndarray:
    sma_idx = np.array([combo.sma_idx for combo in chunk], dtype=np.int64)
    rw_idx = np.array([combo.rw_idx for combo in chunk], dtype=np.int64)
    fib_idx = np.array([combo.fib_idx for combo in chunk], dtype=np.int64)
    ema_idx = np.array([combo.ema_idx for combo in chunk], dtype=np.int64)
    entries = sma_masks[:, sma_idx]
    entries &= rw_masks[:, rw_idx]
    entries &= fib_masks[:, fib_idx]
    entries &= ema_masks[:, ema_idx]
    return entries


def chunked(sequence: Sequence[ParamCombo], size: int) -> Iterable[Sequence[ParamCombo]]:
    for start in range(0, len(sequence), size):
        yield sequence[start : start + size]


def select_symbols(df_market: pd.DataFrame, symbol_arg: str | None) -> List[str]:
    available = sorted(df_market["symbol"].astype(str).unique().tolist())
    if symbol_arg:
        if symbol_arg not in available:
            raise ValueError(f"Symbol not found in market file: {symbol_arg}")
        return [symbol_arg]

    wanted = [symbol for symbol in DEFAULT_SYMBOLS if symbol in available]
    missing = [symbol for symbol in DEFAULT_SYMBOLS if symbol not in available]
    if missing:
        print(f"Warning: missing {len(missing)} expected symbols: {missing}")
    if not wanted:
        raise ValueError("None of the default 10 requested symbols were found in the market file.")
    return wanted


def write_summary(
    summary_path: str,
    total_rows: int,
    candidate_rows: int,
    top_rows: int,
    best_expectancy: float,
    best_win_rate: float,
    best_trades: int,
    elapsed: float,
    symbols: Sequence[str],
) -> None:
    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write("# Daily Wider v2 sweep optimization summary\n\n")
        handle.write(f"- **symbols_processed**: {', '.join(symbols)}\n")
        handle.write(f"- **combinations_per_symbol**: {COMBOS_PER_SYMBOL}\n")
        handle.write(f"- **total_rows_written**: {total_rows}\n")
        handle.write(f"- **candidates_after_relaxed_gates**: {candidate_rows}\n")
        handle.write(f"- **top_candidates_saved**: {top_rows}\n")
        handle.write(f"- **best_expectancy**: {best_expectancy}\n")
        handle.write(f"- **best_win_rate**: {best_win_rate}\n")
        handle.write(f"- **best_total_trades**: {best_trades}\n")
        handle.write(f"- **elapsed_seconds**: {elapsed:.2f}\n")
        handle.write("\n## Temporary Run Logic\n\n")
        handle.write("- Widening further is intended to break the current trade starvation and surface more parameter neighborhoods.\n")
        handle.write("- The relaxed gates are temporary discovery gates, not deployment gates.\n")
        handle.write(f"- Success for this pass is {TARGET_CANDIDATES}+ candidates for Backtrader validation.\n")
        handle.write("- After candidate generation, the next step is chronological Backtrader validation under Maven-style constraints.\n")


def run_sweep(
    market_path: str,
    results_prefix: str,
    chunk_size: int,
    top_n: int,
    symbol_arg: str | None = None,
    max_chunks: int | None = None,
    keep_existing: bool = False,
) -> None:
    ensure_results_dir()
    if not os.path.exists(market_path):
        raise FileNotFoundError(f"Market data not found: {market_path}")

    df_market = pd.read_parquet(market_path)
    if "symbol" not in df_market.columns:
        raise ValueError("Expected a tall market parquet with a `symbol` column.")

    symbols = select_symbols(df_market, symbol_arg)
    results_csv = f"{results_prefix}_sweep_results.csv"
    candidates_csv = f"{results_prefix}_candidates.csv"
    top_csv = f"{results_prefix}_top_candidates.csv"
    summary_md = f"{results_prefix}_optimization_summary.md"

    if not keep_existing:
        for path in [results_csv, candidates_csv, top_csv, summary_md]:
            if os.path.exists(path):
                os.remove(path)

    print("Starting wider daily v2 sweep")
    print(f"Market file: {market_path}")
    print(f"Symbols: {symbols}")
    print(f"Combinations per symbol: {COMBOS_PER_SYMBOL:,}")
    print(f"Total combinations for this run: {COMBOS_PER_SYMBOL * len(symbols):,}")
    print(f"Chunk size: {chunk_size:,}")
    print(
        "Relaxed gates: "
        f"total_trades >= {MIN_TRADES_GATE}, "
        f"win_rate >= {MIN_WIN_RATE_GATE:.2f}, "
        f"expectancy >= ${MIN_EXPECTANCY_GATE:.2f}"
    )
    if not NUMBA_AVAILABLE:
        print("Warning: numba not available. The fallback path will be slower.")

    total_rows_written = 0
    start_time = time.time()

    for symbol in symbols:
        df_sym = (
            df_market.loc[df_market["symbol"] == symbol]
            .copy()
            .sort_values("timestamp")
            .set_index("timestamp")
        )
        close, sma_masks, rw_masks, fib_masks, ema_masks, exits = build_feature_masks(df_sym)
        symbol_safe = sanitize_symbol(symbol)

        print(f"\n[{symbol}] rows={len(df_sym)} | building chunks...")

        for chunk_number, chunk in enumerate(chunked(PARAM_GRID, chunk_size)):
            if max_chunks is not None and chunk_number >= max_chunks:
                print(f"[{symbol}] max_chunks reached ({max_chunks}); stopping early for smoke mode.")
                break

            entries = build_entry_matrix(sma_masks, rw_masks, fib_masks, ema_masks, chunk)
            total_return, total_trades, win_rate, expectancy = backtest_chunk(close, entries, exits)

            rows = []
            for idx, combo in enumerate(chunk):
                rows.append(
                    {
                        "symbol": symbol,
                        "sma": combo.sma,
                        "ema": EMA_WINDOW,
                        "fib_floor": FIB_FLOOR,
                        "fib_band": combo.fib_band,
                        "rw": combo.rw,
                        "eb": combo.ema_buffer,
                        "rw_lookback": combo.rw_lookback,
                        "total_return": float(total_return[idx]),
                        "total_trades": int(total_trades[idx]),
                        "win_rate": float(win_rate[idx]),
                        "expectancy": float(expectancy[idx]),
                    }
                )

            chunk_df = pd.DataFrame(rows)
            chunk_path = f"{results_prefix}_chunk_{symbol_safe}_{chunk_number}.parquet"
            chunk_df.to_parquet(chunk_path, index=False)
            chunk_df.to_csv(results_csv, mode="a", header=not os.path.exists(results_csv), index=False)

            total_rows_written += len(chunk_df)
            elapsed = time.time() - start_time
            print(
                f"[{symbol}] chunk {chunk_number:03d} "
                f"wrote {len(chunk_df):,} rows "
                f"(running total {total_rows_written:,}) "
                f"elapsed {elapsed:.1f}s"
            )

            del entries
            del chunk_df
            gc.collect()

    if not os.path.exists(results_csv):
        raise RuntimeError("No sweep output was written. Check symbol selection and chunk settings.")

    df_all = pd.read_csv(results_csv)
    mask = (
        (df_all["total_trades"] >= MIN_TRADES_GATE)
        & (df_all["win_rate"] >= MIN_WIN_RATE_GATE)
        & (df_all["expectancy"] >= MIN_EXPECTANCY_GATE)
    )
    df_candidates = df_all.loc[mask].copy().sort_values(
        by=["expectancy", "win_rate", "total_trades"],
        ascending=[False, False, False],
    )
    df_candidates.to_csv(candidates_csv, index=False)
    df_top = df_candidates.head(top_n)
    df_top.to_csv(top_csv, index=False)

    elapsed = time.time() - start_time
    best_expectancy = float(df_all["expectancy"].max()) if not df_all.empty else 0.0
    best_win_rate = float(df_all["win_rate"].max()) if not df_all.empty else 0.0
    best_trades = int(df_all["total_trades"].max()) if not df_all.empty else 0

    write_summary(
        summary_path=summary_md,
        total_rows=len(df_all),
        candidate_rows=len(df_candidates),
        top_rows=len(df_top),
        best_expectancy=best_expectancy,
        best_win_rate=best_win_rate,
        best_trades=best_trades,
        elapsed=elapsed,
        symbols=symbols,
    )

    print("\nSweep complete.")
    print(f"All results: {results_csv}")
    print(f"Candidates:  {candidates_csv}")
    print(f"Top saved:   {top_csv}")
    print(f"Summary:     {summary_md}")
    print(f"Candidates after relaxed gates: {len(df_candidates):,}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wider daily v2 sweep for TRADE_ORACLE")
    parser.add_argument("--market", default=DEFAULT_MARKET_PATH, help="Path to daily market parquet.")
    parser.add_argument(
        "--results-prefix",
        default=DEFAULT_RESULTS_PREFIX,
        help="Prefix for result files. Example: results/daily_wider_v2",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=5000,
        help="Parameter combinations per chunk. Lower this if RAM is tight.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=200,
        help="How many top relaxed candidates to save into the top file.",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Optional single-symbol smoke/test run. Default is all 10 target assets.",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="Optional limit for smoke tests. Example: --max-chunks 1",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Append to existing result files instead of resetting them first.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_sweep(
        market_path=args.market,
        results_prefix=args.results_prefix,
        chunk_size=args.chunk_size,
        top_n=args.top_n,
        symbol_arg=args.symbol,
        max_chunks=args.max_chunks,
        keep_existing=args.keep_existing,
    )


if __name__ == "__main__":
    main()
