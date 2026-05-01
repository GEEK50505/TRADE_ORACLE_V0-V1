"""Tests for the TRADE_ORACLE benchmark/event store."""

from ai.trade_oracle_benchmark import TradeOracleBenchmarkStore


def test_trade_oracle_benchmark_store_records_and_queries_cycle_events():
    store = TradeOracleBenchmarkStore("results/test_trade_oracle_benchmark.sqlite")

    recorded = store.record_event(
        event_type="risk_check",
        source="pytest",
        cycle_id="cycle-001",
        run_id="run-001",
        thread_id="thread-001",
        symbol="AVAX/USDT",
        execution_backend="mt5",
        benchmark_variant="super_brain",
        status="ok",
        decision="allow",
        payload={"can_open_new_trade": True},
    )

    assert recorded.event_id
    assert recorded.cycle_id == "cycle-001"
    assert recorded.benchmark_variant == "super_brain"

    recent = store.list_recent_events(limit=5, event_type="risk_check", cycle_id="cycle-001")
    assert any(event.event_id == recorded.event_id for event in recent)

    cycle_events = store.list_cycle_events("cycle-001", limit=5)
    assert any(event.event_id == recorded.event_id for event in cycle_events)


def test_trade_oracle_benchmark_store_builds_summary_and_recent_cycles():
    store = TradeOracleBenchmarkStore("results/test_trade_oracle_benchmark_summary.sqlite")

    store.record_event(
        event_type="scanner_cycle",
        source="pytest",
        cycle_id="cycle-summary-001",
        run_id="run-summary-001",
        benchmark_variant="super_brain",
        status="ok",
        decision="scanner_rows_ready",
    )
    store.record_event(
        event_type="super_brain_run",
        source="pytest",
        cycle_id="cycle-summary-001",
        run_id="run-summary-001",
        symbol="AVAX/USDT",
        benchmark_variant="super_brain",
        status="ok",
        decision="pending_review",
    )
    store.record_event(
        event_type="order_transmit_attempt",
        source="pytest",
        cycle_id="cycle-summary-001",
        run_id="run-summary-001",
        symbol="AVAX/USDT",
        execution_backend="mt5",
        benchmark_variant="super_brain",
        status="pending",
        decision="attempt",
    )
    store.record_event(
        event_type="order_transmit_result",
        source="pytest",
        cycle_id="cycle-summary-001",
        run_id="run-summary-001",
        symbol="AVAX/USDT",
        execution_backend="mt5",
        benchmark_variant="super_brain",
        status="ok",
        decision="transmitted",
    )

    summary = store.build_summary(benchmark_variant="super_brain")
    recent_cycles = store.list_recent_cycle_summaries(limit=5, benchmark_variant="super_brain")

    assert summary["total_cycles"] >= 1
    assert summary["transmit_attempts"] >= 1
    assert summary["transmit_successes"] >= 1
    assert summary["broker_acceptance_rate"] == 1.0
    assert recent_cycles[0]["cycle_id"] == "cycle-summary-001"
    assert recent_cycles[0]["pending_review"] is True
    assert recent_cycles[0]["transmit_attempted"] is True
    assert recent_cycles[0]["transmit_succeeded"] is True
