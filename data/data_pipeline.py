"""Lightweight data ingestion utilities for TRADE_ORACLE.

This module provides small, memory-conscious helpers to fetch OHLCV via ccxt,
compute core indicators, and persist a compact multi-symbol parquet file.

Design notes:
- Heavy imports (ccxt, pandas, pyarrow) are performed inside functions so the module
  can be imported for static checks without requiring all optional deps.
- The combined market data file is a tall table with columns: timestamp, symbol,
  open, high, low, close, volume, sma50, ema20, rel_weak_14, high30, low30
"""

from __future__ import annotations

import os
import time
import datetime
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def _ensure_dir(path: str) -> None:
    if not path:
        return
    os.makedirs(path, exist_ok=True)


def _to_ms(date_or_none) -> Optional[int]:
    if date_or_none is None:
        return None
    if isinstance(date_or_none, (int, float)):
        return int(date_or_none)
    if isinstance(date_or_none, str):
        # Accept ISO date strings like '2020-01-01' or '2020-01-01T00:00:00'
        dt = datetime.datetime.fromisoformat(date_or_none)
        return int(dt.timestamp() * 1000)
    if isinstance(date_or_none, datetime.datetime):
        return int(date_or_none.timestamp() * 1000)
    return None


def fetch_ohlcv_ccxt(
    exchange_id: str,
    symbol: str,
    timeframe: str = "1h",
    since: Optional[str | int | datetime.datetime] = None,
    limit: int = 1000,
    max_pages: Optional[int] = None,
) -> "pandas.DataFrame":
    """Fetch OHLCV from a ccxt exchange and return a pandas DataFrame.

    Notes:
    - `since` may be an ISO date string, datetime, or millisecond timestamp.
    - This helper pages through history by requesting `limit` bars repeatedly until
      no more data is returned or `max_pages` is reached.
    """
    import ccxt
    import pandas as pd

    ex_cls = getattr(ccxt, exchange_id, None)
    if ex_cls is None:
        raise ValueError(f"Unknown ccxt exchange id: {exchange_id}")

    ex = ex_cls({"enableRateLimit": True})
    since_ms = _to_ms(since)

    rows: List[list] = []
    pages = 0

    while True:
        try:
            bars = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=limit)
        except Exception as exc:  # pragma: no cover - network/error handling
            logger.warning("fetch_ohlcv failed for %s %s: %s", symbol, timeframe, exc)
            time.sleep(1.0)
            continue

        if not bars:
            break

        rows.extend(bars)
        pages += 1

        if max_pages and pages >= max_pages:
            break

        # If fewer bars returned than requested, we've reached the available history
        if len(bars) < limit:
            break

        # Advance `since_ms` to after the last fetched candle
        last_ts = bars[-1][0]
        since_ms = int(last_ts) + 1

        # Respect exchange rate limit if provided
        sleep_time = getattr(ex, "rateLimit", 200) / 1000.0
        time.sleep(sleep_time)

    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])  # empty

    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["ts"], unit="ms")
    df.set_index("timestamp", inplace=True)
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    df.index.name = "timestamp"

    # Drop exact-duplicate timestamps if any
    df = df[~df.index.duplicated(keep="first")]

    return df


def compute_indicators(
    df: "pandas.DataFrame",
    sma_period: int = 50,
    ema_period: int = 20,
    rel_weak_period: int = 14,
    structural_period: int = 30,
) -> "pandas.DataFrame":
    """Append core indicators to a price DataFrame and return a new DataFrame.

    Produces columns: `sma50`, `ema20`, `rel_weak_14`, `high30`, `low30`.
    """
    import pandas as pd
    import numpy as np

    df = df.copy()
    df["sma50"] = df["close"].rolling(window=sma_period, min_periods=1).mean()
    df["ema20"] = df["close"].ewm(span=ema_period, adjust=False).mean()
    df["high30"] = df["high"].rolling(window=structural_period, min_periods=1).max()
    df["low30"] = df["low"].rolling(window=structural_period, min_periods=1).min()

    # Relative weakness defined as percent distance from the rolling N-period high
    rolling_high = df["high"].rolling(window=rel_weak_period, min_periods=1).max()
    df["rel_weak_14"] = (df["close"] - rolling_high) / rolling_high
    # Avoid pandas chained-assignment/copy-on-write warnings by assigning results
    df["rel_weak_14"] = df["rel_weak_14"].replace([np.inf, -np.inf], np.nan)
    df["rel_weak_14"] = df["rel_weak_14"].fillna(0.0)

    return df


def _ensure_regular_index(df: "pandas.DataFrame", timeframe: str) -> "pandas.DataFrame":
    """Reindex the DataFrame to a regular time grid for the given timeframe.

    Missing OHLCV rows are forward-filled for price fields and volume set to 0.
    This ensures indicator columns can be computed without producing NaNs.
    """
    import pandas as pd

    tf_map = {"1h": "H", "4h": "4H", "1d": "D", "1D": "D"}
    freq = tf_map.get(timeframe, timeframe)

    if df.empty:
        return df

    # ensure index is datetime and sorted
    if df.index.name != "timestamp":
        try:
            df = df.set_index(pd.to_datetime(df.index))
        except Exception:
            df.index = pd.to_datetime(df.index)
        df.index.name = "timestamp"

    start = df.index.min()
    end = df.index.max()
    full_idx = pd.date_range(start=start, end=end, freq=freq)
    df = df.reindex(full_idx)

    # Fill prices using forward-fill; volume -> 0 for missing candles
    if "close" in df.columns:
        df["close"] = df["close"].ffill()
    for col in ["open", "high", "low"]:
        if col in df.columns:
            df[col] = df[col].ffill().fillna(df["close"] if "close" in df.columns else None)
    if "volume" in df.columns:
        df["volume"] = df["volume"].fillna(0)

    df.index.name = "timestamp"
    return df


def save_parquet(df: "pandas.DataFrame", path: str, compression: str = "snappy") -> None:
    """Persist DataFrame to parquet if possible; fallback to compressed CSV.

    Creates parent directories as needed.
    """
    _ensure_dir(os.path.dirname(path))
    try:
        df.to_parquet(path, compression=compression)
        logger.info("Saved parquet: %s", path)
    except Exception as exc:  # pragma: no cover - runtime environment differences
        logger.warning("Failed to write parquet (%s), falling back to CSV: %s", path, exc)
        csv_path = os.path.splitext(path)[0] + ".csv.gz"
        df.to_csv(csv_path, index=True, compression="gzip")
        logger.info("Saved CSV: %s", csv_path)


def fetch_symbols_to_parquet(
    exchange_id: str,
    symbols: List[str],
    timeframe: str = "1h",
    since: Optional[str | int | datetime.datetime] = None,
    out_path: str = "data/market_data_1H.parquet",
    overwrite: bool = False,
    max_pages: Optional[int] = None,
) -> str:
    """Fetch multiple symbols, compute indicators, and write a single tall parquet.

    The resulting DataFrame has columns: timestamp, symbol, open, high, low, close, volume, sma50, ema20, rel_weak_14, high30, low30
    """
    import pandas as pd

    if os.path.exists(out_path) and not overwrite:
        raise FileExistsError(f"Output path already exists: {out_path}")

    rows = []
    for sym in symbols:
        logger.info("Fetching %s %s (%s)", sym, timeframe, exchange_id)
        df = fetch_ohlcv_ccxt(exchange_id, sym, timeframe=timeframe, since=since, max_pages=max_pages)
        if df.empty:
            logger.warning("No data for %s", sym)
            continue
        # ensure regular time grid for this timeframe and then compute indicators
        try:
            df = _ensure_regular_index(df, timeframe)
        except Exception:
            # fallback: proceed without reindexing if something unexpected occurs
            logger.exception("Failed to regularize index for %s %s", sym, timeframe)
        df = compute_indicators(df)
        df = df.reset_index()
        df["symbol"] = sym
        rows.append(df)

    if not rows:
        raise RuntimeError("No data fetched for any symbol")

    combined = pd.concat(rows, ignore_index=True, sort=False)
    # Ensure timestamp column exists and is named consistently
    if "timestamp" not in combined.columns and combined.index.name == "timestamp":
        combined = combined.reset_index()

    save_parquet(combined, out_path)
    return out_path


def fetch_timeframes_to_parquet(
    exchange_id: str,
    symbols: List[str],
    timeframes: Optional[List[str]] = None,
    since: Optional[str | int | datetime.datetime] = None,
    out_dir: str = "data",
    overwrite: bool = False,
    max_pages: Optional[int] = None,
) -> List[str]:
    """Fetch multiple timeframes for the given symbols and write per-timeframe parquet files.

    Default `timeframes` is ['1h', '4h', '1d']. If `since` is None, defaults to 36 months back.
    Returns list of output paths written.
    """
    if timeframes is None:
        timeframes = ["1h", "4h", "1d"]

    # default to 36 months of history if not specified
    if since is None:
        since = datetime.datetime.utcnow() - datetime.timedelta(days=365 * 3)

    out_paths: List[str] = []
    for tf in timeframes:
        # sanitize timeframe label for filename (e.g., '1h' -> '1H')
        label = tf.replace("h", "H").replace("d", "D").replace("/", "")
        out_path = os.path.join(out_dir, f"market_data_{label}.parquet")
        logger.info("Fetching timeframe %s -> %s", tf, out_path)
        try:
            path = fetch_symbols_to_parquet(
                exchange_id=exchange_id,
                symbols=symbols,
                timeframe=tf,
                since=since,
                out_path=out_path,
                overwrite=overwrite,
                max_pages=max_pages,
            )
            out_paths.append(path)
        except Exception as exc:  # pragma: no cover - runtime/network
            logger.exception("Failed to fetch timeframe %s: %s", tf, exc)

    return out_paths


if __name__ == "__main__":
    print("This module provides helpers — import and call `fetch_symbols_to_parquet()` from a script.")
