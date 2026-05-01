"""Run the single-runtime TRADE_ORACLE daemon without n8n orchestration."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.trade_oracle_daemon import build_default_trade_oracle_daemon


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the TRADE_ORACLE single-runtime daemon.")
    parser.add_argument("--once", action="store_true", help="Run one forward-test cycle and exit.")
    parser.add_argument("--poll-once", action="store_true", help="Poll Telegram once for callback updates and exit.")
    parser.add_argument(
        "--no-immediate-start",
        action="store_true",
        help="When running forever, wait one full interval before the first cycle.",
    )
    return parser.parse_args()


async def _main() -> None:
    args = parse_args()
    daemon = build_default_trade_oracle_daemon()
    if args.once:
        await daemon.run_cycle_once()
        return
    if args.poll_once:
        await daemon.poll_telegram_once()
        return
    await daemon.run_forever(start_immediately=not args.no_immediate_start)


if __name__ == "__main__":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass
    asyncio.run(_main())
