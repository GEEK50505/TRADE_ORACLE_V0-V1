"""Fetch TradingView OHLCV via tvdatafeed, recompute SMA/EMA, and compare with our samples.

Writes `results/tradingview_historical_validation.csv` with relative errors and pass/fail.
"""
from __future__ import annotations

import os
import time
import math
import csv
from typing import Dict, Any

import pandas as pd

try:
    from tvDatafeed import TvDatafeed
    from tvDatafeed import Interval
except Exception as exc:
    raise RuntimeError("tvDatafeed not installed or import failed: %s" % exc)


SAMPLES = "results/indicator_samples.csv"
OUT = "results/tradingview_historical_validation.csv"

if not os.path.exists(SAMPLES):
    raise FileNotFoundError(SAMPLES)

samples = pd.read_csv(SAMPLES)

# Normalize timeframe label
def norm_tf(tf: str) -> str:
    return tf.strip().upper()


def tf_to_interval(tf: str):
    t = tf.strip().lower()
    if t in ("1h", "1H"):
        return Interval.in_1_hour
    if t in ("4h", "4H"):
        return Interval.in_4_hours
    if t in ("1d", "1D", "d"):
        return Interval.in_daily
    raise ValueError(f"Unsupported timeframe: {tf}")


# number of bars to request per timeframe (sufficient to cover 36 months)
n_bars_map = {"1H": 30000, "4H": 8000, "1D": 1500}

tv = TvDatafeed()

results = []

grouped = samples.groupby([samples["timeframe"], samples["symbol"]])
for (tf, sym), g in grouped:
    tfn = norm_tf(tf)
    sym_tv = sym.replace("/", "").upper()
    exchange = "BINANCE"
    try:
        interval = tf_to_interval(tfn)
    except Exception as e:
        for _, row in g.iterrows():
            results.append({"timeframe": tf, "symbol": sym, "timestamp": row["timestamp"], "error": str(e)})
        continue

    n_bars = n_bars_map.get(tfn, 2000)

    print(f"Fetching TV history {sym_tv} {exchange} {tfn} n_bars={n_bars}")
    try:
        df_tv = tv.get_hist(sym_tv, exchange, interval=interval, n_bars=n_bars)
    except Exception as e:
        for _, row in g.iterrows():
            results.append({"timeframe": tf, "symbol": sym, "timestamp": row["timestamp"], "error": f"tv_get_hist:{e}"})
        continue

    if df_tv is None or df_tv.empty:
        for _, row in g.iterrows():
            results.append({"timeframe": tf, "symbol": sym, "timestamp": row["timestamp"], "error": "no_data"})
        continue

    # ensure datetime index
    if not isinstance(df_tv.index, pd.DatetimeIndex):
        if "time" in df_tv.columns:
            df_tv.index = pd.to_datetime(df_tv["time"])  # fallback
        else:
            df_tv.index = pd.to_datetime(df_tv.index)

    df_tv = df_tv.sort_index()

    # compute indicators from TradingView OHLCV
    close = df_tv["close"].astype(float)
    sma_tv = close.rolling(window=50, min_periods=1).mean()
    ema_tv = close.ewm(span=20, adjust=False).mean()

    for _, row in g.iterrows():
        sample_ts = pd.to_datetime(row["timestamp"])
        # find nearest previous index
        try:
            pos = df_tv.index.get_indexer([sample_ts], method="ffill")[0]
        except Exception:
            pos = -1

        if pos == -1:
            results.append({"timeframe": tf, "symbol": sym, "timestamp": row["timestamp"], "error": "no_match_ts"})
            continue

        ts_idx = df_tv.index[pos]
        sma_val = float(sma_tv.iloc[pos])
        ema_val = float(ema_tv.iloc[pos])

        sample_sma = float(row.get("sma50")) if not pd.isna(row.get("sma50")) else None
        sample_ema = float(row.get("ema20")) if not pd.isna(row.get("ema20")) else None

        def rel_err(a, b):
            if a is None or b is None:
                return None
            if a == 0:
                return abs(a - b)
            return abs(a - b) / abs(a)

        sma_rel = rel_err(sma_val, sample_sma)
        ema_rel = rel_err(ema_val, sample_ema)
        sma_ok = sma_rel is not None and sma_rel <= 0.00001
        ema_ok = ema_rel is not None and ema_rel <= 0.00001

        results.append(
            {
                "timeframe": tf,
                "symbol": sym,
                "sample_timestamp": row["timestamp"],
                "tv_timestamp": ts_idx.isoformat(),
                "tv_sma50": sma_val,
                "tv_ema20": ema_val,
                "sample_sma50": sample_sma,
                "sample_ema20": sample_ema,
                "sma_rel_error": sma_rel,
                "ema_rel_error": ema_rel,
                "sma_ok": sma_ok,
                "ema_ok": ema_ok,
            }
        )

        # be polite
        time.sleep(0.5)

# write results
keys = [k for r in results for k in r.keys()]
keys = list(dict.fromkeys(keys))
os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
with open(OUT, "w", newline="", encoding="utf8") as fh:
    writer = csv.DictWriter(fh, fieldnames=keys)
    writer.writeheader()
    for r in results:
        writer.writerow(r)

print("Wrote historical TradingView validation:", OUT)
