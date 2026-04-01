"""Validate generated market parquet files for indicators and basic integrity."""
import os
import pandas as pd

files = [
    "data/market_data_1H.parquet",
    "data/market_data_4H.parquet",
    "data/market_data_1D.parquet",
]

for f in files:
    if not os.path.exists(f):
        print(f"MISSING: {f}")
        continue
    try:
        df = pd.read_parquet(f)
    except Exception as e:
        print(f"FAILED TO READ {f}: {e}")
        continue

    print(f"\nFILE: {f}")
    print(" rows:", len(df))
    print(" cols:", list(df.columns))

    for col in ["sma50", "ema20", "rel_weak_14", "high30", "low30"]:
        if col in df.columns:
            nans = int(df[col].isna().sum())
            pct = (nans / len(df)) if len(df) else 0
            print(f"  {col}: nans={nans} ({pct:.4%})")
        else:
            print(f"  missing: {col}")

    size = os.path.getsize(f)
    print(" size bytes:", size, " MB:", round(size / (1024 * 1024), 2))

    if "timestamp" in df.columns and "symbol" in df.columns:
        dup = int(df.duplicated(subset=["timestamp", "symbol"]).sum())
        print(" duplicates timestamp+symbol:", dup)

    # print first rows for quick inspection
    print(df.head(3).to_string(index=False))
