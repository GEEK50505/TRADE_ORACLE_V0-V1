"""Safe forward-test readiness checker for TRADE_ORACLE.

The default mode is intentionally offline and secret-safe:
- loads the requested env file before importing settings
- reports whether required values are present without printing secret values
- inspects local SQLite runtime state for open reviews
- does not poll Telegram, contact brokers, or transmit orders

Use --check-supabase only when a live Supabase table reachability probe is intended.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _present(name: str) -> dict[str, Any]:
    value = os.getenv(name, "")
    return {"name": name, "present": bool(str(value).strip())}


def _read_runtime_state(settings: Any, *, allow_remote: bool) -> dict[str, Any]:
    from ai.trade_oracle_daemon import OPEN_REVIEW_STATUSES
    from ai.trade_oracle_storage import build_trade_oracle_runtime_state_store

    if settings.TRADE_ORACLE_RUNTIME_STATE_BACKEND == "supabase" and not allow_remote:
        return {
            "ok": None,
            "backend": settings.TRADE_ORACLE_RUNTIME_STATE_BACKEND,
            "checked": False,
            "reason": "Skipped by default because Supabase runtime-state checking uses network credentials.",
            "open_review_count": None,
        }

    last_exc = None
    for attempt in range(2):
        try:
            store = build_trade_oracle_runtime_state_store(
                backend=settings.TRADE_ORACLE_RUNTIME_STATE_BACKEND,
            )
            open_reviews = []
            for status in sorted(OPEN_REVIEW_STATUSES):
                open_reviews.extend(store.list_pending_reviews(limit=20, review_status=status))
            checkpoint = store.get_daemon_checkpoint("telegram_update_offset")
            return {
                "ok": True,
                "backend": settings.TRADE_ORACLE_RUNTIME_STATE_BACKEND,
                "db_path": settings.TRADE_ORACLE_RUNTIME_STATE_DB_PATH
                if settings.TRADE_ORACLE_RUNTIME_STATE_BACKEND == "sqlite"
                else "",
                "open_review_count": len(open_reviews),
                "open_reviews": [
                    {
                        "thread_id": review.thread_id,
                        "cycle_id": review.cycle_id,
                        "symbol": review.symbol,
                        "status": review.review_status,
                        "updated_at_utc": review.updated_at_utc,
                    }
                    for review in open_reviews
                ],
                "telegram_update_offset_checkpoint_present": checkpoint is not None,
            }
        except Exception as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(1.0)
    return {
        "ok": False,
        "backend": settings.TRADE_ORACLE_RUNTIME_STATE_BACKEND,
        "error_type": type(last_exc).__name__ if last_exc is not None else "UnknownError",
        "message": str(last_exc) if last_exc is not None else "Unknown runtime-state error.",
    }


def _check_supabase_tables(settings: Any) -> dict[str, Any]:
    from ai.trade_oracle_supabase import build_trade_oracle_supabase_client, coerce_supabase_rows

    table_names = [
        settings.TRADE_ORACLE_SUPABASE_AUDIT_TABLE,
        settings.TRADE_ORACLE_SUPABASE_BENCHMARK_TABLE,
        settings.TRADE_ORACLE_SUPABASE_PENDING_REVIEW_TABLE,
        settings.TRADE_ORACLE_SUPABASE_FORWARD_JOURNAL_TABLE,
        settings.TRADE_ORACLE_SUPABASE_DAEMON_CHECKPOINT_TABLE,
    ]
    try:
        client = build_trade_oracle_supabase_client()
    except Exception as exc:
        return {
            "ok": False,
            "checked": False,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }

    tables = []
    for table_name in table_names:
        last_exc = None
        for attempt in range(2):
            try:
                rows = coerce_supabase_rows(client.table(table_name).select("*").limit(1).execute())
                tables.append({"table": table_name, "reachable": True, "sample_row_count": len(rows)})
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                if attempt == 0:
                    time.sleep(1.0)
        if last_exc is not None:
            tables.append(
                {
                    "table": table_name,
                    "reachable": False,
                    "error_type": type(last_exc).__name__,
                    "message": str(last_exc),
                }
            )
    return {"ok": all(row["reachable"] for row in tables), "checked": True, "tables": tables}


def build_report(*, env_file: str, check_supabase: bool) -> dict[str, Any]:
    env_path = REPO_ROOT / env_file
    load_dotenv(env_path, override=True)

    from config import settings

    execution_backend = settings.TRADE_ORACLE_EXECUTION_BACKEND
    required_env_names = [
        "TRADE_ORACLE_TELEGRAM_BOT_TOKEN",
        "TRADE_ORACLE_TELEGRAM_CHAT_ID",
        "SUPABASE_URL",
        "SUPABASE_KEY",
    ]
    if execution_backend == "mt5":
        required_env_names.extend(["MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER"])
    elif execution_backend == "match_trader":
        required_env_names.extend(["MATCH_TRADER_BROKER_ID", "MATCH_TRADER_USER", "MATCH_TRADER_PASS"])

    env_status = [_present(name) for name in required_env_names]
    missing = [item["name"] for item in env_status if not item["present"]]
    runtime_state = _read_runtime_state(settings, allow_remote=check_supabase)
    supabase = (
        _check_supabase_tables(settings)
        if check_supabase
        else {
            "ok": None,
            "checked": False,
            "reason": "Skipped by default. Re-run with --check-supabase for live table probing.",
        }
    )

    blockers: list[str] = []
    if missing:
        blockers.append("missing_required_env_values")
    open_review_count = runtime_state.get("open_review_count", 0)
    if isinstance(open_review_count, int) and open_review_count:
        blockers.append("open_pending_review")
    if runtime_state.get("ok") is False:
        blockers.append("runtime_state_probe_failed")
    if check_supabase and not supabase.get("ok"):
        blockers.append("supabase_table_probe_failed")

    startup_blockers = [item for item in blockers if item != "open_pending_review"]

    return {
        "service": "trade_oracle_forward_test_readiness",
        "env_file": str(env_path),
        "secret_values_printed": False,
        "execution_backend": execution_backend,
        "storage_backends": {
            "audit": settings.TRADE_ORACLE_AUDIT_BACKEND,
            "benchmark": settings.TRADE_ORACLE_BENCHMARK_BACKEND,
            "runtime_state": settings.TRADE_ORACLE_RUNTIME_STATE_BACKEND,
        },
        "telegram_long_polling_path": True,
        "n8n_role": "fallback_reference_only",
        "required_env": env_status,
        "missing_required_env": missing,
        "runtime_state": runtime_state,
        "supabase": supabase,
        "blockers": blockers,
        "startup_blockers": startup_blockers,
        "ready_for_supervised_poll_once": not missing,
        "ready_for_new_once_cycle": not missing and open_review_count == 0,
        "ready_for_forward_testing_start": len(startup_blockers) == 0,
        "notes": [
            "This check does not poll Telegram, call MT5/Match-Trader, or transmit orders.",
            "Resolve or intentionally account for open pending reviews before starting a new cycle.",
            "Use scripts/validate_mt5_demo_profile.py for safe MT5 account and symbol probing.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check TRADE_ORACLE forward-test readiness without printing secrets.")
    parser.add_argument("--env-file", default=".env.n8n.local", help="Env file to load before checking readiness.")
    parser.add_argument(
        "--check-supabase",
        action="store_true",
        help="Probe configured Supabase tables. This intentionally uses network credentials.",
    )
    args = parser.parse_args()
    print(json.dumps(build_report(env_file=args.env_file, check_supabase=args.check_supabase), indent=2))


if __name__ == "__main__":
    main()
