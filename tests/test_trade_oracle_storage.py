"""Tests for backend-selectable TRADE_ORACLE storage factories."""

import pytest

from ai.trade_oracle_audit import TradeOracleAuditStore
from ai.trade_oracle_benchmark import TradeOracleBenchmarkStore
from ai.trade_oracle_supabase_storage import (
    TradeOracleSupabaseAuditStore,
    TradeOracleSupabaseBenchmarkStore,
)
from ai.trade_oracle_storage import (
    build_trade_oracle_audit_store,
    build_trade_oracle_benchmark_store,
)


def test_build_trade_oracle_audit_store_defaults_to_sqlite():
    store = build_trade_oracle_audit_store("results/test_trade_oracle_audit_factory.sqlite", backend="sqlite")
    assert isinstance(store, TradeOracleAuditStore)


def test_build_trade_oracle_benchmark_store_defaults_to_sqlite():
    store = build_trade_oracle_benchmark_store(
        "results/test_trade_oracle_benchmark_factory.sqlite",
        backend="sqlite",
    )
    assert isinstance(store, TradeOracleBenchmarkStore)


def test_build_trade_oracle_audit_store_rejects_unknown_backend():
    with pytest.raises(ValueError, match="Unsupported TRADE_ORACLE audit storage backend"):
        build_trade_oracle_audit_store("results/test_trade_oracle_audit_factory.sqlite", backend="mystery")


class _FakeSupabaseResponse:
    def __init__(self, data):
        self.data = data


class _FakeSupabaseQuery:
    def __init__(self, tables, table_name):
        self.tables = tables
        self.table_name = table_name
        self.mode = "select"
        self.filters = []
        self.limit_value = None
        self.order_field = ""
        self.order_desc = False
        self.payload = None

    def select(self, *_args, **_kwargs):
        self.mode = "select"
        return self

    def insert(self, payload):
        self.mode = "insert"
        self.payload = dict(payload)
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def order(self, field, desc=False):
        self.order_field = field
        self.order_desc = desc
        return self

    def limit(self, value):
        self.limit_value = int(value)
        return self

    def execute(self):
        table = self.tables.setdefault(self.table_name, [])
        if self.mode == "insert":
            table.append(dict(self.payload))
            return _FakeSupabaseResponse([dict(self.payload)])

        rows = [dict(row) for row in table]
        for field, value in self.filters:
            rows = [row for row in rows if row.get(field) == value]
        if self.order_field:
            rows.sort(key=lambda row: row.get(self.order_field, ""), reverse=self.order_desc)
        if self.limit_value is not None:
            rows = rows[: self.limit_value]
        return _FakeSupabaseResponse(rows)


class _FakeSupabaseClient:
    def __init__(self):
        self.tables = {}

    def table(self, table_name):
        return _FakeSupabaseQuery(self.tables, table_name)


def test_build_trade_oracle_audit_store_supports_supabase_backend():
    fake_client = _FakeSupabaseClient()
    store = build_trade_oracle_audit_store(
        backend="supabase",
        supabase_client=fake_client,
        table_name="audit_events",
    )
    assert isinstance(store, TradeOracleSupabaseAuditStore)


def test_build_trade_oracle_benchmark_store_supports_supabase_backend():
    fake_client = _FakeSupabaseClient()
    store = build_trade_oracle_benchmark_store(
        backend="supabase",
        supabase_client=fake_client,
        table_name="benchmark_events",
    )
    assert isinstance(store, TradeOracleSupabaseBenchmarkStore)


def test_supabase_storage_round_trips_audit_and_benchmark_events():
    fake_client = _FakeSupabaseClient()
    audit_store = build_trade_oracle_audit_store(
        backend="supabase",
        supabase_client=fake_client,
        table_name="audit_events",
    )
    benchmark_store = build_trade_oracle_benchmark_store(
        backend="supabase",
        supabase_client=fake_client,
        table_name="benchmark_events",
    )

    audit_store.record_event(
        event_type="evaluate_setup",
        source="pytest",
        run_id="run-supabase-001",
        thread_id="thread-supabase-001",
        status="pending_review",
        payload={"symbol": "SOL/USDT"},
    )
    benchmark_store.record_event(
        event_type="super_brain_run",
        source="pytest",
        cycle_id="cycle-supabase-001",
        run_id="run-supabase-001",
        thread_id="thread-supabase-001",
        symbol="SOL/USDT",
        execution_backend="mt5",
        benchmark_variant="super_brain",
        status="ok",
        decision="pending_review",
        payload={"candidate_count": 1},
    )

    audit_events = audit_store.list_thread_events("thread-supabase-001")
    benchmark_events = benchmark_store.list_cycle_events("cycle-supabase-001")
    summary = benchmark_store.build_summary(benchmark_variant="super_brain")

    assert audit_events[0].payload["symbol"] == "SOL/USDT"
    assert benchmark_events[0].decision == "pending_review"
    assert summary["pending_review_runs"] == 1
