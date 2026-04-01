"""Small CLI wrapper to populate `data/market_data_1H.parquet`.

Usage examples:
    python scripts/fetch_data.py --symbols BTC/USDT,ETH/USDT --timeframe 1h --since 2019-01-01 --out data/market_data_1H.parquet
"""

from __future__ import annotations

import argparse
import os
import logging
from typing import List

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_symbols(s: str) -> List[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch OHLCV and compute indicators for symbols")
    parser.add_argument("--exchange", type=str, default="binance", help="ccxt exchange id (default: binance)")
    parser.add_argument("--symbols", type=str, required=True, help="Comma-separated symbols, e.g. BTC/USDT,ETH/USDT")
    parser.add_argument(
        "--timeframes",
        type=str,
        default="1h,4h,1d",
        help="Comma-separated OHLCV timeframes (default: 1h,4h,1d)",
    )
    parser.add_argument("--since", type=str, default=None, help="ISO date to start from, e.g. 2019-01-01")
    parser.add_argument("--out", type=str, default="data/market_data_1H.parquet", help="Output parquet path")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output file")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit page fetches per symbol (useful for quick tests)")

    args = parser.parse_args()

    symbols = parse_symbols(args.symbols)

    # Ensure the repository root is on sys.path so `data` package is importable
    import sys
    workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if workspace_root not in sys.path:
        sys.path.insert(0, workspace_root)

    # Import heavy helper here to avoid requiring deps at import-time
    from data.data_pipeline import fetch_symbols_to_parquet, fetch_timeframes_to_parquet

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    try:
        tf_list = [t.strip() for t in args.timeframes.split(",") if t.strip()]
        if len(tf_list) == 1:
            out = fetch_symbols_to_parquet(
                exchange_id=args.exchange,
                symbols=symbols,
                timeframe=tf_list[0],
                since=args.since,
                out_path=args.out,
                overwrite=args.overwrite,
                max_pages=args.max_pages,
            )
            logger.info("Saved market data to %s", out)
        else:
            out_dir = os.path.dirname(args.out) or "data"
            paths = fetch_timeframes_to_parquet(
                exchange_id=args.exchange,
                symbols=symbols,
                timeframes=tf_list,
                since=args.since,
                out_dir=out_dir,
                overwrite=args.overwrite,
                max_pages=args.max_pages,
            )
            logger.info("Saved market data files: %s", paths)
    except Exception as exc:
        logger.exception("Failed to fetch and save market data: %s", exc)
        raise


if __name__ == "__main__":
    main()
