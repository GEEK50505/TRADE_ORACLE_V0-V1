"""Tests for backend-selectable TRADE_ORACLE runtime-state storage."""

from __future__ import annotations

from ai.trade_oracle_runtime_state import (
    TradeOracleRuntimeStateStore,
    TradeOracleSupabaseRuntimeStateStore,
)
from ai.trade_oracle_storage import build_trade_oracle_runtime_state_store


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
        self.on_conflict = ""

    def select(self, *_args, **_kwargs):
        self.mode = "select"
        return self

    def upsert(self, payload, on_conflict=""):
        self.mode = "upsert"
        self.payload = dict(payload)
        self.on_conflict = str(on_conflict or "")
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
        if self.mode == "upsert":
            if self.on_conflict:
                for index, row in enumerate(table):
                    if row.get(self.on_conflict) == self.payload.get(self.on_conflict):
                        table[index] = dict(self.payload)
                        return _FakeSupabaseResponse([dict(self.payload)])
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


def test_build_trade_oracle_runtime_state_store_defaults_to_sqlite():
    store = build_trade_oracle_runtime_state_store(
        "results/test_trade_oracle_runtime_state_factory.sqlite",
        backend="sqlite",
    )
    assert isinstance(store, TradeOracleRuntimeStateStore)


def test_build_trade_oracle_runtime_state_store_supports_supabase_backend():
    fake_client = _FakeSupabaseClient()
    store = build_trade_oracle_runtime_state_store(
        backend="supabase",
        supabase_client=fake_client,
        pending_review_table="pending_reviews",
        forward_journal_table="forward_journal",
        daemon_checkpoint_table="daemon_checkpoints",
    )
    assert isinstance(store, TradeOracleSupabaseRuntimeStateStore)


def test_sqlite_runtime_state_store_round_trips_pending_reviews_and_journal():
    store = build_trade_oracle_runtime_state_store(
        "results/test_trade_oracle_runtime_state_roundtrip.sqlite",
        backend="sqlite",
    )

    record = store.upsert_pending_review(
        {
            "thread_id": "thread-sqlite-001",
            "cycle_id": "cycle-sqlite-001",
            "run_id": "run-sqlite-001",
            "symbol": "AVAX/USDT",
            "direction": "BUY",
            "candidate": {"symbol": "AVAX/USDT", "direction": "BUY"},
            "review_context": {"reason": "human gate"},
            "account_state": {"current_balance": 5200},
            "telegram_chat_id": "12345",
        }
    )
    resolved = store.resolve_pending_review(
        "thread-sqlite-001",
        review_action="APPROVE",
        reviewer="telegram_bot",
        review_notes="Approved from test.",
        cycle_outcome="resume_execution_result",
    )
    journal = store.upsert_forward_journal_entry(
        {
            "cycle_id": "cycle-sqlite-001",
            "run_id": "run-sqlite-001",
            "thread_id": "thread-sqlite-001",
            "workflow_name": "pytest",
            "stage": "resume_execution_result",
            "outcome": "resume_execution_result",
            "symbol": "AVAX/USDT",
            "direction": "BUY",
            "pending_review": False,
            "transmit_succeeded": True,
            "benchmark_event_count": 6,
            "thread_ids": ["thread-sqlite-001"],
            "summary": {"event_types": ["super_brain_run", "order_transmit_result"]},
        }
    )

    assert record.review_status == "pending"
    assert resolved is not None
    assert resolved.review_action == "APPROVE"
    assert resolved.review_status == "resolved"
    assert journal.transmit_succeeded is True
    assert store.get_pending_review("thread-sqlite-001").cycle_outcome == "resume_execution_result"
    assert store.get_forward_journal_entry("cycle-sqlite-001").summary["event_types"][1] == "order_transmit_result"

    checkpoint = store.upsert_daemon_checkpoint(
        {
            "checkpoint_key": "telegram_update_offset",
            "checkpoint_value": {"offset": 12345},
        }
    )

    assert checkpoint.checkpoint_value["offset"] == 12345
    assert store.get_daemon_checkpoint("telegram_update_offset").checkpoint_value["offset"] == 12345


def test_supabase_runtime_state_store_round_trips_pending_reviews_and_journal():
    fake_client = _FakeSupabaseClient()
    store = build_trade_oracle_runtime_state_store(
        backend="supabase",
        supabase_client=fake_client,
        pending_review_table="pending_reviews",
        forward_journal_table="forward_journal",
        daemon_checkpoint_table="daemon_checkpoints",
    )

    store.upsert_pending_review(
        {
            "thread_id": "thread-supabase-001",
            "cycle_id": "cycle-supabase-001",
            "run_id": "run-supabase-001",
            "symbol": "DOGE/USDT",
            "direction": "SELL",
            "candidate": {"symbol": "DOGE/USDT", "direction": "SELL"},
            "review_context": {"reason": "telegram gate"},
            "account_state": {"current_balance": 5100},
        }
    )
    resolved = store.resolve_pending_review(
        "thread-supabase-001",
        review_action="REJECT",
        review_status="resolved",
        reviewer="openclaw",
        review_notes="Rejected from test.",
        cycle_outcome="no_trade",
    )
    journal = store.upsert_forward_journal_entry(
        {
            "cycle_id": "cycle-supabase-001",
            "run_id": "run-supabase-001",
            "thread_id": "thread-supabase-001",
            "workflow_name": "pytest",
            "stage": "no_trade",
            "outcome": "no_trade",
            "symbol": "DOGE/USDT",
            "direction": "SELL",
            "pending_review": False,
            "transmit_succeeded": False,
            "benchmark_event_count": 4,
            "thread_ids": ["thread-supabase-001"],
            "summary": {"decisions": ["pending_review", "no_trade"]},
        }
    )

    pending_reviews = store.list_pending_reviews(review_status="resolved")
    forward_rows = store.list_forward_journal_entries(outcome="no_trade")
    checkpoint = store.upsert_daemon_checkpoint(
        {
            "checkpoint_key": "telegram_update_offset",
            "checkpoint_value": {"offset": 67890},
        }
    )

    assert resolved is not None
    assert resolved.review_action == "REJECT"
    assert pending_reviews[0].reviewer == "openclaw"
    assert journal.summary["decisions"][0] == "pending_review"
    assert forward_rows[0].symbol == "DOGE/USDT"
    assert checkpoint.checkpoint_value["offset"] == 67890
    assert store.get_daemon_checkpoint("telegram_update_offset").checkpoint_value["offset"] == 67890
