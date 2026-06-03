"""Supabase-backed TRADE_ORACLE audit and benchmark stores."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from config import settings

from .trade_oracle_audit import TradeOracleAuditEvent
from .trade_oracle_benchmark import TradeOracleBenchmarkEvent
from .trade_oracle_supabase import build_trade_oracle_supabase_client, coerce_supabase_rows, execute_supabase_request


def _coerce_payload(row: dict[str, Any], *field_names: str) -> dict[str, Any]:
    for field_name in field_names:
        value = row.get(field_name)
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str) and value.strip():
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                return decoded
    return {}


@dataclass(slots=True)
class TradeOracleSupabaseAuditStore:
    """Supabase-backed audit-event store."""

    table_name: str = settings.TRADE_ORACLE_SUPABASE_AUDIT_TABLE
    supabase_client: Any | None = None

    def __post_init__(self) -> None:
        if self.supabase_client is None:
            self.supabase_client = build_trade_oracle_supabase_client()

    @staticmethod
    def _row_to_event(row: dict[str, Any]) -> TradeOracleAuditEvent:
        return TradeOracleAuditEvent(
            event_id=str(row.get("event_id", "")),
            created_at_utc=str(row.get("created_at_utc", "")),
            event_type=str(row.get("event_type", "")),
            source=str(row.get("source", "")),
            run_id=str(row.get("run_id", "")),
            thread_id=str(row.get("thread_id", "")),
            status=str(row.get("status", "")),
            payload=_coerce_payload(row, "payload", "payload_json"),
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
        response = execute_supabase_request(
            lambda: self.supabase_client.table(self.table_name).insert(
                {
                    "event_id": event.event_id,
                    "created_at_utc": event.created_at_utc,
                    "event_type": event.event_type,
                    "source": event.source,
                    "run_id": event.run_id,
                    "thread_id": event.thread_id,
                    "status": event.status,
                    "payload": event.payload,
                }
            )
        )
        rows = coerce_supabase_rows(response)
        return self._row_to_event(rows[0]) if rows else event

    def list_recent_events(
        self,
        *,
        limit: int = 20,
        event_type: str = "",
        status: str = "",
    ) -> list[TradeOracleAuditEvent]:
        query = self.supabase_client.table(self.table_name).select("*")
        if event_type:
            query = query.eq("event_type", event_type)
        if status:
            query = query.eq("status", status)
        rows = coerce_supabase_rows(
            execute_supabase_request(
                lambda: query.order("created_at_utc", desc=True).limit(max(1, int(limit)))
            )
        )
        return [self._row_to_event(row) for row in rows]

    def list_thread_events(self, thread_id: str, *, limit: int = 100) -> list[TradeOracleAuditEvent]:
        rows = coerce_supabase_rows(
            execute_supabase_request(
                lambda: self.supabase_client.table(self.table_name)
                .select("*")
                .eq("thread_id", thread_id)
                .order("created_at_utc", desc=True)
                .limit(max(1, int(limit)))
            )
        )
        return [self._row_to_event(row) for row in rows]


@dataclass(slots=True)
class TradeOracleSupabaseBenchmarkStore:
    """Supabase-backed benchmark-event store."""

    table_name: str = settings.TRADE_ORACLE_SUPABASE_BENCHMARK_TABLE
    supabase_client: Any | None = None

    def __post_init__(self) -> None:
        if self.supabase_client is None:
            self.supabase_client = build_trade_oracle_supabase_client()

    @staticmethod
    def _row_to_event(row: dict[str, Any]) -> TradeOracleBenchmarkEvent:
        return TradeOracleBenchmarkEvent(
            event_id=str(row.get("event_id", "")),
            created_at_utc=str(row.get("created_at_utc", "")),
            event_type=str(row.get("event_type", "")),
            source=str(row.get("source", "")),
            cycle_id=str(row.get("cycle_id", "")),
            run_id=str(row.get("run_id", "")),
            thread_id=str(row.get("thread_id", "")),
            symbol=str(row.get("symbol", "")),
            execution_backend=str(row.get("execution_backend", "")),
            benchmark_variant=str(row.get("benchmark_variant", "")),
            status=str(row.get("status", "")),
            decision=str(row.get("decision", "")),
            payload=_coerce_payload(row, "payload", "payload_json"),
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
        response = execute_supabase_request(
            lambda: self.supabase_client.table(self.table_name).insert(
                {
                    "event_id": event.event_id,
                    "created_at_utc": event.created_at_utc,
                    "event_type": event.event_type,
                    "source": event.source,
                    "cycle_id": event.cycle_id,
                    "run_id": event.run_id,
                    "thread_id": event.thread_id,
                    "symbol": event.symbol,
                    "execution_backend": event.execution_backend,
                    "benchmark_variant": event.benchmark_variant,
                    "status": event.status,
                    "decision": event.decision,
                    "payload": event.payload,
                }
            )
        )
        rows = coerce_supabase_rows(response)
        return self._row_to_event(rows[0]) if rows else event

    def list_recent_events(
        self,
        *,
        limit: int = 20,
        event_type: str = "",
        benchmark_variant: str = "",
        cycle_id: str = "",
        status: str = "",
    ) -> list[TradeOracleBenchmarkEvent]:
        query = self.supabase_client.table(self.table_name).select("*")
        if event_type:
            query = query.eq("event_type", event_type)
        if benchmark_variant:
            query = query.eq("benchmark_variant", benchmark_variant)
        if cycle_id:
            query = query.eq("cycle_id", cycle_id)
        if status:
            query = query.eq("status", status)
        rows = coerce_supabase_rows(
            execute_supabase_request(
                lambda: query.order("created_at_utc", desc=True).limit(max(1, int(limit)))
            )
        )
        return [self._row_to_event(row) for row in rows]

    def list_cycle_events(self, cycle_id: str, *, limit: int = 100) -> list[TradeOracleBenchmarkEvent]:
        rows = coerce_supabase_rows(
            execute_supabase_request(
                lambda: self.supabase_client.table(self.table_name)
                .select("*")
                .eq("cycle_id", cycle_id)
                .order("created_at_utc", desc=True)
                .limit(max(1, int(limit)))
            )
        )
        return [self._row_to_event(row) for row in rows]

    def build_summary(
        self,
        *,
        benchmark_variant: str = "",
        execution_backend: str = "",
    ) -> dict[str, Any]:
        events = self.list_recent_events(
            limit=5000,
            benchmark_variant=benchmark_variant,
        )
        filtered_events = [
            event
            for event in events
            if not execution_backend or event.execution_backend == execution_backend
        ]

        transmit_attempts = sum(1 for event in filtered_events if event.event_type == "order_transmit_attempt")
        transmit_successes = sum(
            1
            for event in filtered_events
            if event.event_type == "order_transmit_result" and event.decision == "transmitted"
        )

        return {
            "total_events": len(filtered_events),
            "total_cycles": len({event.cycle_id for event in filtered_events if event.cycle_id}),
            "total_runs": len({event.run_id for event in filtered_events if event.run_id}),
            "total_symbols": len({event.symbol for event in filtered_events if event.symbol}),
            "scanner_cycles": sum(1 for event in filtered_events if event.event_type == "scanner_cycle"),
            "super_brain_runs": sum(1 for event in filtered_events if event.event_type == "super_brain_run"),
            "super_brain_resumes": sum(1 for event in filtered_events if event.event_type == "super_brain_resume"),
            "risk_checks": sum(1 for event in filtered_events if event.event_type == "risk_check"),
            "transmit_attempts": transmit_attempts,
            "transmit_successes": transmit_successes,
            "transmit_rejections": sum(
                1
                for event in filtered_events
                if event.event_type == "order_transmit_result" and event.decision == "not_transmitted"
            ),
            "pending_review_runs": sum(
                1
                for event in filtered_events
                if event.event_type == "super_brain_run" and event.decision == "pending_review"
            ),
            "approved_candidate_runs": sum(
                1
                for event in filtered_events
                if event.event_type == "super_brain_run" and event.decision == "approved_candidate_ready"
            ),
            "error_events": sum(1 for event in filtered_events if event.status == "error"),
            "broker_acceptance_rate": round(transmit_successes / transmit_attempts, 6)
            if transmit_attempts
            else 0.0,
            "benchmark_variant": benchmark_variant,
            "execution_backend": execution_backend,
            "latest_event_at_utc": filtered_events[0].created_at_utc if filtered_events else "",
        }

    def list_recent_cycle_summaries(
        self,
        *,
        limit: int = 20,
        benchmark_variant: str = "",
        execution_backend: str = "",
        fetch_limit: int | None = None,
    ) -> list[dict[str, Any]]:
        events = self.list_recent_events(
            limit=fetch_limit if fetch_limit is not None else max(100, int(limit) * 40),
            benchmark_variant=benchmark_variant,
        )
        filtered_events = [
            event
            for event in events
            if not execution_backend or event.execution_backend == execution_backend
        ]

        summaries: dict[str, dict[str, Any]] = {}
        ordered_cycle_ids: list[str] = []

        for event in filtered_events:
            if not event.cycle_id:
                continue
            if event.cycle_id not in summaries:
                ordered_cycle_ids.append(event.cycle_id)
                summaries[event.cycle_id] = {
                    "cycle_id": event.cycle_id,
                    "latest_event_at_utc": event.created_at_utc,
                    "latest_event_type": event.event_type,
                    "latest_status": event.status,
                    "latest_decision": event.decision,
                    "benchmark_variant": event.benchmark_variant,
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

            summary = summaries[event.cycle_id]
            summary["event_count"] += 1
            if event.execution_backend:
                summary["execution_backends"].add(event.execution_backend)
            if event.symbol:
                summary["symbols"].add(event.symbol)
            if event.run_id:
                summary["run_ids"].add(event.run_id)
            if event.thread_id:
                summary["thread_ids"].add(event.thread_id)
            summary["event_types"].add(event.event_type)
            if event.event_type == "super_brain_run" and event.decision == "pending_review":
                summary["pending_review"] = True
            if event.event_type == "super_brain_run" and event.decision == "approved_candidate_ready":
                summary["approved_candidate_ready"] = True
            if event.event_type == "order_transmit_attempt":
                summary["transmit_attempted"] = True
            if event.event_type == "order_transmit_result" and event.decision == "transmitted":
                summary["transmit_succeeded"] = True
            if event.status == "error":
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
    "TradeOracleSupabaseAuditStore",
    "TradeOracleSupabaseBenchmarkStore",
]
