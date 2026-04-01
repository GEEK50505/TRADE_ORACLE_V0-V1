"""Recompute SMA and EMA from the MultiIndex parquet and report relative errors.

Ensures calculated `sma50` and `ema20` match stored values within required tolerance.
"""
from __future__ import annotations

import os
import math
from typing import List

import numpy as np
import pandas as pd


FILES = [
    ("1H", "data/market_data_multi_1H.parquet"),
    ("4H", "data/market_data_multi_4H.parquet"),
    ("1D", "data/market_data_multi_1D.parquet"),
]

tol = 0.0000001  # tiny numerical tolerance
required_rel = 0.00001  # 0.001% -> 0.00001

report = []

for tf_label, path in FILES:
    if not os.path.exists(path):
        print(f"Missing multi parquet: {path}")
        continue

    wide = pd.read_parquet(path)
    # ensure MultiIndex columns
    if not isinstance(wide.columns, pd.MultiIndex):
        print(f"File {path} does not have MultiIndex columns. Skipping.")
        continue

    symbols = list(wide.columns.levels[0])
    for sym in symbols:
        try:
            close = wide[sym]["close"].astype(float)
            sma_stored = wide[sym]["sma50"].astype(float)
            ema_stored = wide[sym]["ema20"].astype(float)
        except Exception as e:
            print(f"Missing columns for {sym} in {path}: {e}")
            continue

        sma_calc = close.rolling(window=50, min_periods=1).mean()
        ema_calc = close.ewm(span=20, adjust=False).mean()

        # compute relative errors where stored != 0
        sma_mask = sma_stored != 0
        if sma_mask.any():
            sma_rel = (sma_calc[sma_mask] - sma_stored[sma_mask]).abs() / sma_stored[sma_mask].abs()
            sma_max_rel = float(sma_rel.max()) if not sma_rel.empty else 0.0
        else:
            sma_max_rel = float((sma_calc - sma_stored).abs().max())

        ema_mask = ema_stored != 0
        if ema_mask.any():
            ema_rel = (ema_calc[ema_mask] - ema_stored[ema_mask]).abs() / ema_stored[ema_mask].abs()
            ema_max_rel = float(ema_rel.max()) if not ema_rel.empty else 0.0
        else:
            ema_max_rel = float((ema_calc - ema_stored).abs().max())

        ok_sma = sma_max_rel <= required_rel or math.isclose(sma_max_rel, 0.0, rel_tol=tol)
        ok_ema = ema_max_rel <= required_rel or math.isclose(ema_max_rel, 0.0, rel_tol=tol)

        report.append({
            "timeframe": tf_label,
            "symbol": sym,
            "sma50_max_rel_error": sma_max_rel,
            "ema20_max_rel_error": ema_max_rel,
            "sma_within_0.001pct": bool(ok_sma),
            "ema_within_0.001pct": bool(ok_ema),
        })

rep_df = pd.DataFrame(report)
print(rep_df.to_string(index=False))

if (rep_df["sma_within_0.001pct"].all() and rep_df["ema_within_0.001pct"].all()):
    print("\nAll SMA/EMA match recomputed values within 0.001% relative error.")
else:
    print("\nOne or more indicators exceed 0.001% relative error. See above for details.")
