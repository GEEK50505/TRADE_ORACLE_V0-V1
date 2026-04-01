"""Generate a per-symbol manifest for market parquet files and validate 36-month coverage.

Outputs:
 - results/data_manifest.csv
 - results/data_manifest.json

Prints a concise summary and any issues detected (insufficient history or indicator NaNs).
"""
from __future__ import annotations

import os
import json
import datetime
from typing import List, Dict, Any

import pandas as pd


FILES = [
    ("1H", "data/market_data_1H.parquet"),
    ("4H", "data/market_data_4H.parquet"),
    ("1D", "data/market_data_1D.parquet"),
]

OUT_DIR = "results"
os.makedirs(OUT_DIR, exist_ok=True)

manifest: List[Dict[str, Any]] = []
issues: List[str] = []

now = datetime.datetime.utcnow().date()
expected_36 = now - datetime.timedelta(days=1095)  # ~36 months (approx)

indicator_cols = ["sma50", "ema20", "rel_weak_14", "high30", "low30"]

for tf_label, path in FILES:
    if not os.path.exists(path):
        issues.append(f"MISSING FILE: {path}")
        continue

    size_bytes = os.path.getsize(path)

    try:
        df = pd.read_parquet(path)
    except Exception as e:
        issues.append(f"FAILED_READ {path}: {e}")
        continue

    # ensure timestamp column
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    else:
        df = df.reset_index()
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"]) 

    if "symbol" not in df.columns:
        # treat entire table as single symbol if missing
        df["symbol"] = "_all"

    symbols = sorted(df["symbol"].unique())

    for sym in symbols:
        sdf = df[df["symbol"] == sym]
        rows = len(sdf)
        if rows == 0:
            issues.append(f"EMPTY for {sym} in {path}")
            continue

        start = pd.to_datetime(sdf["timestamp"]).min()
        end = pd.to_datetime(sdf["timestamp"]).max()

        row: Dict[str, Any] = {
            "timeframe": tf_label,
            "file": path,
            "file_size_bytes": int(size_bytes),
            "symbol": sym,
            "rows": int(rows),
            "start": pd.Timestamp(start).isoformat(),
            "end": pd.Timestamp(end).isoformat(),
        }

        # indicators completeness per symbol
        for col in indicator_cols:
            if col in sdf.columns:
                nans = int(sdf[col].isna().sum())
                row[f"{col}_nans"] = nans
                row[f"{col}_nans_pct"] = float(nans) / float(rows)
                if nans > 0:
                    issues.append(f"{nans} NaNs in {col} for {sym} ({tf_label})")
            else:
                row[f"{col}_nans"] = None
                row[f"{col}_nans_pct"] = None
                issues.append(f"MISSING_COLUMN {col} in {path}")

        # coverage check (does start <= expected_36?)
        try:
            start_date = pd.to_datetime(start).date()
            covers_36 = start_date <= expected_36
        except Exception:
            covers_36 = False

        row["covers_36_months"] = bool(covers_36)
        manifest.append(row)


# Save manifest CSV & JSON
csv_path = os.path.join(OUT_DIR, "data_manifest.csv")
json_path = os.path.join(OUT_DIR, "data_manifest.json")

mdf = pd.DataFrame(manifest)
if not mdf.empty:
    mdf.to_csv(csv_path, index=False)
    with open(json_path, "w", encoding="utf8") as fh:
        json.dump(manifest, fh, indent=2, default=str)

# Print concise summary
print("Per-symbol manifest written:", csv_path)
print(mdf[["timeframe", "symbol", "rows", "start", "end", "covers_36_months"]].to_string(index=False))

if issues:
    print("\nISSUES DETECTED:")
    for it in issues:
        print(" -", it)
else:
    print("\nNo issues detected. Dataset appears complete for 36-month coverage and indicators.")
