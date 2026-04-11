"""Tests for the scanner/risk/execution operational FastAPI service."""

from fastapi.testclient import TestClient

from api.trade_oracle_ops_service import LiveScannerRequest, build_trade_oracle_ops_app


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


def test_ops_service_phase2_scanner_endpoint_returns_setups():
    app = build_trade_oracle_ops_app(
        require_auth=False,
        phase2_scanner_runner=_fake_phase2_scanner_runner,
        live_scanner_runner=_fake_live_scanner_runner,
        match_trader_api_cls=_FakeMatchTraderAPI,
    )
    client = TestClient(app)

    response = client.post(
        "/ops/scanner/phase2/run",
        json={"watchlist": ["SOL/USDT", "ETH/USDT"]},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["result"]["setup_count"] == 1
    assert body["result"]["setups"][0]["symbol"] == "SOL/USDT"


def test_ops_service_live_scanner_endpoint_returns_header_and_setups():
    app = build_trade_oracle_ops_app(
        require_auth=False,
        phase2_scanner_runner=_fake_phase2_scanner_runner,
        live_scanner_runner=_fake_live_scanner_runner,
        match_trader_api_cls=_FakeMatchTraderAPI,
    )
    client = TestClient(app)

    response = client.post(
        "/ops/scanner/live/run",
        json={"mode": "live", "top_n": 3},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["result"]["active_pairs"] == 3
    assert body["result"]["setups"][0]["pair_id"] == "pair_001"


def test_ops_service_risk_endpoint_returns_gatekeeping_and_position_size():
    app = build_trade_oracle_ops_app(
        require_auth=False,
        phase2_scanner_runner=_fake_phase2_scanner_runner,
        live_scanner_runner=_fake_live_scanner_runner,
        match_trader_api_cls=_FakeMatchTraderAPI,
    )
    client = TestClient(app)

    response = client.post(
        "/ops/risk/evaluate",
        json={
            "current_balance": 5100.0,
            "highest_equity": 5150.0,
            "active_trades_count": 1,
            "entry_price": 41.25,
            "atr": 1.35,
            "direction": "BUY",
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["result"]["can_open_new_trade"] is True
    assert body["result"]["position_size"]["tokens"] > 0


def test_ops_service_execution_endpoints_use_match_trader_bridge():
    app = build_trade_oracle_ops_app(
        require_auth=False,
        phase2_scanner_runner=_fake_phase2_scanner_runner,
        live_scanner_runner=_fake_live_scanner_runner,
        match_trader_api_cls=_FakeMatchTraderAPI,
    )
    client = TestClient(app)

    platform_response = client.post(
        "/ops/execution/platform-details",
        json={
            "broker_id": "broker",
            "email": "user@example.com",
            "password": "secret",
            "base_url": "https://example.test",
            "system_uuid": "SYSTEM_123",
        },
    )
    platform_body = platform_response.json()

    assert platform_response.status_code == 200
    assert platform_body["status"] == "ok"
    assert platform_body["result"]["platform_details"]["equity"] == 5125.0

    order_response = client.post(
        "/ops/execution/transmit-limit-order",
        json={
            "broker_id": "broker",
            "email": "user@example.com",
            "password": "secret",
            "base_url": "https://example.test",
            "system_uuid": "SYSTEM_123",
            "symbol": "AVAX/USDT",
            "direction": "BUY",
            "size": 4.93827,
            "limit_price": 41.25,
            "stop_loss": 39.225,
            "take_profit": 43.95,
        },
    )
    order_body = order_response.json()

    assert order_response.status_code == 200
    assert order_body["status"] == "ok"
    assert order_body["result"]["order_transmitted"] is True
