"""Safely test the live Telegram review callback path end to end.

This script:
- creates a dummy pending review in the selected backend
- sends a real Telegram inline-button review message
- waits for one Approve/Reject callback
- resolves the review to a no-trade terminal outcome

It never scans markets and never transmits broker orders.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class _SafeExecutionClient:
    async def authenticate(self):
        return True

    async def get_platform_details(self):
        return {"equity": 10000.0, "active_trades": 0}

    async def shutdown(self):
        return None


class _SafeResumeOrchestrator:
    def __init__(self, thread_id: str):
        self.thread_id = thread_id

    async def resume_review(self, *args, **kwargs):
        from ai.langgraph_orchestrator import LangGraphEvaluationResult

        return LangGraphEvaluationResult(
            status="no_trade",
            thread_id=self.thread_id,
            interrupted=True,
            review_required=False,
            raw_setup={"asset_ticker": "TELEGRAM/TEST", "localized_atr": 0.0},
            review_context={"reason": "live_telegram_diagnostic"},
            final_decision={},
            gatekeeper_status="telegram_test_complete",
            candidate=None,
        )


async def _run(*, env_file: str, backend: str, wait_seconds: int) -> dict:
    load_dotenv(REPO_ROOT / env_file, override=True)

    from ai.trade_oracle_daemon import HttpxTelegramBotClient, OPEN_REVIEW_STATUSES, TradeOracleSingleRuntimeDaemon
    from ai.trade_oracle_storage import build_trade_oracle_benchmark_store, build_trade_oracle_runtime_state_store
    from config import settings

    token = (settings.TRADE_ORACLE_TELEGRAM_BOT_TOKEN or "").strip()
    chat_id = (settings.TRADE_ORACLE_TELEGRAM_CHAT_ID or "").strip()
    if not token:
        raise SystemExit("Missing TRADE_ORACLE_TELEGRAM_BOT_TOKEN.")
    if not chat_id:
        raise SystemExit("Missing TRADE_ORACLE_TELEGRAM_CHAT_ID.")

    runtime_state_store = build_trade_oracle_runtime_state_store(backend=backend)
    benchmark_store = build_trade_oracle_benchmark_store(backend=backend)
    thread_id = f"telegram-live-test-{uuid4().hex}"
    run_id = f"telegram_live_test_{int(time.time() * 1000)}"
    cycle_id = f"cycle_{int(time.time() * 1000)}"

    telegram_client = HttpxTelegramBotClient(token, timeout_seconds=10)
    daemon = TradeOracleSingleRuntimeDaemon(
        runtime_state_store=runtime_state_store,
        benchmark_store=benchmark_store,
        orchestrator=_SafeResumeOrchestrator(thread_id),
        scanner_runner=lambda _watchlist: None,
        execution_client_factory=lambda: _SafeExecutionClient(),
        execution_backend="mt5",
        telegram_client=telegram_client,
        telegram_chat_id=chat_id,
        watchlist=[],
        send_cycle_summary=False,
        telegram_poll_timeout_seconds=5,
        idle_sleep_seconds=0.5,
    )

    try:
        record = {
            "thread_id": thread_id,
            "cycle_id": cycle_id,
            "run_id": run_id,
            "benchmark_variant": settings.TRADE_ORACLE_BENCHMARK_VARIANT,
            "review_status": "pending",
            "review_action": "PENDING",
            "telegram_chat_id": chat_id,
            "telegram_message_id": "",
            "symbol": "TELEGRAM/TEST",
            "direction": "BUY",
            "candidate": {},
            "review_context": {"reason": "live_telegram_diagnostic"},
            "account_state": {
                "current_balance": 10000.0,
                "highest_equity": 10000.0,
                "active_trades_count": 0,
                "source": "telegram_live_diagnostic",
            },
            "review_notes": "Safe Telegram review-flow diagnostic.",
            "cycle_outcome": "pending_review",
        }
        message_id = await daemon._send_review_prompt(record)
        record["telegram_message_id"] = message_id
        runtime_state_store.upsert_pending_review(record)

        deadline = time.monotonic() + max(5, int(wait_seconds))
        while time.monotonic() < deadline:
            await daemon.poll_telegram_once()
            resolved = runtime_state_store.get_pending_review(thread_id)
            if resolved is not None and resolved.review_status not in OPEN_REVIEW_STATUSES:
                journal = runtime_state_store.get_forward_journal_entry(cycle_id)
                return {
                    "thread_id": thread_id,
                    "cycle_id": cycle_id,
                    "run_id": run_id,
                    "message_id": message_id,
                    "resolved": True,
                    "review_status": resolved.review_status,
                    "review_action": resolved.review_action,
                    "cycle_outcome": resolved.cycle_outcome,
                    "journal_outcome": journal.outcome if journal is not None else "",
                }
            await asyncio.sleep(1.0)

        return {
            "thread_id": thread_id,
            "cycle_id": cycle_id,
            "run_id": run_id,
            "message_id": message_id,
            "resolved": False,
            "review_status": "pending",
            "review_action": "PENDING",
            "cycle_outcome": "pending_review",
            "journal_outcome": "",
        }
    finally:
        await telegram_client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely test the live Telegram review callback path.")
    parser.add_argument("--env-file", default=".env.n8n.local", help="Env file to load before the test.")
    parser.add_argument("--backend", default="supabase", choices=["sqlite", "supabase"], help="Runtime/benchmark backend to use for the diagnostic.")
    parser.add_argument("--wait-seconds", type=int, default=90, help="How long to wait for a callback click.")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(env_file=args.env_file, backend=args.backend, wait_seconds=args.wait_seconds)), indent=2))


if __name__ == "__main__":
    main()
