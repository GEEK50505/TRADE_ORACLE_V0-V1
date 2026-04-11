"""Persistent audit/event store for the TRADE_ORACLE LangGraph stack."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from config import settings


class TradeOracleAuditEvent(BaseModel):
    """One persisted audit event emitted by the LangGraph platform stack."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    created_at_utc: str
    event_type: str
    source: str
    run_id: str = ""
    thread_id: str = ""
    status: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class TradeOracleAuditStore:
    """SQLite-backed audit/event store for LangGraph, review, and execution traces."""

    db_path: str | Path = settings.TRADE_ORACLE_AUDIT_DB_PATH

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
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    created_at_utc TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_events_created_at ON audit_events(created_at_utc DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_events_thread_id ON audit_events(thread_id, created_at_utc DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_events_run_id ON audit_events(run_id, created_at_utc DESC)"
            )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> TradeOracleAuditEvent:
        return TradeOracleAuditEvent(
            event_id=str(row["event_id"]),
            created_at_utc=str(row["created_at_utc"]),
            event_type=str(row["event_type"]),
            source=str(row["source"]),
            run_id=str(row["run_id"]),
            thread_id=str(row["thread_id"]),
            status=str(row["status"]),
            payload=json.loads(str(row["payload_json"])) if row["payload_json"] else {},
        )

    def record_event(
        self,
        *,
        event_type: str,
        source: str,
        payload: dict[str, Any] | None = None,
        run_id: str = "",
        thread_id: str = "",
        status: str = "",
    ) -> TradeOracleAuditEvent:
        event = TradeOracleAuditEvent(
            event_id=uuid4().hex,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            source=source,
            run_id=run_id,
            thread_id=thread_id,
            status=status,
            payload=payload or {},
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (
                    event_id,
                    created_at_utc,
                    event_type,
                    source,
                    run_id,
                    thread_id,
                    status,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.created_at_utc,
                    event.event_type,
                    event.source,
                    event.run_id,
                    event.thread_id,
                    event.status,
                    json.dumps(event.payload, ensure_ascii=True, sort_keys=True),
                ),
            )
        return event

    def list_recent_events(
        self,
        *,
        limit: int = 20,
        event_type: str = "",
        status: str = "",
    ) -> list[TradeOracleAuditEvent]:
        query = "SELECT * FROM audit_events"
        filters: list[str] = []
        params: list[Any] = []
        if event_type:
            filters.append("event_type = ?")
            params.append(event_type)
        if status:
            filters.append("status = ?")
            params.append(status)
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY created_at_utc DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_event(row) for row in rows]

    def list_thread_events(self, thread_id: str, *, limit: int = 100) -> list[TradeOracleAuditEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM audit_events
                WHERE thread_id = ?
                ORDER BY created_at_utc DESC
                LIMIT ?
                """,
                (thread_id, max(1, int(limit))),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]


__all__ = [
    "TradeOracleAuditEvent",
    "TradeOracleAuditStore",
]
