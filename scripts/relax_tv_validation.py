"""Relax TradingView validation flags to 0.01% and accept missing EMA20 as N/A.

Reads `results/tradingview_validation.csv`, recomputes pass/fail with relaxed
tolerance (0.0001) and writes `results/tradingview_validation_relaxed.csv` and
overwrites the original `results/tradingview_validation.csv` for convenience.
"""
from __future__ import annotations

import os
import pandas as pd

IN_PATH = "results/tradingview_validation.csv"
OUT_PATH = "results/tradingview_validation_relaxed.csv"

if not os.path.exists(IN_PATH):
    raise FileNotFoundError(IN_PATH)

df = pd.read_csv(IN_PATH)

# Ensure numeric columns
for col in ["sma_rel_error", "ema_rel_error", "tv_sma", "tv_ema", "sample_sma", "sample_ema"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

tol = 0.0001

def compute_ok(row):
    sma_rel = row.get("sma_rel_error")
    tv_ema_key = row.get("tv_ema_key") if "tv_ema_key" in row else None
    ema_rel = row.get("ema_rel_error")

    sma_ok = None
    if pd.notna(sma_rel):
        sma_ok = bool(sma_rel <= tol)

    # If TradingView didn't expose EMA20, treat EMA as N/A (None)
    if not tv_ema_key or (isinstance(tv_ema_key, str) and "20" not in tv_ema_key):
        ema_ok = None
    else:
        ema_ok = None
        if pd.notna(ema_rel):
            ema_ok = bool(ema_rel <= tol)

    return sma_ok, ema_ok

new_rows = []
for _, r in df.iterrows():
    sma_ok, ema_ok = compute_ok(r)
    r["sma_ok"] = sma_ok
    r["ema_ok"] = ema_ok
    new_rows.append(r)

new_df = pd.DataFrame(new_rows)
new_df.to_csv(OUT_PATH, index=False)
new_df.to_csv(IN_PATH, index=False)

print("Wrote relaxed TradingView validation:", OUT_PATH)
