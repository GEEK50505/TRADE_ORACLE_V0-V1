"""Chunked parameter sweep for TRADE_ORACLE (lightweight fallback).

This script implements the Sub-Phase 2 chunked sweep pattern. It will:
- load a tall parquet market dataset (`timestamp,symbol,open,high,low,close,volume,...`)
- build a small parameter grid (fib_min, fib_max, ema_buffer)
- evaluate each parameter set in memory-safe chunks and persist chunk results

The evaluator is a lightweight placeholder that computes crude forward returns
for candidate signals so the pipeline is runnable on a laptop without VectorBT.
If you later want to integrate VectorBT, replace `run_simulated_sweep` with a
VectorBT-based evaluator that accepts a chunk of parameter combinations.
"""

from __future__ import annotations

import argparse
import itertools
import os
import gc
from typing import List, Dict, Any

import numpy as np
import pandas as pd


def build_grid(fib_mins, fib_maxs, ema_buffers) -> List[Dict[str, Any]]:
    grid = []
    for a, b, c in itertools.product(fib_mins, fib_maxs, ema_buffers):
        if a >= b:
            continue
        grid.append({"fib_min": float(a), "fib_max": float(b), "ema_buffer": float(c)})
    return grid


def run_simulated_sweep(df: pd.DataFrame, params_chunk: List[Dict[str, Any]], forward: int = 5) -> pd.DataFrame:
    """Evaluate a chunk of parameter sets using a simple forward-return metric.

    Notes:
    - Operates on a tall dataframe but works best if df is for a single symbol.
    - Returns a DataFrame with one row per parameter set and simple metrics.
    """
    rows = []

    # Prepare indicator columns once
    data = df.copy()
    if "timestamp" in data.columns:
        data = data.sort_values("timestamp")
    data["ema20_local"] = data["close"].ewm(span=20, adjust=False).mean()
    data["high14"] = data["high"].rolling(window=14, min_periods=1).max()
    data["low14"] = data["low"].rolling(window=14, min_periods=1).min()
    denom = (data["high14"] - data["low14"]).replace(0, np.nan)
    data["retracement"] = (data["high14"] - data["close"]) / denom
    data["retracement"] = data["retracement"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    forward_returns = (data["close"].shift(-forward) - data["close"]) / data["close"]

    for p in params_chunk:
        fib_min = p["fib_min"]
        fib_max = p["fib_max"]
        ema_buffer = p["ema_buffer"]

        cond = (
            (data["retracement"] >= fib_min)
            & (data["retracement"] <= fib_max)
            & (data["close"] < data["ema20_local"] * (1 - ema_buffer))
        )

        trades = forward_returns[cond]
        trade_count = int(cond.sum())

        if trade_count == 0:
            win_rate = 0.0
            avg_return = 0.0
            expectancy = 0.0
        else:
            win_rate = float((trades > 0).sum()) / float(len(trades))
            avg_return = float(trades.mean())
            avg_win = float(trades[trades > 0].mean()) if (trades > 0).any() else 0.0
            avg_loss = float(trades[trades <= 0].mean()) if (trades <= 0).any() else 0.0
            expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss

        rows.append({
            "fib_min": fib_min,
            "fib_max": fib_max,
            "ema_buffer": ema_buffer,
            "trade_count": trade_count,
            "win_rate": win_rate,
            "avg_return": avg_return,
            "expectancy": expectancy,
        })

    return pd.DataFrame(rows)


def run_chunked_optimization(data_path: str, out_dir: str, chunk_size: int = 500, forward: int = 5):
    os.makedirs(out_dir, exist_ok=True)
    df = pd.read_parquet(data_path)

    # If tall multi-symbol table, choose first symbol for smoke runs
    if "symbol" in df.columns:
        symbols = df["symbol"].unique()
        symbol = symbols[0]
        df_symbol = df[df["symbol"] == symbol].copy()
    else:
        symbol = "_all"
        df_symbol = df.copy()

    # Example grid (expand as needed)
    fib_mins = [0.45, 0.5, 0.618]
    fib_maxs = [0.618, 0.7, 0.786]
    ema_buffers = [0.005, 0.01, 0.02]

    grid = build_grid(fib_mins, fib_maxs, ema_buffers)

    partials = []
    for i in range(0, len(grid), chunk_size):
        chunk = grid[i : i + chunk_size]
        print(f"Running chunk {i // chunk_size + 1} — {len(chunk)} param sets")
        chunk_df = run_simulated_sweep(df_symbol, chunk, forward=forward)
        chunk_file = os.path.join(out_dir, f"chunk_{i//chunk_size}.parquet")
        chunk_df.to_parquet(chunk_file)
        partials.append(chunk_df)

        # free memory between chunks
        del chunk_df
        gc.collect()

    if partials:
        full = pd.concat(partials, ignore_index=True)
    else:
        full = pd.DataFrame()

    # Save aggregated results
    surface_csv = os.path.join(out_dir, "oracle_parameter_surface.csv")
    full.sort_values("expectancy", ascending=False).to_csv(surface_csv, index=False)

    # Save top 100
    top_csv = os.path.join(out_dir, "top_100_parameters.csv")
    full.sort_values("expectancy", ascending=False).head(100).to_csv(top_csv, index=False)

    print("Optimization sweep complete.")
    print("Surface:", surface_csv)
    print("Top 100:", top_csv)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, default="data/market_data_1H.parquet")
    parser.add_argument("--out", type=str, default="results")
    parser.add_argument("--chunk-size", type=int, default=50)
    parser.add_argument("--forward", type=int, default=5)
    args = parser.parse_args()

    run_chunked_optimization(args.data, args.out, chunk_size=args.chunk_size, forward=args.forward)


if __name__ == "__main__":
    main()
