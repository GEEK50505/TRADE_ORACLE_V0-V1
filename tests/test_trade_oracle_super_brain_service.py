"""Tests for the unified TRADE_ORACLE LangGraph Super Brain service."""

from fastapi.testclient import TestClient

from ai.trade_oracle_benchmark import TradeOracleBenchmarkStore
from api.trade_oracle_super_brain_service import build_trade_oracle_super_brain_app


async def _fake_scanner_runner(*, watchlist, scanner_limit):
    rows = [
        {
            "symbol": "SOL/USDT",
            "regime": "BULLISH",
            "current_price": 145.0,
            "atr": 9.25,
            "fibonacci_convergence_proximity": 0.011,
            "ema_cluster_distance": 0.007,
            "setup_quality": 0.88,
        },
        {
            "symbol": "ETH/USDT",
            "regime": "BEARISH",
            "current_price": 2010.0,
            "atr": 125.5,
            "fibonacci_convergence_proximity": 0.012,
            "ema_cluster_distance": 0.009,
            "setup_quality": 0.81,
        },
    ]
    if scanner_limit is None:
        return rows
    return rows[: max(0, int(scanner_limit))]


def test_super_brain_run_once_can_scan_and_return_pending_review():
    app = build_trade_oracle_super_brain_app(
        require_auth=False,
        checkpointer_path="results/test_trade_oracle_super_brain.sqlite",
        scanner_runner=_fake_scanner_runner,
    )
    client = TestClient(app)

    response = client.post(
        "/superbrain/run-once",
        json={
            "watchlist": ["SOL/USDT", "ETH/USDT"],
            "scanner_limit": 1,
            "account_state": {
                "current_balance": 5200.0,
                "highest_equity": 5300.0,
                "active_trades_count": 1,
            },
            "auto_approve": False,
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["result"]["scanner_source"] == "phase2_scanner"
    assert body["result"]["scanner_row_count"] == 1
    assert body["result"]["evaluations"][0]["status"] == "pending_review"


def test_super_brain_run_once_and_resume_review_complete_end_to_end():
    app = build_trade_oracle_super_brain_app(
        require_auth=False,
        checkpointer_path="results/test_trade_oracle_super_brain_resume.sqlite",
        benchmark_db_path="results/test_trade_oracle_super_brain_resume_benchmark.sqlite",
        scanner_runner=_fake_scanner_runner,
    )
    client = TestClient(app)

    run_response = client.post(
        "/superbrain/run-once",
        json={
            "scanner_setups": [
                {
                    "symbol": "SOL/USDT",
                    "regime": "BULLISH",
                    "current_price": 145.0,
                    "atr": 9.25,
                    "fibonacci_convergence_proximity": 0.011,
                    "ema_cluster_distance": 0.007,
                    "setup_quality": 0.88,
                }
            ],
            "account_state": {
                "current_balance": 5200.0,
                "highest_equity": 5300.0,
                "active_trades_count": 1,
            },
            "auto_approve": False,
        },
    )
    run_body = run_response.json()

    assert run_response.status_code == 200
    assert run_body["result"]["evaluations"][0]["status"] == "pending_review"
    thread_id = run_body["result"]["evaluations"][0]["thread_id"]

    resume_response = client.post(
        "/superbrain/review-resume",
        json={
            "thread_id": thread_id,
            "human_decision": {
                "action": "APPROVE",
                "reviewer": "pytest",
                "notes": "Approved from unified super brain test.",
            },
        },
    )
    resume_body = resume_response.json()

    assert resume_response.status_code == 200
    assert resume_body["status"] == "ok"
    assert resume_body["result"]["status"] == "completed"
    assert resume_body["result"]["candidate"]["execute_trade"] is True
    assert resume_body["result"]["candidate"]["review_required"] is False


def test_super_brain_service_writes_benchmark_events_for_cycle():
    cycle_id = "cycle-super-brain-001"
    app = build_trade_oracle_super_brain_app(
        require_auth=False,
        checkpointer_path="results/test_trade_oracle_super_brain_benchmark.sqlite",
        benchmark_db_path="results/test_trade_oracle_super_brain_benchmark_events.sqlite",
        scanner_runner=_fake_scanner_runner,
    )
    client = TestClient(app)

    run_response = client.post(
        "/superbrain/run-once",
        json={
            "scanner_setups": [
                {
                    "symbol": "SOL/USDT",
                    "regime": "BULLISH",
                    "current_price": 145.0,
                    "atr": 9.25,
                    "fibonacci_convergence_proximity": 0.011,
                    "ema_cluster_distance": 0.007,
                    "setup_quality": 0.88,
                }
            ],
            "account_state": {
                "current_balance": 5200.0,
                "highest_equity": 5300.0,
                "active_trades_count": 1,
            },
            "auto_approve": False,
            "run_id": "run-super-brain-001",
            "cycle_id": cycle_id,
            "benchmark_variant": "super_brain",
        },
    )
    run_body = run_response.json()

    assert run_response.status_code == 200
    assert run_body["result"]["cycle_id"] == cycle_id
    thread_id = run_body["result"]["evaluations"][0]["thread_id"]

    resume_response = client.post(
        "/superbrain/review-resume",
        json={
            "thread_id": thread_id,
            "human_decision": {
                "action": "APPROVE",
                "reviewer": "pytest",
                "notes": "Benchmark trail validation.",
            },
            "run_id": "run-super-brain-001-resume",
            "cycle_id": cycle_id,
            "benchmark_variant": "super_brain",
        },
    )

    assert resume_response.status_code == 200

    store = TradeOracleBenchmarkStore("results/test_trade_oracle_super_brain_benchmark_events.sqlite")
    cycle_events = store.list_cycle_events(cycle_id, limit=20)
    event_types = {event.event_type for event in cycle_events}

    assert "scanner_cycle" in event_types
    assert "super_brain_run" in event_types
    assert "super_brain_resume" in event_types
    assert any(event.thread_id == thread_id for event in cycle_events if event.event_type == "super_brain_resume")
