"""Unified runtime state store for daemon checkpoints, pending reviews, and journal rows."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from config import settings

from .trade_oracle_supabase import build_trade_oracle_supabase_client, coerce_supabase_rows


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(decoded) if isinstance(decoded, dict) else {}
    return {}


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(decoded, list):
            return [str(item) for item in decoded if str(item)]
    return []


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False


class TradeOraclePendingReviewRecord(BaseModel):
    """Persisted pending-review state shared across orchestration runtimes."""

    model_config = ConfigDict(extra="forbid")

    thread_id: str
    cycle_id: str = ""
    run_id: str = ""
    benchmark_variant: str = "super_brain"
    review_status: str = "pending"
    review_action: str = "PENDING"
    telegram_chat_id: str = ""
    telegram_message_id: str = ""
    symbol: str = ""
    direction: str = ""
    candidate: dict[str, Any] = Field(default_factory=dict)
    review_context: dict[str, Any] = Field(default_factory=dict)
    account_state: dict[str, Any] = Field(default_factory=dict)
    created_at_utc: str = ""
    updated_at_utc: str = ""
    reviewer: str = ""
    review_notes: str = ""
    cycle_outcome: str = "pending_review"


class TradeOracleForwardJournalRecord(BaseModel):
    """Persisted machine journal row for each forward-test cycle outcome."""

    model_config = ConfigDict(extra="forbid")

    cycle_id: str
    run_id: str = ""
    benchmark_variant: str = "super_brain"
    thread_id: str = ""
    workflow_name: str = ""
    stage: str = ""
    outcome: str = ""
    symbol: str = ""
    direction: str = ""
    pending_review: bool = False
    transmit_succeeded: bool = False
    benchmark_event_count: int = 0
    thread_ids: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    updated_at_utc: str = ""


class TradeOracleDaemonCheckpointRecord(BaseModel):
    """Persisted daemon checkpoint such as the Telegram polling cursor."""

    model_config = ConfigDict(extra="forbid")

    checkpoint_key: str
    checkpoint_value: dict[str, Any] = Field(default_factory=dict)
    updated_at_utc: str = ""


@dataclass(slots=True)
class TradeOracleRuntimeStateStore:
    """SQLite-backed runtime state store for daemon checkpoints, reviews, and journaling."""

    db_path: str | Path = settings.TRADE_ORACLE_RUNTIME_STATE_DB_PATH
    pending_review_table: str = "pending_reviews"
    forward_journal_table: str = "forward_journal"
    daemon_checkpoint_table: str = "daemon_checkpoints"

    def __post_init__(self) -> None:
        self.db_path = str(self.db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.pending_review_table} (
                    thread_id TEXT PRIMARY KEY,
                    cycle_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    benchmark_variant TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    review_action TEXT NOT NULL,
                    telegram_chat_id TEXT NOT NULL,
                    telegram_message_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    candidate_json TEXT NOT NULL,
                    review_context_json TEXT NOT NULL,
                    account_state_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    review_notes TEXT NOT NULL,
                    cycle_outcome TEXT NOT NULL
                )
                """
            )
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.pending_review_table}_status ON {self.pending_review_table}(review_status, updated_at_utc DESC)"
            )
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.pending_review_table}_cycle ON {self.pending_review_table}(cycle_id, updated_at_utc DESC)"
            )
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.forward_journal_table} (
                    cycle_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    benchmark_variant TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    workflow_name TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    pending_review INTEGER NOT NULL,
                    transmit_succeeded INTEGER NOT NULL,
                    benchmark_event_count INTEGER NOT NULL,
                    thread_ids_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                )
                """
            )
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.forward_journal_table}_updated ON {self.forward_journal_table}(updated_at_utc DESC)"
            )
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.forward_journal_table}_outcome ON {self.forward_journal_table}(outcome, updated_at_utc DESC)"
            )
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.daemon_checkpoint_table} (
                    checkpoint_key TEXT PRIMARY KEY,
                    checkpoint_value_json TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                )
                """
            )
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.daemon_checkpoint_table}_updated ON {self.daemon_checkpoint_table}(updated_at_utc DESC)"
            )

    @staticmethod
    def _row_to_pending_review(row: sqlite3.Row) -> TradeOraclePendingReviewRecord:
        return TradeOraclePendingReviewRecord(
            thread_id=str(row["thread_id"]),
            cycle_id=str(row["cycle_id"]),
            run_id=str(row["run_id"]),
            benchmark_variant=str(row["benchmark_variant"]),
            review_status=str(row["review_status"]),
            review_action=str(row["review_action"]),
            telegram_chat_id=str(row["telegram_chat_id"]),
            telegram_message_id=str(row["telegram_message_id"]),
            symbol=str(row["symbol"]),
            direction=str(row["direction"]),
            candidate=_coerce_dict(row["candidate_json"]),
            review_context=_coerce_dict(row["review_context_json"]),
            account_state=_coerce_dict(row["account_state_json"]),
            created_at_utc=str(row["created_at_utc"]),
            updated_at_utc=str(row["updated_at_utc"]),
            reviewer=str(row["reviewer"]),
            review_notes=str(row["review_notes"]),
            cycle_outcome=str(row["cycle_outcome"]),
        )

    @staticmethod
    def _row_to_forward_journal(row: sqlite3.Row) -> TradeOracleForwardJournalRecord:
        return TradeOracleForwardJournalRecord(
            cycle_id=str(row["cycle_id"]),
            run_id=str(row["run_id"]),
            benchmark_variant=str(row["benchmark_variant"]),
            thread_id=str(row["thread_id"]),
            workflow_name=str(row["workflow_name"]),
            stage=str(row["stage"]),
            outcome=str(row["outcome"]),
            symbol=str(row["symbol"]),
            direction=str(row["direction"]),
            pending_review=bool(row["pending_review"]),
            transmit_succeeded=bool(row["transmit_succeeded"]),
            benchmark_event_count=int(row["benchmark_event_count"]),
            thread_ids=_coerce_str_list(row["thread_ids_json"]),
            summary=_coerce_dict(row["summary_json"]),
            updated_at_utc=str(row["updated_at_utc"]),
        )

    @staticmethod
    def _row_to_daemon_checkpoint(row: sqlite3.Row) -> TradeOracleDaemonCheckpointRecord:
        return TradeOracleDaemonCheckpointRecord(
            checkpoint_key=str(row["checkpoint_key"]),
            checkpoint_value=_coerce_dict(row["checkpoint_value_json"]),
            updated_at_utc=str(row["updated_at_utc"]),
        )

    def get_pending_review(self, thread_id: str) -> TradeOraclePendingReviewRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM {self.pending_review_table} WHERE thread_id = ? LIMIT 1",
                (thread_id,),
            ).fetchone()
        return self._row_to_pending_review(row) if row else None

    def list_pending_reviews(
        self,
        *,
        limit: int = 50,
        review_status: str = "",
        symbol: str = "",
    ) -> list[TradeOraclePendingReviewRecord]:
        query = f"SELECT * FROM {self.pending_review_table}"
        filters: list[str] = []
        params: list[Any] = []
        if review_status:
            filters.append("review_status = ?")
            params.append(review_status)
        if symbol:
            filters.append("symbol = ?")
            params.append(symbol)
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY updated_at_utc DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_pending_review(row) for row in rows]

    def upsert_pending_review(
        self,
        record: TradeOraclePendingReviewRecord | dict[str, Any],
    ) -> TradeOraclePendingReviewRecord:
        existing = None
        normalized = (
            record
            if isinstance(record, TradeOraclePendingReviewRecord)
            else TradeOraclePendingReviewRecord.model_validate(record)
        )
        if normalized.thread_id:
            existing = self.get_pending_review(normalized.thread_id)
        now = _utcnow_iso()
        normalized = normalized.model_copy(
            update={
                "created_at_utc": normalized.created_at_utc or (existing.created_at_utc if existing else now),
                "updated_at_utc": normalized.updated_at_utc or now,
            }
        )
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO {self.pending_review_table} (
                    thread_id, cycle_id, run_id, benchmark_variant, review_status, review_action,
                    telegram_chat_id, telegram_message_id, symbol, direction,
                    candidate_json, review_context_json, account_state_json,
                    created_at_utc, updated_at_utc, reviewer, review_notes, cycle_outcome
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    cycle_id=excluded.cycle_id,
                    run_id=excluded.run_id,
                    benchmark_variant=excluded.benchmark_variant,
                    review_status=excluded.review_status,
                    review_action=excluded.review_action,
                    telegram_chat_id=excluded.telegram_chat_id,
                    telegram_message_id=excluded.telegram_message_id,
                    symbol=excluded.symbol,
                    direction=excluded.direction,
                    candidate_json=excluded.candidate_json,
                    review_context_json=excluded.review_context_json,
                    account_state_json=excluded.account_state_json,
                    created_at_utc=excluded.created_at_utc,
                    updated_at_utc=excluded.updated_at_utc,
                    reviewer=excluded.reviewer,
                    review_notes=excluded.review_notes,
                    cycle_outcome=excluded.cycle_outcome
                """,
                (
                    normalized.thread_id,
                    normalized.cycle_id,
                    normalized.run_id,
                    normalized.benchmark_variant,
                    normalized.review_status,
                    normalized.review_action,
                    normalized.telegram_chat_id,
                    normalized.telegram_message_id,
                    normalized.symbol,
                    normalized.direction,
                    json.dumps(normalized.candidate, ensure_ascii=True, sort_keys=True),
                    json.dumps(normalized.review_context, ensure_ascii=True, sort_keys=True),
                    json.dumps(normalized.account_state, ensure_ascii=True, sort_keys=True),
                    normalized.created_at_utc,
                    normalized.updated_at_utc,
                    normalized.reviewer,
                    normalized.review_notes,
                    normalized.cycle_outcome,
                ),
            )
        return normalized

    def resolve_pending_review(
        self,
        thread_id: str,
        *,
        review_action: str,
        review_status: str = "resolved",
        reviewer: str = "",
        review_notes: str = "",
        telegram_message_id: str | None = None,
        cycle_outcome: str | None = None,
    ) -> TradeOraclePendingReviewRecord | None:
        existing = self.get_pending_review(thread_id)
        if existing is None:
            return None
        updates: dict[str, Any] = {
            "review_action": review_action,
            "review_status": review_status,
            "reviewer": reviewer or existing.reviewer,
            "review_notes": review_notes or existing.review_notes,
            "updated_at_utc": _utcnow_iso(),
            "cycle_outcome": cycle_outcome or existing.cycle_outcome,
        }
        if telegram_message_id is not None:
            updates["telegram_message_id"] = telegram_message_id
        return self.upsert_pending_review(existing.model_copy(update=updates))

    def get_forward_journal_entry(self, cycle_id: str) -> TradeOracleForwardJournalRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM {self.forward_journal_table} WHERE cycle_id = ? LIMIT 1",
                (cycle_id,),
            ).fetchone()
        return self._row_to_forward_journal(row) if row else None

    def list_forward_journal_entries(
        self,
        *,
        limit: int = 50,
        outcome: str = "",
        pending_review: bool | None = None,
    ) -> list[TradeOracleForwardJournalRecord]:
        query = f"SELECT * FROM {self.forward_journal_table}"
        filters: list[str] = []
        params: list[Any] = []
        if outcome:
            filters.append("outcome = ?")
            params.append(outcome)
        if pending_review is not None:
            filters.append("pending_review = ?")
            params.append(1 if pending_review else 0)
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY updated_at_utc DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_forward_journal(row) for row in rows]

    def upsert_forward_journal_entry(
        self,
        record: TradeOracleForwardJournalRecord | dict[str, Any],
    ) -> TradeOracleForwardJournalRecord:
        normalized = (
            record
            if isinstance(record, TradeOracleForwardJournalRecord)
            else TradeOracleForwardJournalRecord.model_validate(record)
        )
        normalized = normalized.model_copy(update={"updated_at_utc": normalized.updated_at_utc or _utcnow_iso()})
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO {self.forward_journal_table} (
                    cycle_id, run_id, benchmark_variant, thread_id, workflow_name, stage, outcome,
                    symbol, direction, pending_review, transmit_succeeded, benchmark_event_count,
                    thread_ids_json, summary_json, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cycle_id) DO UPDATE SET
                    run_id=excluded.run_id,
                    benchmark_variant=excluded.benchmark_variant,
                    thread_id=excluded.thread_id,
                    workflow_name=excluded.workflow_name,
                    stage=excluded.stage,
                    outcome=excluded.outcome,
                    symbol=excluded.symbol,
                    direction=excluded.direction,
                    pending_review=excluded.pending_review,
                    transmit_succeeded=excluded.transmit_succeeded,
                    benchmark_event_count=excluded.benchmark_event_count,
                    thread_ids_json=excluded.thread_ids_json,
                    summary_json=excluded.summary_json,
                    updated_at_utc=excluded.updated_at_utc
                """,
                (
                    normalized.cycle_id,
                    normalized.run_id,
                    normalized.benchmark_variant,
                    normalized.thread_id,
                    normalized.workflow_name,
                    normalized.stage,
                    normalized.outcome,
                    normalized.symbol,
                    normalized.direction,
                    1 if normalized.pending_review else 0,
                    1 if normalized.transmit_succeeded else 0,
                    normalized.benchmark_event_count,
                    json.dumps(normalized.thread_ids, ensure_ascii=True),
                    json.dumps(normalized.summary, ensure_ascii=True, sort_keys=True),
                    normalized.updated_at_utc,
                ),
            )
        return normalized

    def get_daemon_checkpoint(self, checkpoint_key: str) -> TradeOracleDaemonCheckpointRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM {self.daemon_checkpoint_table} WHERE checkpoint_key = ? LIMIT 1",
                (checkpoint_key,),
            ).fetchone()
        return self._row_to_daemon_checkpoint(row) if row else None

    def upsert_daemon_checkpoint(
        self,
        record: TradeOracleDaemonCheckpointRecord | dict[str, Any],
    ) -> TradeOracleDaemonCheckpointRecord:
        normalized = (
            record
            if isinstance(record, TradeOracleDaemonCheckpointRecord)
            else TradeOracleDaemonCheckpointRecord.model_validate(record)
        )
        normalized = normalized.model_copy(update={"updated_at_utc": normalized.updated_at_utc or _utcnow_iso()})
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO {self.daemon_checkpoint_table} (
                    checkpoint_key, checkpoint_value_json, updated_at_utc
                ) VALUES (?, ?, ?)
                ON CONFLICT(checkpoint_key) DO UPDATE SET
                    checkpoint_value_json=excluded.checkpoint_value_json,
                    updated_at_utc=excluded.updated_at_utc
                """,
                (
                    normalized.checkpoint_key,
                    json.dumps(normalized.checkpoint_value, ensure_ascii=True, sort_keys=True),
                    normalized.updated_at_utc,
                ),
            )
        return normalized


@dataclass(slots=True)
class TradeOracleSupabaseRuntimeStateStore:
    """Supabase-backed runtime state store for daemon checkpoints, reviews, and journaling."""

    pending_review_table: str = settings.TRADE_ORACLE_SUPABASE_PENDING_REVIEW_TABLE
    forward_journal_table: str = settings.TRADE_ORACLE_SUPABASE_FORWARD_JOURNAL_TABLE
    daemon_checkpoint_table: str = settings.TRADE_ORACLE_SUPABASE_DAEMON_CHECKPOINT_TABLE
    supabase_client: Any | None = None

    def __post_init__(self) -> None:
        if self.supabase_client is None:
            self.supabase_client = build_trade_oracle_supabase_client()

    @staticmethod
    def _row_to_pending_review(row: dict[str, Any]) -> TradeOraclePendingReviewRecord:
        return TradeOraclePendingReviewRecord(
            thread_id=str(row.get("thread_id", "")),
            cycle_id=str(row.get("cycle_id", "")),
            run_id=str(row.get("run_id", "")),
            benchmark_variant=str(row.get("benchmark_variant", "super_brain") or "super_brain"),
            review_status=str(row.get("review_status", "pending") or "pending"),
            review_action=str(row.get("review_action", "PENDING") or "PENDING"),
            telegram_chat_id=str(row.get("telegram_chat_id", "")),
            telegram_message_id=str(row.get("telegram_message_id", "")),
            symbol=str(row.get("symbol", "")),
            direction=str(row.get("direction", "")),
            candidate=_coerce_dict(row.get("candidate")),
            review_context=_coerce_dict(row.get("review_context")),
            account_state=_coerce_dict(row.get("account_state")),
            created_at_utc=str(row.get("created_at_utc", "")),
            updated_at_utc=str(row.get("updated_at_utc", "")),
            reviewer=str(row.get("reviewer", "")),
            review_notes=str(row.get("review_notes", "")),
            cycle_outcome=str(row.get("cycle_outcome", "pending_review") or "pending_review"),
        )

    @staticmethod
    def _row_to_forward_journal(row: dict[str, Any]) -> TradeOracleForwardJournalRecord:
        return TradeOracleForwardJournalRecord(
            cycle_id=str(row.get("cycle_id", "")),
            run_id=str(row.get("run_id", "")),
            benchmark_variant=str(row.get("benchmark_variant", "super_brain") or "super_brain"),
            thread_id=str(row.get("thread_id", "")),
            workflow_name=str(row.get("workflow_name", "")),
            stage=str(row.get("stage", "")),
            outcome=str(row.get("outcome", "")),
            symbol=str(row.get("symbol", "")),
            direction=str(row.get("direction", "")),
            pending_review=_coerce_bool(row.get("pending_review")),
            transmit_succeeded=_coerce_bool(row.get("transmit_succeeded")),
            benchmark_event_count=int(row.get("benchmark_event_count", 0) or 0),
            thread_ids=_coerce_str_list(row.get("thread_ids")),
            summary=_coerce_dict(row.get("summary")),
            updated_at_utc=str(row.get("updated_at_utc", "")),
        )

    @staticmethod
    def _row_to_daemon_checkpoint(row: dict[str, Any]) -> TradeOracleDaemonCheckpointRecord:
        return TradeOracleDaemonCheckpointRecord(
            checkpoint_key=str(row.get("checkpoint_key", "")),
            checkpoint_value=_coerce_dict(row.get("checkpoint_value")),
            updated_at_utc=str(row.get("updated_at_utc", "")),
        )

    def get_pending_review(self, thread_id: str) -> TradeOraclePendingReviewRecord | None:
        rows = coerce_supabase_rows(
            self.supabase_client.table(self.pending_review_table)
            .select("*")
            .eq("thread_id", thread_id)
            .limit(1)
            .execute()
        )
        return self._row_to_pending_review(rows[0]) if rows else None

    def list_pending_reviews(
        self,
        *,
        limit: int = 50,
        review_status: str = "",
        symbol: str = "",
    ) -> list[TradeOraclePendingReviewRecord]:
        query = self.supabase_client.table(self.pending_review_table).select("*")
        if review_status:
            query = query.eq("review_status", review_status)
        if symbol:
            query = query.eq("symbol", symbol)
        rows = coerce_supabase_rows(query.order("updated_at_utc", desc=True).limit(max(1, int(limit))).execute())
        return [self._row_to_pending_review(row) for row in rows]

    def upsert_pending_review(
        self,
        record: TradeOraclePendingReviewRecord | dict[str, Any],
    ) -> TradeOraclePendingReviewRecord:
        existing = None
        normalized = (
            record
            if isinstance(record, TradeOraclePendingReviewRecord)
            else TradeOraclePendingReviewRecord.model_validate(record)
        )
        if normalized.thread_id:
            existing = self.get_pending_review(normalized.thread_id)
        now = _utcnow_iso()
        normalized = normalized.model_copy(
            update={
                "created_at_utc": normalized.created_at_utc or (existing.created_at_utc if existing else now),
                "updated_at_utc": normalized.updated_at_utc or now,
            }
        )
        response = (
            self.supabase_client.table(self.pending_review_table)
            .upsert(
                {
                    "thread_id": normalized.thread_id,
                    "cycle_id": normalized.cycle_id,
                    "run_id": normalized.run_id,
                    "benchmark_variant": normalized.benchmark_variant,
                    "review_status": normalized.review_status,
                    "review_action": normalized.review_action,
                    "telegram_chat_id": normalized.telegram_chat_id,
                    "telegram_message_id": normalized.telegram_message_id,
                    "symbol": normalized.symbol,
                    "direction": normalized.direction,
                    "candidate": normalized.candidate,
                    "review_context": normalized.review_context,
                    "account_state": normalized.account_state,
                    "created_at_utc": normalized.created_at_utc,
                    "updated_at_utc": normalized.updated_at_utc,
                    "reviewer": normalized.reviewer,
                    "review_notes": normalized.review_notes,
                    "cycle_outcome": normalized.cycle_outcome,
                },
                on_conflict="thread_id",
            )
            .execute()
        )
        rows = coerce_supabase_rows(response)
        return self._row_to_pending_review(rows[0]) if rows else normalized

    def resolve_pending_review(
        self,
        thread_id: str,
        *,
        review_action: str,
        review_status: str = "resolved",
        reviewer: str = "",
        review_notes: str = "",
        telegram_message_id: str | None = None,
        cycle_outcome: str | None = None,
    ) -> TradeOraclePendingReviewRecord | None:
        existing = self.get_pending_review(thread_id)
        if existing is None:
            return None
        updates: dict[str, Any] = {
            "review_action": review_action,
            "review_status": review_status,
            "reviewer": reviewer or existing.reviewer,
            "review_notes": review_notes or existing.review_notes,
            "updated_at_utc": _utcnow_iso(),
            "cycle_outcome": cycle_outcome or existing.cycle_outcome,
        }
        if telegram_message_id is not None:
            updates["telegram_message_id"] = telegram_message_id
        return self.upsert_pending_review(existing.model_copy(update=updates))

    def get_forward_journal_entry(self, cycle_id: str) -> TradeOracleForwardJournalRecord | None:
        rows = coerce_supabase_rows(
            self.supabase_client.table(self.forward_journal_table)
            .select("*")
            .eq("cycle_id", cycle_id)
            .limit(1)
            .execute()
        )
        return self._row_to_forward_journal(rows[0]) if rows else None

    def list_forward_journal_entries(
        self,
        *,
        limit: int = 50,
        outcome: str = "",
        pending_review: bool | None = None,
    ) -> list[TradeOracleForwardJournalRecord]:
        query = self.supabase_client.table(self.forward_journal_table).select("*")
        if outcome:
            query = query.eq("outcome", outcome)
        if pending_review is not None:
            query = query.eq("pending_review", pending_review)
        rows = coerce_supabase_rows(query.order("updated_at_utc", desc=True).limit(max(1, int(limit))).execute())
        return [self._row_to_forward_journal(row) for row in rows]

    def upsert_forward_journal_entry(
        self,
        record: TradeOracleForwardJournalRecord | dict[str, Any],
    ) -> TradeOracleForwardJournalRecord:
        normalized = (
            record
            if isinstance(record, TradeOracleForwardJournalRecord)
            else TradeOracleForwardJournalRecord.model_validate(record)
        )
        normalized = normalized.model_copy(update={"updated_at_utc": normalized.updated_at_utc or _utcnow_iso()})
        response = (
            self.supabase_client.table(self.forward_journal_table)
            .upsert(
                {
                    "cycle_id": normalized.cycle_id,
                    "run_id": normalized.run_id,
                    "benchmark_variant": normalized.benchmark_variant,
                    "thread_id": normalized.thread_id,
                    "workflow_name": normalized.workflow_name,
                    "stage": normalized.stage,
                    "outcome": normalized.outcome,
                    "symbol": normalized.symbol,
                    "direction": normalized.direction,
                    "pending_review": normalized.pending_review,
                    "transmit_succeeded": normalized.transmit_succeeded,
                    "benchmark_event_count": normalized.benchmark_event_count,
                    "thread_ids": normalized.thread_ids,
                    "summary": normalized.summary,
                    "updated_at_utc": normalized.updated_at_utc,
                },
                on_conflict="cycle_id",
            )
            .execute()
        )
        rows = coerce_supabase_rows(response)
        return self._row_to_forward_journal(rows[0]) if rows else normalized

    def get_daemon_checkpoint(self, checkpoint_key: str) -> TradeOracleDaemonCheckpointRecord | None:
        rows = coerce_supabase_rows(
            self.supabase_client.table(self.daemon_checkpoint_table)
            .select("*")
            .eq("checkpoint_key", checkpoint_key)
            .limit(1)
            .execute()
        )
        return self._row_to_daemon_checkpoint(rows[0]) if rows else None

    def upsert_daemon_checkpoint(
        self,
        record: TradeOracleDaemonCheckpointRecord | dict[str, Any],
    ) -> TradeOracleDaemonCheckpointRecord:
        normalized = (
            record
            if isinstance(record, TradeOracleDaemonCheckpointRecord)
            else TradeOracleDaemonCheckpointRecord.model_validate(record)
        )
        normalized = normalized.model_copy(update={"updated_at_utc": normalized.updated_at_utc or _utcnow_iso()})
        response = (
            self.supabase_client.table(self.daemon_checkpoint_table)
            .upsert(
                {
                    "checkpoint_key": normalized.checkpoint_key,
                    "checkpoint_value": normalized.checkpoint_value,
                    "updated_at_utc": normalized.updated_at_utc,
                },
                on_conflict="checkpoint_key",
            )
            .execute()
        )
        rows = coerce_supabase_rows(response)
        return self._row_to_daemon_checkpoint(rows[0]) if rows else normalized


__all__ = [
    "TradeOracleDaemonCheckpointRecord",
    "TradeOracleForwardJournalRecord",
    "TradeOraclePendingReviewRecord",
    "TradeOracleRuntimeStateStore",
    "TradeOracleSupabaseRuntimeStateStore",
]
