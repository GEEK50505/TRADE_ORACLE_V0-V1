"""Backend-selectable storage factories for TRADE_ORACLE audit and benchmark data."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from config import settings

from .trade_oracle_audit import TradeOracleAuditEvent, TradeOracleAuditStore
from .trade_oracle_benchmark import TradeOracleBenchmarkEvent, TradeOracleBenchmarkStore
from .trade_oracle_runtime_state import (
    TradeOracleDaemonCheckpointRecord,
    TradeOracleForwardJournalRecord,
    TradeOraclePendingReviewRecord,
    TradeOracleRuntimeStateStore,
    TradeOracleSupabaseRuntimeStateStore,
)
from .trade_oracle_supabase_storage import TradeOracleSupabaseAuditStore, TradeOracleSupabaseBenchmarkStore

SUPPORTED_TRADE_ORACLE_STORAGE_BACKENDS = ("sqlite", "supabase")


@runtime_checkable
class TradeOracleAuditStoreProtocol(Protocol):
    """Minimal contract required by the platform for audit-event storage."""

    def record_event(
        self,
        *,
        event_type: str,
        source: str,
        payload: dict[str, Any] | None = None,
        run_id: str = "",
        thread_id: str = "",
        status: str = "",
    ) -> TradeOracleAuditEvent: ...

    def list_recent_events(
        self,
        *,
        limit: int = 20,
        event_type: str = "",
        status: str = "",
    ) -> list[TradeOracleAuditEvent]: ...

    def list_thread_events(self, thread_id: str, *, limit: int = 100) -> list[TradeOracleAuditEvent]: ...


@runtime_checkable
class TradeOracleBenchmarkStoreProtocol(Protocol):
    """Minimal contract required by the platform for benchmark-event storage."""

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
    ) -> TradeOracleBenchmarkEvent: ...

    def list_recent_events(
        self,
        *,
        limit: int = 20,
        event_type: str = "",
        benchmark_variant: str = "",
        cycle_id: str = "",
        status: str = "",
    ) -> list[TradeOracleBenchmarkEvent]: ...

    def list_cycle_events(self, cycle_id: str, *, limit: int = 100) -> list[TradeOracleBenchmarkEvent]: ...

    def build_summary(
        self,
        *,
        benchmark_variant: str = "",
        execution_backend: str = "",
    ) -> dict[str, Any]: ...

    def list_recent_cycle_summaries(
        self,
        *,
        limit: int = 20,
        benchmark_variant: str = "",
        execution_backend: str = "",
        fetch_limit: int | None = None,
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class TradeOracleRuntimeStateStoreProtocol(Protocol):
    """Minimal contract required by the future daemon for orchestration state."""

    def get_pending_review(self, thread_id: str) -> TradeOraclePendingReviewRecord | None: ...

    def list_pending_reviews(
        self,
        *,
        limit: int = 50,
        review_status: str = "",
        symbol: str = "",
    ) -> list[TradeOraclePendingReviewRecord]: ...

    def upsert_pending_review(
        self,
        record: TradeOraclePendingReviewRecord | dict[str, Any],
    ) -> TradeOraclePendingReviewRecord: ...

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
    ) -> TradeOraclePendingReviewRecord | None: ...

    def get_forward_journal_entry(self, cycle_id: str) -> TradeOracleForwardJournalRecord | None: ...

    def list_forward_journal_entries(
        self,
        *,
        limit: int = 50,
        outcome: str = "",
        pending_review: bool | None = None,
    ) -> list[TradeOracleForwardJournalRecord]: ...

    def upsert_forward_journal_entry(
        self,
        record: TradeOracleForwardJournalRecord | dict[str, Any],
    ) -> TradeOracleForwardJournalRecord: ...

    def get_daemon_checkpoint(self, checkpoint_key: str) -> TradeOracleDaemonCheckpointRecord | None: ...

    def upsert_daemon_checkpoint(
        self,
        record: TradeOracleDaemonCheckpointRecord | dict[str, Any],
    ) -> TradeOracleDaemonCheckpointRecord: ...


def _normalize_backend(*, backend: str | None, default: str) -> str:
    return str(backend or default or "sqlite").strip().lower()


def _unsupported_backend_error(*, kind: str, backend: str) -> ValueError:
    supported = ", ".join(SUPPORTED_TRADE_ORACLE_STORAGE_BACKENDS)
    return ValueError(
        f"Unsupported TRADE_ORACLE {kind} storage backend '{backend}'. Supported backends: {supported}."
    )


def build_trade_oracle_audit_store(
    db_path: str | Path | None = None,
    *,
    backend: str | None = None,
    supabase_client: Any | None = None,
    table_name: str | None = None,
) -> TradeOracleAuditStoreProtocol:
    """Build the configured audit store while keeping SQLite as the safe default."""

    resolved_backend = _normalize_backend(backend=backend, default=settings.TRADE_ORACLE_AUDIT_BACKEND)
    resolved_db_path = str(db_path if db_path is not None else settings.TRADE_ORACLE_AUDIT_DB_PATH)

    if resolved_backend == "sqlite":
        return TradeOracleAuditStore(resolved_db_path)
    if resolved_backend == "supabase":
        return TradeOracleSupabaseAuditStore(
            table_name=table_name or settings.TRADE_ORACLE_SUPABASE_AUDIT_TABLE,
            supabase_client=supabase_client,
        )
    raise _unsupported_backend_error(kind="audit", backend=resolved_backend)


def build_trade_oracle_benchmark_store(
    db_path: str | Path | None = None,
    *,
    backend: str | None = None,
    supabase_client: Any | None = None,
    table_name: str | None = None,
) -> TradeOracleBenchmarkStoreProtocol:
    """Build the configured benchmark store while keeping SQLite as the safe default."""

    resolved_backend = _normalize_backend(backend=backend, default=settings.TRADE_ORACLE_BENCHMARK_BACKEND)
    resolved_db_path = str(db_path if db_path is not None else settings.TRADE_ORACLE_BENCHMARK_DB_PATH)

    if resolved_backend == "sqlite":
        return TradeOracleBenchmarkStore(resolved_db_path)
    if resolved_backend == "supabase":
        return TradeOracleSupabaseBenchmarkStore(
            table_name=table_name or settings.TRADE_ORACLE_SUPABASE_BENCHMARK_TABLE,
            supabase_client=supabase_client,
        )
    raise _unsupported_backend_error(kind="benchmark", backend=resolved_backend)


def build_trade_oracle_runtime_state_store(
    db_path: str | Path | None = None,
    *,
    backend: str | None = None,
    supabase_client: Any | None = None,
    pending_review_table: str | None = None,
    forward_journal_table: str | None = None,
    daemon_checkpoint_table: str | None = None,
) -> TradeOracleRuntimeStateStoreProtocol:
    """Build the configured runtime-state store while keeping SQLite as the safe default."""

    resolved_backend = _normalize_backend(
        backend=backend,
        default=settings.TRADE_ORACLE_RUNTIME_STATE_BACKEND,
    )
    resolved_db_path = str(db_path if db_path is not None else settings.TRADE_ORACLE_RUNTIME_STATE_DB_PATH)

    if resolved_backend == "sqlite":
        return TradeOracleRuntimeStateStore(
            resolved_db_path,
            pending_review_table=pending_review_table or "pending_reviews",
            forward_journal_table=forward_journal_table or "forward_journal",
            daemon_checkpoint_table=daemon_checkpoint_table or "daemon_checkpoints",
        )
    if resolved_backend == "supabase":
        return TradeOracleSupabaseRuntimeStateStore(
            pending_review_table=pending_review_table or settings.TRADE_ORACLE_SUPABASE_PENDING_REVIEW_TABLE,
            forward_journal_table=forward_journal_table or settings.TRADE_ORACLE_SUPABASE_FORWARD_JOURNAL_TABLE,
            daemon_checkpoint_table=daemon_checkpoint_table or settings.TRADE_ORACLE_SUPABASE_DAEMON_CHECKPOINT_TABLE,
            supabase_client=supabase_client,
        )
    raise _unsupported_backend_error(kind="runtime state", backend=resolved_backend)


__all__ = [
    "SUPPORTED_TRADE_ORACLE_STORAGE_BACKENDS",
    "TradeOracleAuditStoreProtocol",
    "TradeOracleBenchmarkStoreProtocol",
    "TradeOracleRuntimeStateStoreProtocol",
    "build_trade_oracle_audit_store",
    "build_trade_oracle_benchmark_store",
    "build_trade_oracle_runtime_state_store",
]
