"""Persistent benchmark/event store for forward-testing and Super Brain measurement."""

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


class TradeOracleBenchmarkEvent(BaseModel):
    """One persisted benchmark event emitted by the platform stack."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    created_at_utc: str
    event_type: str
    source: str
    cycle_id: str = ""
    run_id: str = ""
    thread_id: str = ""
    symbol: str = ""
    execution_backend: str = ""
    benchmark_variant: str = ""
    status: str = ""
    decision: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class TradeOracleBenchmarkStore:
    """SQLite-backed benchmark/event store for forward-testing measurements."""

    db_path: str | Path = settings.TRADE_ORACLE_BENCHMARK_DB_PATH

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
                CREATE TABLE IF NOT EXISTS benchmark_events (
                    event_id TEXT PRIMARY KEY,
                    created_at_utc TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    cycle_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    execution_backend TEXT NOT NULL,
                    benchmark_variant TEXT NOT NULL,
                    status TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_benchmark_events_created_at ON benchmark_events(created_at_utc DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_benchmark_events_cycle_id ON benchmark_events(cycle_id, created_at_utc DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_benchmark_events_run_id ON benchmark_events(run_id, created_at_utc DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_benchmark_events_thread_id ON benchmark_events(thread_id, created_at_utc DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_benchmark_events_variant ON benchmark_events(benchmark_variant, created_at_utc DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_benchmark_events_symbol ON benchmark_events(symbol, created_at_utc DESC)"
            )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> TradeOracleBenchmarkEvent:
        return TradeOracleBenchmarkEvent(
            event_id=str(row["event_id"]),
            created_at_utc=str(row["created_at_utc"]),
            event_type=str(row["event_type"]),
            source=str(row["source"]),
            cycle_id=str(row["cycle_id"]),
            run_id=str(row["run_id"]),
            thread_id=str(row["thread_id"]),
            symbol=str(row["symbol"]),
            execution_backend=str(row["execution_backend"]),
            benchmark_variant=str(row["benchmark_variant"]),
            status=str(row["status"]),
            decision=str(row["decision"]),
            payload=json.loads(str(row["payload_json"])) if row["payload_json"] else {},
        )

    def record_event(
        self,
        *,
        event_type: str,
        source: str,
        payload: dict[str, Any] | None = None,
        cycle_id: str = "",
        run_id: str = "",
        thread_id: str = "",
        symbol: str = "",
        execution_backend: str = "",
        benchmark_variant: str = "",
        status: str = "",
        decision: str = "",
    ) -> TradeOracleBenchmarkEvent:
        event = TradeOracleBenchmarkEvent(
            event_id=uuid4().hex,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            source=source,
            cycle_id=cycle_id,
            run_id=run_id,
            thread_id=thread_id,
            symbol=symbol,
            execution_backend=execution_backend,
            benchmark_variant=benchmark_variant,
            status=status,
            decision=decision,
            payload=payload or {},
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO benchmark_events (
                    event_id,
                    created_at_utc,
                    event_type,
                    source,
                    cycle_id,
                    run_id,
                    thread_id,
                    symbol,
                    execution_backend,
                    benchmark_variant,
                    status,
                    decision,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.created_at_utc,
                    event.event_type,
                    event.source,
                    event.cycle_id,
                    event.run_id,
                    event.thread_id,
                    event.symbol,
                    event.execution_backend,
                    event.benchmark_variant,
                    event.status,
                    event.decision,
                    json.dumps(event.payload, ensure_ascii=True, sort_keys=True),
                ),
            )
        return event

    def list_recent_events(
        self,
        *,
        limit: int = 20,
        event_type: str = "",
        benchmark_variant: str = "",
        cycle_id: str = "",
        status: str = "",
    ) -> list[TradeOracleBenchmarkEvent]:
        query = "SELECT * FROM benchmark_events"
        filters: list[str] = []
        params: list[Any] = []
        if event_type:
            filters.append("event_type = ?")
            params.append(event_type)
        if benchmark_variant:
            filters.append("benchmark_variant = ?")
            params.append(benchmark_variant)
        if cycle_id:
            filters.append("cycle_id = ?")
            params.append(cycle_id)
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

    def list_cycle_events(self, cycle_id: str, *, limit: int = 100) -> list[TradeOracleBenchmarkEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM benchmark_events
                WHERE cycle_id = ?
                ORDER BY created_at_utc DESC
                LIMIT ?
                """,
                (cycle_id, max(1, int(limit))),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def build_summary(
        self,
        *,
        benchmark_variant: str = "",
        execution_backend: str = "",
    ) -> dict[str, Any]:
        filters: list[str] = []
        params: list[Any] = []
        if benchmark_variant:
            filters.append("benchmark_variant = ?")
            params.append(benchmark_variant)
        if execution_backend:
            filters.append("execution_backend = ?")
            params.append(execution_backend)

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        query = f"""
            SELECT
                COUNT(*) AS total_events,
                COUNT(DISTINCT CASE WHEN cycle_id <> '' THEN cycle_id END) AS total_cycles,
                COUNT(DISTINCT CASE WHEN run_id <> '' THEN run_id END) AS total_runs,
                COUNT(DISTINCT CASE WHEN symbol <> '' THEN symbol END) AS total_symbols,
                SUM(CASE WHEN event_type = 'scanner_cycle' THEN 1 ELSE 0 END) AS scanner_cycles,
                SUM(CASE WHEN event_type = 'super_brain_run' THEN 1 ELSE 0 END) AS super_brain_runs,
                SUM(CASE WHEN event_type = 'super_brain_resume' THEN 1 ELSE 0 END) AS super_brain_resumes,
                SUM(CASE WHEN event_type = 'risk_check' THEN 1 ELSE 0 END) AS risk_checks,
                SUM(CASE WHEN event_type = 'order_transmit_attempt' THEN 1 ELSE 0 END) AS transmit_attempts,
                SUM(CASE WHEN event_type = 'order_transmit_result' AND decision = 'transmitted' THEN 1 ELSE 0 END) AS transmit_successes,
                SUM(CASE WHEN event_type = 'order_transmit_result' AND decision = 'not_transmitted' THEN 1 ELSE 0 END) AS transmit_rejections,
                SUM(CASE WHEN event_type = 'super_brain_run' AND decision = 'pending_review' THEN 1 ELSE 0 END) AS pending_review_runs,
                SUM(CASE WHEN event_type = 'super_brain_run' AND decision = 'approved_candidate_ready' THEN 1 ELSE 0 END) AS approved_candidate_runs,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS error_events,
                MAX(created_at_utc) AS latest_event_at_utc
            FROM benchmark_events
            {where_clause}
        """

        with self._connect() as connection:
            row = connection.execute(query, params).fetchone()

        def _int(name: str) -> int:
            value = row[name] if row is not None else 0
            return int(value or 0)

        transmit_attempts = _int("transmit_attempts")
        transmit_successes = _int("transmit_successes")
        broker_acceptance_rate = (
            round(transmit_successes / transmit_attempts, 6) if transmit_attempts > 0 else 0.0
        )

        return {
            "total_events": _int("total_events"),
            "total_cycles": _int("total_cycles"),
            "total_runs": _int("total_runs"),
            "total_symbols": _int("total_symbols"),
            "scanner_cycles": _int("scanner_cycles"),
            "super_brain_runs": _int("super_brain_runs"),
            "super_brain_resumes": _int("super_brain_resumes"),
            "risk_checks": _int("risk_checks"),
            "transmit_attempts": transmit_attempts,
            "transmit_successes": transmit_successes,
            "transmit_rejections": _int("transmit_rejections"),
            "pending_review_runs": _int("pending_review_runs"),
            "approved_candidate_runs": _int("approved_candidate_runs"),
            "error_events": _int("error_events"),
            "broker_acceptance_rate": broker_acceptance_rate,
            "benchmark_variant": benchmark_variant,
            "execution_backend": execution_backend,
            "latest_event_at_utc": str(row["latest_event_at_utc"] or "") if row is not None else "",
        }

    def list_recent_cycle_summaries(
        self,
        *,
        limit: int = 20,
        benchmark_variant: str = "",
        execution_backend: str = "",
        fetch_limit: int | None = None,
    ) -> list[dict[str, Any]]:
        filters: list[str] = ["cycle_id <> ''"]
        params: list[Any] = []
        if benchmark_variant:
            filters.append("benchmark_variant = ?")
            params.append(benchmark_variant)
        if execution_backend:
            filters.append("execution_backend = ?")
            params.append(execution_backend)

        window_size = fetch_limit if fetch_limit is not None else max(100, int(limit) * 40)
        query = (
            "SELECT * FROM benchmark_events "
            f"WHERE {' AND '.join(filters)} "
            "ORDER BY created_at_utc DESC LIMIT ?"
        )
        params.append(window_size)

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()

        summaries: dict[str, dict[str, Any]] = {}
        ordered_cycle_ids: list[str] = []

        for row in rows:
            cycle_id = str(row["cycle_id"])
            if cycle_id not in summaries:
                ordered_cycle_ids.append(cycle_id)
                summaries[cycle_id] = {
                    "cycle_id": cycle_id,
                    "latest_event_at_utc": str(row["created_at_utc"]),
                    "latest_event_type": str(row["event_type"]),
                    "latest_status": str(row["status"]),
                    "latest_decision": str(row["decision"]),
                    "benchmark_variant": str(row["benchmark_variant"]),
                    "execution_backends": set(),
                    "symbols": set(),
                    "run_ids": set(),
                    "thread_ids": set(),
                    "event_types": set(),
                    "event_count": 0,
                    "pending_review": False,
                    "approved_candidate_ready": False,
                    "transmit_attempted": False,
                    "transmit_succeeded": False,
                    "error_event_count": 0,
                }

            summary = summaries[cycle_id]
            summary["event_count"] += 1
            if str(row["execution_backend"]):
                summary["execution_backends"].add(str(row["execution_backend"]))
            if str(row["symbol"]):
                summary["symbols"].add(str(row["symbol"]))
            if str(row["run_id"]):
                summary["run_ids"].add(str(row["run_id"]))
            if str(row["thread_id"]):
                summary["thread_ids"].add(str(row["thread_id"]))
            summary["event_types"].add(str(row["event_type"]))
            if str(row["event_type"]) == "super_brain_run" and str(row["decision"]) == "pending_review":
                summary["pending_review"] = True
            if str(row["event_type"]) == "super_brain_run" and str(row["decision"]) == "approved_candidate_ready":
                summary["approved_candidate_ready"] = True
            if str(row["event_type"]) == "order_transmit_attempt":
                summary["transmit_attempted"] = True
            if str(row["event_type"]) == "order_transmit_result" and str(row["decision"]) == "transmitted":
                summary["transmit_succeeded"] = True
            if str(row["status"]) == "error":
                summary["error_event_count"] += 1

        results: list[dict[str, Any]] = []
        for cycle_id in ordered_cycle_ids[: max(1, int(limit))]:
            summary = summaries[cycle_id]
            results.append(
                {
                    "cycle_id": summary["cycle_id"],
                    "latest_event_at_utc": summary["latest_event_at_utc"],
                    "latest_event_type": summary["latest_event_type"],
                    "latest_status": summary["latest_status"],
                    "latest_decision": summary["latest_decision"],
                    "benchmark_variant": summary["benchmark_variant"],
                    "execution_backends": sorted(summary["execution_backends"]),
                    "symbols": sorted(summary["symbols"]),
                    "run_ids": sorted(summary["run_ids"]),
                    "thread_ids": sorted(summary["thread_ids"]),
                    "event_types": sorted(summary["event_types"]),
                    "event_count": summary["event_count"],
                    "pending_review": summary["pending_review"],
                    "approved_candidate_ready": summary["approved_candidate_ready"],
                    "transmit_attempted": summary["transmit_attempted"],
                    "transmit_succeeded": summary["transmit_succeeded"],
                    "error_event_count": summary["error_event_count"],
                }
            )
        return results


__all__ = [
    "TradeOracleBenchmarkEvent",
    "TradeOracleBenchmarkStore",
]
