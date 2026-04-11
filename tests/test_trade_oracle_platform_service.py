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

    async def transmit_limit_order(self, symbol, direction, size, limit_price, stop_loss, take_profit):
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
    assert capabilities_body["mounted_services"]["ops"]["routes"]["risk_evaluate"] == "/services/ops/ops/risk/evaluate"
    assert capabilities_body["n8n_entrypoints"]["audit_recent"] == "/system/audit/recent"


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
