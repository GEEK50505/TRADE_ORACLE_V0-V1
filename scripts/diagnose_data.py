"""Diagnostics for market data quality and MultiIndex output.

Produces:
- results/data_diagnostic.csv (per-symbol diagnostic)
- results/data_diagnostic.json
- data/market_data_multi_{TF}.parquet for each timeframe
- results/indicator_samples.csv for external validation (TradingView)

Checks:
- expected vs actual timestamps (counts, missing/imputed)
- indicator NaN counts and completeness ratios
- overall completeness percentage (must be > 99.9%)
"""
from __future__ import annotations

import os
import json
import math
from typing import List, Dict, Any

import numpy as np
import pandas as pd


FILES = [
    ("1H", "data/market_data_1H.parquet", "H"),
    ("4H", "data/market_data_4H.parquet", "4H"),
    ("1D", "data/market_data_1D.parquet", "D"),
]

OUT_DIR = "results"
os.makedirs(OUT_DIR, exist_ok=True)

indicator_cols = ["sma50", "ema20", "rel_weak_14", "high30", "low30"]
ohlcv_cols = ["open", "high", "low", "close", "volume"]

diagnostics: List[Dict[str, Any]] = []

samples: List[Dict[str, Any]] = []

for tf_label, path, freq in FILES:
    if not os.path.exists(path):
        print(f"Missing file: {path}")
        continue

    df = pd.read_parquet(path)
    # normalize timestamp column/index
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        if df.index.name != "timestamp":
            df = df.set_index("timestamp")
    else:
        df.index = pd.to_datetime(df.index)
        df.index.name = "timestamp"

    df = df.sort_index()

    symbols = sorted(df["symbol"].unique())

    # Build per-symbol diagnostics and assemble multiindex wide frame
    symbol_frames = {}
    for sym in symbols:
        sdf = df[df["symbol"] == sym].copy()
        sdf = sdf.sort_index()

        start = sdf.index.min()
        end = sdf.index.max()
        expected_idx = pd.date_range(start=start, end=end, freq=freq)
        expected_count = len(expected_idx)
        actual_count = len(sdf)
        missing_count = expected_count - actual_count

        # missing timestamps (imputed via forward-fill during fetch)
        missing_ts = []
        if missing_count > 0:
            missing_ts = list(expected_idx.difference(sdf.index))

        # indicator NaNs
        ind_nans = {col: int(sdf[col].isna().sum()) if col in sdf.columns else None for col in indicator_cols}

        # completeness ratio for indicators
        total_indicator_cells = actual_count * len(indicator_cols)
        non_null_cells = sum((0 if ind_nans[c] is None else (actual_count - ind_nans[c])) for c in indicator_cols)
        completeness = float(non_null_cells) / float(total_indicator_cells) if total_indicator_cells else 0.0

        diag = {
            "timeframe": tf_label,
            "symbol": sym,
            "file": path,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "expected_count": int(expected_count),
            "actual_count": int(actual_count),
            "missing_timestamps": int(missing_count),
            "completeness_ratio": completeness,
        }

        for col in indicator_cols:
            diag[f"{col}_nans"] = ind_nans.get(col)

        diagnostics.append(diag)

        # prepare wide frame for this symbol
        cols = ohlcv_cols + indicator_cols
        # ensure all columns exist
        for c in cols:
            if c not in sdf.columns:
                sdf[c] = pd.NA

        sdf = sdf[cols]
        # resample/sort to expected index to ensure alignment
        sdf = sdf.reindex(expected_idx)
        symbol_frames[sym] = sdf

        # take 6 sample timestamps evenly across the available range for external validation
        if len(expected_idx) >= 6:
            idx_positions = np.linspace(0, len(expected_idx) - 1, num=6, dtype=int)
        else:
            idx_positions = np.arange(len(expected_idx), dtype=int)

        for pos in idx_positions:
            ts = expected_idx[pos]
            row = symbol_frames[sym].loc[ts]
            sample = {
                "timeframe": tf_label,
                "symbol": sym,
                "timestamp": ts.isoformat(),
            }
            for c in ["close", "sma50", "ema20"]:
                sample[c] = None if c not in row.index else (None if pd.isna(row[c]) else float(row[c]))
            samples.append(sample)

    # create a MultiIndex-wide DataFrame by concatenating with keys
    if symbol_frames:
        wide = pd.concat(symbol_frames, axis=1)
        # save wide parquet
        out_multi = f"data/market_data_multi_{tf_label}.parquet"
        wide.to_parquet(out_multi)
        print(f"Wrote multiindex parquet: {out_multi} (symbols: {len(symbol_frames)})")


# Save diagnostics
diag_df = pd.DataFrame(diagnostics)
diag_csv = os.path.join(OUT_DIR, "data_diagnostic.csv")
diag_json = os.path.join(OUT_DIR, "data_diagnostic.json")
diag_df.to_csv(diag_csv, index=False)
with open(diag_json, "w", encoding="utf8") as fh:
    json.dump(diagnostics, fh, indent=2, default=str)

samples_csv = os.path.join(OUT_DIR, "indicator_samples.csv")
pd.DataFrame(samples).to_csv(samples_csv, index=False)

print("\nDiagnostics written:", diag_csv)
print("Samples for external validation:", samples_csv)

# Print summary
overall = diag_df.groupby("timeframe")["completeness_ratio"].agg(["mean", "min"]).reset_index()
print("\nCompleteness summary by timeframe:")
print(overall.to_string(index=False))

threshold = 0.999
all_good = True
for _, row in overall.iterrows():
    if row["mean"] < threshold:
        all_good = False
        print(f"WARNING: {row['timeframe']} completeness mean {row['mean']:.6f} below {threshold}")

if all_good:
    print("\nAll timeframes exceed completeness threshold 99.9% — ready for Sub-Phase 2.")
else:
    print("\nOne or more timeframes failed completeness gate. Investigate data_diagnostic.csv")
