"""Tests for the n8n-facing LangGraph brain FastAPI service."""

from fastapi.testclient import TestClient

from api.trade_oracle_brain_service import build_trade_oracle_brain_app


def test_brain_service_evaluate_setup_returns_pending_review_and_resume_completes():
    app = build_trade_oracle_brain_app(
        require_auth=False,
        checkpointer_path="results/test_trade_oracle_brain_service.sqlite",
    )
    client = TestClient(app)

    evaluate_response = client.post(
        "/brain/evaluate-setup",
        json={
            "scanner_setup": {
                "symbol": "SOL/USDT",
                "regime": "BULLISH",
                "current_price": 145.0,
                "atr": 9.25,
                "fibonacci_convergence_proximity": 0.011,
                "ema_cluster_distance": 0.007,
                "setup_quality": 0.88,
            },
            "account_state": {
                "current_balance": 5200.0,
                "highest_equity": 5300.0,
                "active_trades_count": 1,
            },
            "auto_approve": False,
        },
    )
    evaluate_body = evaluate_response.json()

    assert evaluate_response.status_code == 200
    assert evaluate_body["status"] == "ok"
    assert evaluate_body["result"]["status"] == "pending_review"
    assert evaluate_body["result"]["review_required"] is True

    thread_id = evaluate_body["result"]["thread_id"]
    review_context = evaluate_body["result"]["review_context"]
    assert thread_id
    assert review_context["review_type"] == "trade_authorization"
    assert review_context["final_decision"]["execution_status"] == "pending_human_review"

    resume_response = client.post(
        "/brain/resume-review",
        json={
            "thread_id": thread_id,
            "human_decision": {
                "action": "APPROVE",
                "reviewer": "pytest",
                "notes": "Approved in test flow.",
            },
        },
    )
    resume_body = resume_response.json()

    assert resume_response.status_code == 200
    assert resume_body["status"] == "ok"
    assert resume_body["result"]["status"] == "completed"
    assert resume_body["result"]["review_required"] is False
    assert resume_body["result"]["candidate"]["execute_trade"] is True
    assert resume_body["result"]["candidate"]["execution_status"] == "approved"
    assert resume_body["result"]["candidate"]["review_required"] is False


def test_brain_service_evaluate_batch_returns_ranked_candidates():
    app = build_trade_oracle_brain_app(
        require_auth=False,
        checkpointer_path="results/test_trade_oracle_brain_batch.sqlite",
    )
    client = TestClient(app)

    response = client.post(
        "/brain/evaluate-batch",
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
            ],
            "account_state": {
                "current_balance": 5200.0,
                "highest_equity": 5300.0,
                "active_trades_count": 1,
            },
            "auto_approve": True,
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["result"]["evaluation_count"] == 2
    assert len(body["result"]["evaluations"]) == 2
    assert body["result"]["candidate_count"] >= 1
    assert body["result"]["candidates"][0]["execution_status"] == "approved"


def test_brain_service_evaluate_batch_preserves_pending_review_threads():
    app = build_trade_oracle_brain_app(
        require_auth=False,
        checkpointer_path="results/test_trade_oracle_brain_batch_pending.sqlite",
    )
    client = TestClient(app)

    response = client.post(
        "/brain/evaluate-batch",
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
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["result"]["evaluation_count"] == 1
    assert body["result"]["evaluations"][0]["status"] == "pending_review"
    assert body["result"]["evaluations"][0]["thread_id"]
