"""Resolve a persisted pending review in SQLite and/or Supabase runtime state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _resolve_for_backend(
    *,
    backend: str,
    thread_id: str,
    review_action: str,
    review_status: str,
    reviewer: str,
    review_notes: str,
    cycle_outcome: str,
) -> dict[str, Any]:
    from ai.trade_oracle_storage import build_trade_oracle_runtime_state_store

    store = build_trade_oracle_runtime_state_store(backend=backend)
    before = store.get_pending_review(thread_id)
    if before is None:
        return {"backend": backend, "found": False, "resolved": False}
    after = store.resolve_pending_review(
        thread_id,
        review_action=review_action,
        review_status=review_status,
        reviewer=reviewer,
        review_notes=review_notes,
        cycle_outcome=cycle_outcome,
    )
    return {
        "backend": backend,
        "found": True,
        "resolved": after is not None and after.review_status == review_status,
        "thread_id": thread_id,
        "symbol": before.symbol,
        "previous_status": before.review_status,
        "current_status": after.review_status if after is not None else "",
        "current_action": after.review_action if after is not None else "",
        "cycle_outcome": after.cycle_outcome if after is not None else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve a persisted TRADE_ORACLE pending review.")
    parser.add_argument("--env-file", default=".env.n8n.local", help="Env file to load before resolving.")
    parser.add_argument("--thread-id", required=True, help="Thread ID of the review to resolve.")
    parser.add_argument(
        "--backend",
        choices=("sqlite", "supabase", "both"),
        default="both",
        help="Which runtime-state backend to update.",
    )
    parser.add_argument("--review-action", default="REJECT", help="Final review action label.")
    parser.add_argument("--review-status", default="resolved", help="Final review status.")
    parser.add_argument("--reviewer", default="codex", help="Reviewer name recorded on the review row.")
    parser.add_argument("--review-notes", default="Resolved stale pending review during daemon cutover finalization.")
    parser.add_argument("--cycle-outcome", default="no_trade", help="Final cycle outcome.")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / args.env_file, override=True)

    backends = ("sqlite", "supabase") if args.backend == "both" else (args.backend,)
    results = [
        _resolve_for_backend(
            backend=backend,
            thread_id=args.thread_id,
            review_action=args.review_action,
            review_status=args.review_status,
            reviewer=args.reviewer,
            review_notes=args.review_notes,
            cycle_outcome=args.cycle_outcome,
        )
        for backend in backends
    ]
    print(json.dumps({"thread_id": args.thread_id, "results": results}, indent=2))


if __name__ == "__main__":
    main()
