"""Migrate TRADE_ORACLE operational state from SQLite into Supabase via Postgres.

This uses the working session-pooler DB connection instead of the REST client so
larger state transfers do not fail on HTTP timeouts.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _connect_sqlite(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _rows(path: str, query: str) -> list[dict]:
    with _connect_sqlite(path) as connection:
        rows = connection.execute(query).fetchall()
    return [dict(row) for row in rows]


def _json_text(raw_value: str, default) -> str:
    if not raw_value:
        return json.dumps(default, ensure_ascii=True, sort_keys=True)
    parsed = json.loads(raw_value)
    return json.dumps(parsed, ensure_ascii=True, sort_keys=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate TRADE_ORACLE SQLite operational state into Supabase.")
    parser.add_argument("--env-file", default=".env.n8n.local", help="Env file to load before migrating.")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / args.env_file, override=True)

    from config import settings

    db_url = (os.getenv("SUPABASE_DB_URL") or "").strip()
    if not db_url:
        raise SystemExit("Missing SUPABASE_DB_URL.")

    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("psycopg is required for DB migration.") from exc

    audit_rows = _rows(
        settings.TRADE_ORACLE_AUDIT_DB_PATH,
        "SELECT event_id, created_at_utc, event_type, source, run_id, thread_id, status, payload_json FROM audit_events",
    )
    benchmark_rows = _rows(
        settings.TRADE_ORACLE_BENCHMARK_DB_PATH,
        """
        SELECT event_id, created_at_utc, event_type, source, cycle_id, run_id, thread_id,
               symbol, execution_backend, benchmark_variant, status, decision, payload_json
        FROM benchmark_events
        """,
    )
    pending_rows = _rows(
        settings.TRADE_ORACLE_RUNTIME_STATE_DB_PATH,
        """
        SELECT thread_id, cycle_id, run_id, benchmark_variant, review_status, review_action,
               telegram_chat_id, telegram_message_id, symbol, direction, candidate_json,
               review_context_json, account_state_json, created_at_utc, updated_at_utc,
               reviewer, review_notes, cycle_outcome
        FROM pending_reviews
        """,
    )
    journal_rows = _rows(
        settings.TRADE_ORACLE_RUNTIME_STATE_DB_PATH,
        """
        SELECT cycle_id, run_id, benchmark_variant, thread_id, workflow_name, stage, outcome,
               symbol, direction, pending_review, transmit_succeeded, benchmark_event_count,
               thread_ids_json, summary_json, updated_at_utc
        FROM forward_journal
        """,
    )
    checkpoint_rows = _rows(
        settings.TRADE_ORACLE_RUNTIME_STATE_DB_PATH,
        "SELECT checkpoint_key, checkpoint_value_json, updated_at_utc FROM daemon_checkpoints",
    )

    migrated = {
        "account_state": 0,
        "audit": 0,
        "benchmark": 0,
        "pending_reviews": 0,
        "forward_journal": 0,
        "daemon_checkpoints": 0,
    }

    with psycopg.connect(db_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO account_state (id, high_watermark)
                VALUES (%s, %s)
                ON CONFLICT (id) DO UPDATE SET high_watermark = EXCLUDED.high_watermark
                """,
                (1, float(settings.TRADE_ORACLE_HIGHEST_EQUITY)),
            )
            migrated["account_state"] = 1

            cursor.executemany(
                """
                INSERT INTO trade_oracle_audit_events (
                    event_id, created_at_utc, event_type, source, run_id, thread_id, status, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (event_id) DO UPDATE SET
                    created_at_utc = EXCLUDED.created_at_utc,
                    event_type = EXCLUDED.event_type,
                    source = EXCLUDED.source,
                    run_id = EXCLUDED.run_id,
                    thread_id = EXCLUDED.thread_id,
                    status = EXCLUDED.status,
                    payload = EXCLUDED.payload
                """,
                [
                    (
                        row["event_id"],
                        row["created_at_utc"],
                        row["event_type"],
                        row["source"],
                        row["run_id"],
                        row["thread_id"],
                        row["status"],
                        _json_text(row["payload_json"], {}),
                    )
                    for row in audit_rows
                ],
            )
            migrated["audit"] = len(audit_rows)

            cursor.executemany(
                """
                INSERT INTO trade_oracle_benchmark_events (
                    event_id, created_at_utc, event_type, source, cycle_id, run_id, thread_id,
                    symbol, execution_backend, benchmark_variant, status, decision, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (event_id) DO UPDATE SET
                    created_at_utc = EXCLUDED.created_at_utc,
                    event_type = EXCLUDED.event_type,
                    source = EXCLUDED.source,
                    cycle_id = EXCLUDED.cycle_id,
                    run_id = EXCLUDED.run_id,
                    thread_id = EXCLUDED.thread_id,
                    symbol = EXCLUDED.symbol,
                    execution_backend = EXCLUDED.execution_backend,
                    benchmark_variant = EXCLUDED.benchmark_variant,
                    status = EXCLUDED.status,
                    decision = EXCLUDED.decision,
                    payload = EXCLUDED.payload
                """,
                [
                    (
                        row["event_id"],
                        row["created_at_utc"],
                        row["event_type"],
                        row["source"],
                        row["cycle_id"],
                        row["run_id"],
                        row["thread_id"],
                        row["symbol"],
                        row["execution_backend"],
                        row["benchmark_variant"],
                        row["status"],
                        row["decision"],
                        _json_text(row["payload_json"], {}),
                    )
                    for row in benchmark_rows
                ],
            )
            migrated["benchmark"] = len(benchmark_rows)

            cursor.executemany(
                """
                INSERT INTO trade_oracle_pending_reviews (
                    thread_id, cycle_id, run_id, benchmark_variant, review_status, review_action,
                    telegram_chat_id, telegram_message_id, symbol, direction, candidate, review_context,
                    account_state, created_at_utc, updated_at_utc, reviewer, review_notes, cycle_outcome
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
                ON CONFLICT (thread_id) DO UPDATE SET
                    cycle_id = EXCLUDED.cycle_id,
                    run_id = EXCLUDED.run_id,
                    benchmark_variant = EXCLUDED.benchmark_variant,
                    review_status = EXCLUDED.review_status,
                    review_action = EXCLUDED.review_action,
                    telegram_chat_id = EXCLUDED.telegram_chat_id,
                    telegram_message_id = EXCLUDED.telegram_message_id,
                    symbol = EXCLUDED.symbol,
                    direction = EXCLUDED.direction,
                    candidate = EXCLUDED.candidate,
                    review_context = EXCLUDED.review_context,
                    account_state = EXCLUDED.account_state,
                    created_at_utc = EXCLUDED.created_at_utc,
                    updated_at_utc = EXCLUDED.updated_at_utc,
                    reviewer = EXCLUDED.reviewer,
                    review_notes = EXCLUDED.review_notes,
                    cycle_outcome = EXCLUDED.cycle_outcome
                """,
                [
                    (
                        row["thread_id"],
                        row["cycle_id"],
                        row["run_id"],
                        row["benchmark_variant"],
                        row["review_status"],
                        row["review_action"],
                        row["telegram_chat_id"],
                        row["telegram_message_id"],
                        row["symbol"],
                        row["direction"],
                        _json_text(row["candidate_json"], {}),
                        _json_text(row["review_context_json"], {}),
                        _json_text(row["account_state_json"], {}),
                        row["created_at_utc"],
                        row["updated_at_utc"],
                        row["reviewer"],
                        row["review_notes"],
                        row["cycle_outcome"],
                    )
                    for row in pending_rows
                ],
            )
            migrated["pending_reviews"] = len(pending_rows)

            cursor.executemany(
                """
                INSERT INTO trade_oracle_forward_journal (
                    cycle_id, run_id, benchmark_variant, thread_id, workflow_name, stage, outcome,
                    symbol, direction, pending_review, transmit_succeeded, benchmark_event_count,
                    thread_ids, summary, updated_at_utc
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                ON CONFLICT (cycle_id) DO UPDATE SET
                    run_id = EXCLUDED.run_id,
                    benchmark_variant = EXCLUDED.benchmark_variant,
                    thread_id = EXCLUDED.thread_id,
                    workflow_name = EXCLUDED.workflow_name,
                    stage = EXCLUDED.stage,
                    outcome = EXCLUDED.outcome,
                    symbol = EXCLUDED.symbol,
                    direction = EXCLUDED.direction,
                    pending_review = EXCLUDED.pending_review,
                    transmit_succeeded = EXCLUDED.transmit_succeeded,
                    benchmark_event_count = EXCLUDED.benchmark_event_count,
                    thread_ids = EXCLUDED.thread_ids,
                    summary = EXCLUDED.summary,
                    updated_at_utc = EXCLUDED.updated_at_utc
                """,
                [
                    (
                        row["cycle_id"],
                        row["run_id"],
                        row["benchmark_variant"],
                        row["thread_id"],
                        row["workflow_name"],
                        row["stage"],
                        row["outcome"],
                        row["symbol"],
                        row["direction"],
                        bool(row["pending_review"]),
                        bool(row["transmit_succeeded"]),
                        int(row["benchmark_event_count"]),
                        _json_text(row["thread_ids_json"], []),
                        _json_text(row["summary_json"], {}),
                        row["updated_at_utc"],
                    )
                    for row in journal_rows
                ],
            )
            migrated["forward_journal"] = len(journal_rows)

            cursor.executemany(
                """
                INSERT INTO trade_oracle_daemon_checkpoints (
                    checkpoint_key, checkpoint_value, updated_at_utc
                ) VALUES (%s, %s::jsonb, %s)
                ON CONFLICT (checkpoint_key) DO UPDATE SET
                    checkpoint_value = EXCLUDED.checkpoint_value,
                    updated_at_utc = EXCLUDED.updated_at_utc
                """,
                [
                    (
                        row["checkpoint_key"],
                        _json_text(row["checkpoint_value_json"], {}),
                        row["updated_at_utc"],
                    )
                    for row in checkpoint_rows
                ],
            )
            migrated["daemon_checkpoints"] = len(checkpoint_rows)

            cursor.execute("NOTIFY pgrst, 'reload schema'")

    print(migrated)


if __name__ == "__main__":
    main()
