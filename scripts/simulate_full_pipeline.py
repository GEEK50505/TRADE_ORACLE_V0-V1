"""Run an end-to-end TRADE_ORACLE demo pipeline against the live daemon path.

This script is intentionally aimed at supervised demo validation:
- loads the requested env file
- injects one high-quality scanner setup into the real daemon pipeline
- sends the real Telegram review message
- can auto-approve the review inside the daemon without waiting for a real callback
- can therefore exercise real MT5 demo execution when the graph and risk gates allow
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full TRADE_ORACLE demo pipeline through the live daemon path.")
    parser.add_argument("--env-file", default=".env.n8n.local", help="Env file to load before starting.")
    parser.add_argument("--symbol", default="SOL/USDT", help="Strategy symbol to inject into the scanner payload.")
    parser.add_argument("--current-price", type=float, default=83.95, help="Current price for the injected setup.")
    parser.add_argument("--atr", type=float, default=1.25, help="ATR for the injected setup.")
    parser.add_argument("--timeframe", default="4h", help="Timeframe label for the injected setup.")
    parser.add_argument("--regime", default="BULLISH", help="Regime label for the injected setup.")
    parser.add_argument("--setup-quality", type=float, default=0.98, help="Setup quality score for the injected setup.")
    parser.add_argument(
        "--no-auto-approve",
        action="store_true",
        help="Stop after the Telegram review message is sent instead of auto-approving internally.",
    )
    return parser.parse_args()


def _build_mock_setup(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "symbol": args.symbol,
        "regime": args.regime,
        "current_price": float(args.current_price),
        "atr": float(args.atr),
        "timeframe": args.timeframe,
        "fibonacci_convergence_proximity": 0.005,
        "ema_cluster_distance": 0.002,
        "setup_quality": float(args.setup_quality),
        "rationale": "Simulated high-conviction bullish structure for full daemon pipeline validation.",
        "narrative_tags": ["ema20_confirmed", "fib_confluence_strong", "simulated_full_pipeline"],
    }


def _build_scanner_runner(mock_setup: dict[str, Any]):
    async def _runner(_watchlist: list[str]) -> list[dict[str, Any]]:
        print("\n[SIMULATOR] Injecting high-quality setup into the live daemon pipeline...")
        return [dict(mock_setup)]

    return _runner


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    load_dotenv(REPO_ROOT / args.env_file, override=True)

    from ai.trade_oracle_daemon import build_default_trade_oracle_daemon

    daemon = build_default_trade_oracle_daemon()
    daemon.scanner_runner = _build_scanner_runner(_build_mock_setup(args))

    print("=== TRADE_ORACLE Full Pipeline Simulator ===")
    print("[SIMULATOR] Clearing any open pending reviews before the run...")
    open_reviews = daemon._list_open_reviews(limit=100)
    for review in open_reviews:
        daemon.runtime_state_store.resolve_pending_review(
            review.thread_id,
            review_action="rejected_by_simulator_clear",
            review_status="resolved",
            reviewer="simulator",
            review_notes="Cleared before fresh full-pipeline simulation run.",
            cycle_outcome="no_trade",
        )
    print(f"[SIMULATOR] Cleared {len(open_reviews)} review(s).")

    try:
        cycle_result = await daemon.run_cycle_once()
        rendered: dict[str, Any] = {
            "stage": "cycle",
            "outcome": cycle_result.outcome,
            "run_id": cycle_result.run_id,
            "cycle_id": cycle_result.cycle_id,
            "candidate_count": cycle_result.candidate_count,
            "pending_review_count": cycle_result.pending_review_count,
            "transmitted": cycle_result.transmitted,
            "thread_ids": list(cycle_result.thread_ids),
        }

        if cycle_result.outcome != "pending_review" or not cycle_result.thread_ids or args.no_auto_approve:
            return rendered

        thread_id = cycle_result.thread_ids[0]
        print(f"[SIMULATOR] Auto-approving thread {thread_id} through the daemon resume path...")
        resume_result = await daemon.process_callback_query(
            {
                "id": "",
                "data": f"approve:{thread_id}",
                "from": {"username": "autonomous_simulator", "first_name": "Autonomous Sim"},
            }
        )
        rendered["stage"] = "resume"
        rendered["review_action"] = "APPROVE"
        rendered["resume_outcome"] = resume_result.outcome if resume_result is not None else ""
        rendered["resume_transmitted"] = bool(resume_result.transmitted) if resume_result is not None else False
        rendered["resume_thread_ids"] = list(resume_result.thread_ids) if resume_result is not None else []
        return rendered
    finally:
        telegram_client = getattr(daemon, "telegram_client", None)
        if telegram_client is not None and hasattr(telegram_client, "aclose"):
            await telegram_client.aclose()


def main() -> None:
    args = _parse_args()
    print(json.dumps(asyncio.run(_run(args)), indent=2))


if __name__ == "__main__":
    main()
