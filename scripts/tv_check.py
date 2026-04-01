"""Automated TradingView comparison for indicator samples.

Reads `results/indicator_samples.csv` and queries TradingView (via tradingview_ta)
for the latest candle's SMA(50) and EMA(20). Compares values and writes
`results/tradingview_validation.csv` with relative errors and pass/fail flags.

Notes:
- TradingView access via tradingview_ta returns latest-candle indicator values; historical
  per-timestamp indicators are not available via this library, so we validate the
  latest sample per (timeframe, symbol) pair.
"""
from __future__ import annotations

import time
import os
import csv
from typing import Dict

import pandas as pd
from tradingview_ta import TA_Handler, Interval


SAMPLES_CSV = "results/indicator_samples.csv"
OUT_CSV = "results/tradingview_validation.csv"

if not os.path.exists(SAMPLES_CSV):
    raise FileNotFoundError(SAMPLES_CSV)

df = pd.read_csv(SAMPLES_CSV)

# Normalize timeframe labels in samples to match our MultiIndex naming
def normalize_tf(tf: str) -> str:
    return tf.strip().upper()


def tf_to_interval(tf: str):
    t = tf.strip().lower()
    if t in ("1h", "1H"):
        return Interval.INTERVAL_1_HOUR
    if t in ("4h", "4H"):
        return Interval.INTERVAL_4_HOURS
    if t in ("1d", "1D", "D"):
        return Interval.INTERVAL_1_DAY
    raise ValueError(f"Unsupported timeframe: {tf}")


# For each (timeframe, symbol) pick the latest sample timestamp available
grouped = df.groupby([df["timeframe"], df["symbol"]])
rows = []

for (tf, sym), g in grouped:
    latest = g.sort_values("timestamp").iloc[-1]
    rows.append(latest.to_dict())

results = []

for row in rows:
    tf = row["timeframe"]
    symbol = row["symbol"]
    sample_sma = row.get("sma50")
    sample_ema = row.get("ema20")
    sample_ts = row.get("timestamp")

    # TradingView wants symbol like 'BTCUSDT' and exchange 'BINANCE'
    sym_tv = symbol.replace("/", "").upper()
    exchange = "BINANCE"

    try:
        interval = tf_to_interval(tf)
    except Exception as e:
        results.append({"timeframe": tf, "symbol": symbol, "error": str(e)})
        continue

    handler = TA_Handler(symbol=sym_tv, screener="crypto", exchange=exchange, interval=interval)

    try:
        analysis = handler.get_analysis()
        indicators = analysis.indicators
    except Exception as e:
        results.append({"timeframe": tf, "symbol": symbol, "error": f"tv_error: {e}"})
        time.sleep(1.5)
        continue

    # find SMA50 and EMA20 keys in indicators dict
    sma_key = None
    ema_key = None
    for k in indicators.keys():
        kl = k.lower()
        if "sma" in kl and "50" in kl:
            sma_key = k
        if "ema" in kl and "20" in kl:
            ema_key = k

    tv_sma = indicators.get(sma_key) if sma_key else None
    tv_ema = indicators.get(ema_key) if ema_key else None

    # Some values might be strings; cast to float where possible
    def as_float(x):
        try:
            return float(x)
        except Exception:
            return None

    tv_sma_f = as_float(tv_sma)
    tv_ema_f = as_float(tv_ema)

    # compute relative errors
    def rel_err(a, b):
        if a is None or b is None:
            return None
        if a == 0:
            return abs(a - b)
        return abs(a - b) / abs(a)

    sma_rel = rel_err(tv_sma_f, sample_sma)
    ema_rel = rel_err(tv_ema_f, sample_ema)

    # Relaxed tolerance: 0.01% -> 0.0001
    tol = 0.0001

    sma_ok = sma_rel is not None and sma_rel <= tol

    # If TradingView did not expose an EMA20 key, skip EMA check (treat as N/A)
    if ema_key is None or tv_ema_f is None:
        ema_ok = None
    else:
        ema_ok = ema_rel is not None and ema_rel <= tol

    results.append(
        {
            "timeframe": tf,
            "symbol": symbol,
            "sample_timestamp": sample_ts,
            "tv_sma_key": sma_key,
            "tv_ema_key": ema_key,
            "tv_sma": tv_sma_f,
            "tv_ema": tv_ema_f,
            "sample_sma": sample_sma,
            "sample_ema": sample_ema,
            "sma_rel_error": sma_rel,
            "ema_rel_error": ema_rel,
            "sma_ok": sma_ok,
            "ema_ok": ema_ok,
        }
    )

    # be polite to TradingView
    time.sleep(1.5)

# write results
keys = list({k for r in results for k in r.keys()})
with open(OUT_CSV, "w", newline="", encoding="utf8") as fh:
    writer = csv.DictWriter(fh, fieldnames=keys)
    writer.writeheader()
    for r in results:
        writer.writerow(r)

print("TradingView validation complete. Results:", OUT_CSV)
print(pd.DataFrame(results).to_string(index=False))
