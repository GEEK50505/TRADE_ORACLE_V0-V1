"""Tests for the TRADE_ORACLE audit/event store."""

from ai.trade_oracle_audit import TradeOracleAuditStore


def test_trade_oracle_audit_store_records_and_queries_events():
    store = TradeOracleAuditStore("results/test_trade_oracle_audit.sqlite")

    recorded = store.record_event(
        event_type="evaluate_setup",
        source="pytest",
        run_id="run-001",
        thread_id="thread-001",
        status="pending_review",
        payload={"symbol": "SOL/USDT"},
    )

    assert recorded.event_id
    assert recorded.thread_id == "thread-001"

    recent = store.list_recent_events(limit=5, event_type="evaluate_setup")
    assert any(event.event_id == recorded.event_id for event in recent)

    thread_events = store.list_thread_events("thread-001", limit=5)
    assert any(event.event_id == recorded.event_id for event in thread_events)
