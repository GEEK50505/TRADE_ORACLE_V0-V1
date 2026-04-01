"""Fetch all symbols from `config.settings.WATCHLIST` and optionally run diagnostics.

Usage:
    python scripts/fetch_watchlist.py --diagnose

This wrapper calls `data.data_pipeline.fetch_timeframes_to_parquet()` for the configured
watchlist and writes `data/market_data_{TF}.parquet` files. Use `--diagnose` to run
`scripts/diagnose_data.py` after fetch to validate completeness and prepare multiindex files.
"""
from __future__ import annotations

import argparse
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser(description="Fetch watchlist symbols across timeframes and optionally run diagnostics")
    p.add_argument("--exchange", default="binance", help="ccxt exchange id (default: binance)")
    p.add_argument("--symbols", default=None, help="Optional comma-separated symbols (overrides WATCHLIST)")
    p.add_argument("--timeframes", default="1h,4h,1d", help="Comma-separated timeframes (default: 1h,4h,1d)")
    p.add_argument("--since", default=None, help="ISO date to start from, e.g. 2019-01-01")
    p.add_argument("--out-dir", default="data", help="Output directory for parquet files")
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing output files")
    p.add_argument("--max-pages", type=int, default=None, help="Limit page fetches per symbol for quick tests")
    p.add_argument("--diagnose", action="store_true", help="Run data diagnostics after fetching (scripts/diagnose_data.py)")

    args = p.parse_args()

    # ensure workspace root on sys.path so local packages import correctly
    workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if workspace_root not in sys.path:
        sys.path.insert(0, workspace_root)

    from config.settings import WATCHLIST
    from data.data_pipeline import fetch_timeframes_to_parquet

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = WATCHLIST

    if not symbols:
        logger.error("No symbols specified or found in WATCHLIST")
        sys.exit(1)

    tf_list = [t.strip() for t in args.timeframes.split(",") if t.strip()]

    logger.info("Fetching symbols: %s", symbols)
    paths = fetch_timeframes_to_parquet(
        exchange_id=args.exchange,
        symbols=symbols,
        timeframes=tf_list,
        since=args.since,
        out_dir=args.out_dir,
        overwrite=args.overwrite,
        max_pages=args.max_pages,
    )

    logger.info("Saved market data files: %s", paths)

    if args.diagnose:
        # run the diagnostic script to verify completeness and produce multiindex files
        diag_path = os.path.join(os.path.dirname(__file__), "diagnose_data.py")
        if os.path.exists(diag_path):
            logger.info("Running diagnostics: %s", diag_path)
            import runpy

            runpy.run_path(diag_path, run_name="__main__")
        else:
            logger.warning("Diagnostic script not found: %s", diag_path)


if __name__ == "__main__":
    main()
