"""Tests for the single-container TRADE_ORACLE platform service."""

from fastapi.testclient import TestClient

from api.trade_oracle_ops_service import LiveScannerRequest
from api.trade_oracle_platform_service import build_trade_oracle_platform_app


async def _fake_super_brain_scanner_runner(*, watchlist, scanner_limit):
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


async def _fake_phase2_scanner_runner(watchlist):
    return [
        {
            "symbol": watchlist[0],
            "regime": "BULLISH",
            "current_price": 145.0,
            "atr": 9.25,
            "setup_quality": 0.88,
        }
    ]


async def _fake_live_scanner_runner(request: LiveScannerRequest):
    return {
        "mode": request.mode,
        "active_pairs": request.top_n,
        "header": "TRADE_ORACLE LIVE SCANNER",
        "setups": [
            {
                "pair_id": "pair_001",
                "symbol": "AVAX/USDT",
                "side": "long",
                "current_price": 41.25,
                "signal_strength": 1.0542,
            }
        ],
    }


class _FakeMatchTraderAPI:
    def __init__(self, broker_id, email, password, base_url):
        self.broker_id = broker_id
        self.email = email
        self.password = password
        self.base_url = base_url
        self.system_uuid = "FAKE_SYSTEM_UUID"

    async def authenticate(self):
        return True

    async def get_platform_details(self):
        return {"equity": 5125.0, "active_trades": 1}

    async def transmit_limit_order(self, symbol, direction, size, limit_price, stop_loss, take_profit, size_mode="units"):
        return all(
            [
                symbol,
                direction in {"BUY", "SELL"},
                size > 0,
                limit_price > 0,
                stop_loss > 0,
                take_profit > 0,
            ]
        )


def test_platform_service_exposes_capabilities_and_system_health():
    app = build_trade_oracle_platform_app(
        require_auth=False,
        checkpointer_path="results/test_trade_oracle_platform.sqlite",
        scanner_runner=_fake_super_brain_scanner_runner,
        phase2_scanner_runner=_fake_phase2_scanner_runner,
        live_scanner_runner=_fake_live_scanner_runner,
        match_trader_api_cls=_FakeMatchTraderAPI,
    )
    client = TestClient(app)

    health_response = client.get("/system/health")
    health_body = health_response.json()
    assert health_response.status_code == 200
    assert health_body["service"] == "trade_oracle_platform"
    assert health_body["primary_entrypoint"] == "/superbrain/run-once"

    capabilities_response = client.get("/system/capabilities")
    capabilities_body = capabilities_response.json()
    assert capabilities_response.status_code == 200
    assert capabilities_body["n8n_entrypoints"]["run_once"] == "/superbrain/run-once"
    assert capabilities_body["mounted_services"]["ops"]["routes"]["account_state"] == "/services/ops/ops/account/state"
    assert capabilities_body["mounted_services"]["ops"]["routes"]["risk_evaluate"] == "/services/ops/ops/risk/evaluate"
    assert capabilities_body["n8n_entrypoints"]["audit_recent"] == "/system/audit/recent"
    assert capabilities_body["n8n_entrypoints"]["benchmark_summary"] == "/system/benchmark/summary"


def test_platform_service_runs_superbrain_and_mounted_auxiliary_services():
    app = build_trade_oracle_platform_app(
        require_auth=False,
        checkpointer_path="results/test_trade_oracle_platform_routes.sqlite",
        scanner_runner=_fake_super_brain_scanner_runner,
        phase2_scanner_runner=_fake_phase2_scanner_runner,
        live_scanner_runner=_fake_live_scanner_runner,
        match_trader_api_cls=_FakeMatchTraderAPI,
    )
    client = TestClient(app)

    run_response = client.post(
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
    run_body = run_response.json()
    assert run_response.status_code == 200
    assert run_body["result"]["evaluations"][0]["status"] == "pending_review"

    risk_response = client.post(
        "/services/ops/ops/risk/evaluate",
        json={
            "current_balance": 5100.0,
            "highest_equity": 5150.0,
            "active_trades_count": 1,
            "entry_price": 41.25,
            "atr": 1.35,
            "direction": "BUY",
        },
    )
    risk_body = risk_response.json()
    assert risk_response.status_code == 200
    assert risk_body["result"]["position_size"]["tokens"] > 0

    technical_response = client.post(
        "/services/mcp/mcp/technical-snapshot",
        json={
            "asset_ticker": "SOL/USDT",
            "timeframe": "4h",
            "benchmark_regime_status": "RISK_ON",
            "localized_atr": 9.25,
            "fibonacci_convergence_proximity": 0.011,
            "current_price": 145.0,
            "setup_direction": "BUY",
            "extra_context": {
                "setup_quality": 0.88,
                "ema_cluster_distance": 0.007,
                "scanner_metadata": {
                    "ema_confirmed": True,
                    "sma_confirmed": True,
                },
            },
        },
    )
    technical_body = technical_response.json()
    assert technical_response.status_code == 200
    assert technical_body["result"]["is_valid"] is True


def test_platform_service_exposes_recent_and_thread_audit_history():
    app = build_trade_oracle_platform_app(
        require_auth=False,
        checkpointer_path="results/test_trade_oracle_platform_audit.sqlite",
        audit_db_path="results/test_trade_oracle_platform_events.sqlite",
        scanner_runner=_fake_super_brain_scanner_runner,
        phase2_scanner_runner=_fake_phase2_scanner_runner,
        live_scanner_runner=_fake_live_scanner_runner,
        match_trader_api_cls=_FakeMatchTraderAPI,
    )
    client = TestClient(app)

    run_response = client.post(
        "/superbrain/run-once",
        json={
            "run_id": "pytest-platform-run",
            "watchlist": ["SOL/USDT"],
            "scanner_limit": 1,
            "account_state": {
                "current_balance": 5200.0,
                "highest_equity": 5300.0,
                "active_trades_count": 1,
            },
            "auto_approve": False,
        },
    )
    run_body = run_response.json()
    thread_id = run_body["result"]["evaluations"][0]["thread_id"]

    recent_response = client.get("/system/audit/recent")
    recent_body = recent_response.json()
    assert recent_response.status_code == 200
    assert recent_body["count"] >= 1
    assert any(event["event_type"] == "evaluate_setup" for event in recent_body["events"])

    thread_response = client.get(f"/system/audit/thread/{thread_id}")
    thread_body = thread_response.json()
    assert thread_response.status_code == 200
    assert thread_body["count"] >= 1
    assert all(event["thread_id"] == thread_id for event in thread_body["events"])


def test_platform_service_supports_prebroker_live_demo_chain(monkeypatch):
    monkeypatch.setattr("config.settings.SUPABASE_URL", "")
    monkeypatch.setattr("config.settings.SUPABASE_KEY", "")
    monkeypatch.setattr("config.settings.TRADE_ORACLE_LIVE_TP_MODE", "tp1_only")

    app = build_trade_oracle_platform_app(
        require_auth=False,
        checkpointer_path="results/test_trade_oracle_platform_demo.sqlite",
        audit_db_path="results/test_trade_oracle_platform_demo_audit.sqlite",
        scanner_runner=_fake_super_brain_scanner_runner,
        phase2_scanner_runner=_fake_phase2_scanner_runner,
        live_scanner_runner=_fake_live_scanner_runner,
        match_trader_api_cls=_FakeMatchTraderAPI,
    )
    client = TestClient(app)

    run_response = client.post(
        "/superbrain/run-once",
        json={
            "watchlist": ["SOL/USDT"],
            "scanner_limit": 1,
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
                "notes": "Approve demo chain candidate.",
            },
        },
    )
    resume_body = resume_response.json()
    assert resume_response.status_code == 200
    candidate = resume_body["result"]["candidate"]
    assert candidate["execute_trade"] is True
    assert candidate["execution_status"] == "approved"
    assert candidate["execution_tp_mode"] == "tp1_only"

    account_state_response = client.post(
        "/services/ops/ops/account/state",
        json={
            "broker_id": "broker",
            "email": "user@example.com",
            "password": "secret",
            "base_url": "https://example.test",
            "system_uuid": "SYSTEM_123",
        },
    )
    account_state_body = account_state_response.json()
    assert account_state_response.status_code == 200
    assert account_state_body["result"]["high_watermark_source"] == "fallback_current_equity"
    assert account_state_body["result"]["can_open_new_trade"] is True

    risk_response = client.post(
        "/services/ops/ops/risk/evaluate",
        json={
            "current_balance": 5200.0,
            "highest_equity": 5300.0,
            "active_trades_count": 1,
            "entry_price": candidate["entry_price"],
            "atr": resume_body["result"]["raw_setup"]["localized_atr"],
            "direction": candidate["direction"],
        },
    )
    risk_body = risk_response.json()
    assert risk_response.status_code == 200
    assert risk_body["result"]["can_open_new_trade"] is True
    assert risk_body["result"]["position_size"]["tokens"] > 0

    execution_response = client.post(
        "/services/ops/ops/execution/transmit-limit-order",
        json={
            "broker_id": "broker",
            "email": "user@example.com",
            "password": "secret",
            "base_url": "https://example.test",
            "system_uuid": "SYSTEM_123",
            "symbol": candidate["symbol"],
            "direction": candidate["direction"],
            "size": candidate["size_tokens"],
            "limit_price": candidate["entry_price"],
            "stop_loss": candidate["stop_loss"],
            "take_profit": candidate["take_profit"],
        },
    )
    execution_body = execution_response.json()
    assert execution_response.status_code == 200
    assert execution_body["result"]["order_transmitted"] is True


def test_platform_service_exposes_benchmark_summary_recent_and_cycle_views(monkeypatch):
    cycle_id = "cycle-platform-benchmark-001"
    monkeypatch.setattr("config.settings.SUPABASE_URL", "")
    monkeypatch.setattr("config.settings.SUPABASE_KEY", "")

    app = build_trade_oracle_platform_app(
        require_auth=False,
        checkpointer_path="results/test_trade_oracle_platform_benchmark.sqlite",
        audit_db_path="results/test_trade_oracle_platform_benchmark_audit.sqlite",
        benchmark_db_path="results/test_trade_oracle_platform_benchmark_events.sqlite",
        scanner_runner=_fake_super_brain_scanner_runner,
        phase2_scanner_runner=_fake_phase2_scanner_runner,
        live_scanner_runner=_fake_live_scanner_runner,
        match_trader_api_cls=_FakeMatchTraderAPI,
    )
    client = TestClient(app)

    run_response = client.post(
        "/superbrain/run-once",
        json={
            "watchlist": ["SOL/USDT"],
            "scanner_limit": 1,
            "account_state": {
                "current_balance": 5200.0,
                "highest_equity": 5300.0,
                "active_trades_count": 1,
            },
            "auto_approve": False,
            "run_id": "run-platform-benchmark-001",
            "cycle_id": cycle_id,
            "benchmark_variant": "super_brain",
        },
    )
    run_body = run_response.json()
    assert run_response.status_code == 200

    thread_id = run_body["result"]["evaluations"][0]["thread_id"]
    resume_response = client.post(
        "/superbrain/review-resume",
        json={
            "thread_id": thread_id,
            "human_decision": {
                "action": "APPROVE",
                "reviewer": "pytest",
                "notes": "Approve benchmark chain candidate.",
            },
            "run_id": "run-platform-benchmark-002",
            "cycle_id": cycle_id,
            "benchmark_variant": "super_brain",
        },
    )
    resume_body = resume_response.json()
    assert resume_response.status_code == 200
    candidate = resume_body["result"]["candidate"]

    risk_response = client.post(
        "/services/ops/ops/risk/evaluate",
        json={
            "symbol": candidate["symbol"],
            "current_balance": 5200.0,
            "highest_equity": 5300.0,
            "active_trades_count": 1,
            "entry_price": candidate["entry_price"],
            "atr": resume_body["result"]["raw_setup"]["localized_atr"],
            "direction": candidate["direction"],
            "run_id": "run-platform-benchmark-003",
            "cycle_id": cycle_id,
            "benchmark_variant": "super_brain",
        },
    )
    assert risk_response.status_code == 200

    execution_response = client.post(
        "/services/ops/ops/execution/transmit-limit-order",
        json={
            "broker_id": "broker",
            "email": "user@example.com",
            "password": "secret",
            "base_url": "https://example.test",
            "system_uuid": "SYSTEM_123",
            "symbol": candidate["symbol"],
            "direction": candidate["direction"],
            "size": candidate["size_tokens"],
            "limit_price": candidate["entry_price"],
            "stop_loss": candidate["stop_loss"],
            "take_profit": candidate["take_profit"],
            "run_id": "run-platform-benchmark-004",
            "cycle_id": cycle_id,
            "benchmark_variant": "super_brain",
        },
    )
    assert execution_response.status_code == 200

    summary_response = client.get("/system/benchmark/summary?benchmark_variant=super_brain")
    summary_body = summary_response.json()
    assert summary_response.status_code == 200
    assert summary_body["summary"]["total_cycles"] >= 1
    assert summary_body["summary"]["transmit_attempts"] >= 1
    assert summary_body["summary"]["transmit_successes"] >= 1

    recent_response = client.get(f"/system/benchmark/recent?cycle_id={cycle_id}")
    recent_body = recent_response.json()
    assert recent_response.status_code == 200
    assert recent_body["count"] >= 1
    assert all(event["cycle_id"] == cycle_id for event in recent_body["events"])

    cycle_events_response = client.get(f"/system/benchmark/cycle/{cycle_id}")
    cycle_events_body = cycle_events_response.json()
    assert cycle_events_response.status_code == 200
    assert cycle_events_body["count"] >= 1

    cycles_recent_response = client.get("/system/benchmark/cycles/recent?benchmark_variant=super_brain")
    cycles_recent_body = cycles_recent_response.json()
    assert cycles_recent_response.status_code == 200
    assert cycles_recent_body["count"] >= 1
    matching_cycles = [cycle for cycle in cycles_recent_body["cycles"] if cycle["cycle_id"] == cycle_id]
    assert matching_cycles
    assert matching_cycles[0]["transmit_attempted"] is True
