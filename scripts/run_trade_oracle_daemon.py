"""Run the single-runtime TRADE_ORACLE daemon without n8n orchestration."""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
import logging
from pathlib import Path

# Configure logging first to capture startup events
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.trade_oracle_daemon import _try_acquire_cycle_lock, build_default_trade_oracle_daemon
from config import settings


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
    runtime_lock = None
    if not args.once and not args.poll_once:
        runtime_lock = _try_acquire_cycle_lock(
            settings.TRADE_ORACLE_DAEMON_RUNTIME_LOCK_PATH,
            stale_seconds=settings.TRADE_ORACLE_DAEMON_RUNTIME_LOCK_STALE_SECONDS,
        )
        if runtime_lock is None:
            print("[TRADE_ORACLE] Another long-running daemon owns the runtime lock. Exiting.")
            return
    daemon = build_default_trade_oracle_daemon()
    try:
        if args.once:
            await daemon.run_cycle_once()
            return
        if args.poll_once:
            await daemon.poll_telegram_once()
            return

        loop = asyncio.get_running_loop()
        main_task = loop.create_task(daemon.run_forever(start_immediately=not args.no_immediate_start))

        def _signal_handler():
            print("\n[TRADE_ORACLE] Interrupt received. Triggering graceful shutdown to preserve runtime state...")
            main_task.cancel()

        try:
            loop.add_signal_handler(signal.SIGINT, _signal_handler)
            loop.add_signal_handler(signal.SIGTERM, _signal_handler)
        except NotImplementedError:
            signal.signal(signal.SIGINT, lambda sig, frame: _signal_handler())
            signal.signal(signal.SIGTERM, lambda sig, frame: _signal_handler())

        try:
            await main_task
        except asyncio.CancelledError:
            print("[TRADE_ORACLE] Daemon shut down cleanly. State is safe.")
    finally:
        telegram_client = getattr(daemon, "telegram_client", None)
        if telegram_client is not None and hasattr(telegram_client, "aclose"):
            await telegram_client.aclose()
        if runtime_lock is not None:
            runtime_lock.release()


if __name__ == "__main__":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass
    asyncio.run(_main())
