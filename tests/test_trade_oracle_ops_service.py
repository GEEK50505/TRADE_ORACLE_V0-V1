"""Tests for the scanner/risk/execution operational FastAPI service."""

from fastapi.testclient import TestClient

from ai.trade_oracle_benchmark import TradeOracleBenchmarkStore
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


class _FakeStateManager:
    def update_high_watermark(self, current_equity):
        assert current_equity == 5125.0
        return 5250.0


class _FailingStateManager:
    def __init__(self):
        raise RuntimeError("Supabase unavailable for test")


class _FakeMT5Bridge:
    def __init__(self, *, login, password, server, terminal_path=None, symbol_suffix="", symbol_map=None):
        self.login = int(login)
        self.password = password
        self.server = server
        self.terminal_path = terminal_path or ""
        self.symbol_suffix = symbol_suffix
        self.symbol_map = symbol_map or {}

    async def authenticate(self):
        return True

    async def get_platform_details(self):
        return {"equity": 4988.0, "active_trades": 2}

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

    async def get_symbol_status(self, symbol):
        resolved = self.symbol_map.get(symbol, symbol.replace("/", ""))
        return {
            "requested_symbol": symbol,
            "resolved_symbol": resolved,
            "authenticated": True,
            "available": resolved in {"ETH", "SOL", "BTC", "XXRP"},
            "selected": True,
            "visible": True,
            "trade_mode": 4,
            "point": 0.01,
            "bid": 100.0 if resolved in {"ETH", "SOL", "BTC", "XXRP"} else 0.0,
            "ask": 101.0 if resolved in {"ETH", "SOL", "BTC", "XXRP"} else 0.0,
            "last": 100.5 if resolved in {"ETH", "SOL", "BTC", "XXRP"} else 0.0,
            "has_live_tick": resolved in {"ETH", "SOL", "BTC", "XXRP"},
        }

    async def shutdown(self):
        return None


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
            "execution_backend": "match_trader",
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
            "execution_backend": "match_trader",
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


def test_ops_service_execution_endpoints_support_mt5_backend():
    app = build_trade_oracle_ops_app(
        require_auth=False,
        phase2_scanner_runner=_fake_phase2_scanner_runner,
        live_scanner_runner=_fake_live_scanner_runner,
        mt5_bridge_cls=_FakeMT5Bridge,
    )
    client = TestClient(app)

    platform_response = client.post(
        "/ops/execution/platform-details",
        json={
            "execution_backend": "mt5",
            "mt5_login": 12345678,
            "mt5_password": "secret",
            "mt5_server": "Maven-Demo",
            "mt5_terminal_path": "C:\\MT5\\terminal64.exe",
            "mt5_symbol_suffix": "",
        },
    )
    platform_body = platform_response.json()

    assert platform_response.status_code == 200
    assert platform_body["status"] == "ok"
    assert platform_body["result"]["execution_backend"] == "mt5"
    assert platform_body["result"]["platform_details"]["equity"] == 4988.0

    order_response = client.post(
        "/ops/execution/transmit-limit-order",
        json={
            "execution_backend": "mt5",
            "mt5_login": 12345678,
            "mt5_password": "secret",
            "mt5_server": "Maven-Demo",
            "mt5_terminal_path": "C:\\MT5\\terminal64.exe",
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
    assert order_body["result"]["execution_backend"] == "mt5"
    assert order_body["result"]["order_transmitted"] is True


def test_ops_service_execution_symbol_status_supports_mt5_symbol_map():
    app = build_trade_oracle_ops_app(
        require_auth=False,
        phase2_scanner_runner=_fake_phase2_scanner_runner,
        live_scanner_runner=_fake_live_scanner_runner,
        mt5_bridge_cls=_FakeMT5Bridge,
    )
    client = TestClient(app)

    response = client.post(
        "/ops/execution/symbol-status",
        json={
            "execution_backend": "mt5",
            "mt5_login": 12345678,
            "mt5_password": "secret",
            "mt5_server": "Maven-Demo",
            "mt5_terminal_path": "C:\\MT5\\terminal64.exe",
            "mt5_symbol_map": {
                "ETH/USDT": "ETH",
                "SOL/USDT": "SOL",
                "XRP/USDT": "XXRP",
            },
            "symbol": "ETH/USDT",
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["result"]["execution_backend"] == "mt5"
    assert body["result"]["symbol_status"]["resolved_symbol"] == "ETH"
    assert body["result"]["symbol_status"]["available"] is True
    assert body["result"]["symbol_status"]["has_live_tick"] is True


def test_ops_service_account_state_endpoint_returns_drawdown_oversight(monkeypatch):
    monkeypatch.setattr("config.settings.SUPABASE_URL", "https://supabase.example.test")
    monkeypatch.setattr("config.settings.SUPABASE_KEY", "service-role-key")

    app = build_trade_oracle_ops_app(
        require_auth=False,
        phase2_scanner_runner=_fake_phase2_scanner_runner,
        live_scanner_runner=_fake_live_scanner_runner,
        match_trader_api_cls=_FakeMatchTraderAPI,
        state_manager_factory=_FakeStateManager,
    )
    client = TestClient(app)

    response = client.post(
        "/ops/account/state",
        json={
            "execution_backend": "match_trader",
            "broker_id": "broker",
            "email": "user@example.com",
            "password": "secret",
            "base_url": "https://example.test",
            "system_uuid": "SYSTEM_123",
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["result"]["current_equity"] == 5125.0
    assert body["result"]["high_watermark"] == 5250.0
    assert body["result"]["high_watermark_source"] == "supabase"
    assert body["result"]["distance_to_failure_usd"] == 32.5
    assert body["result"]["warning_buffer_triggered"] is False
    assert body["result"]["can_open_new_trade"] is True


def test_ops_service_account_state_endpoint_falls_back_when_state_store_unavailable(monkeypatch):
    monkeypatch.setattr("config.settings.SUPABASE_URL", "https://supabase.example.test")
    monkeypatch.setattr("config.settings.SUPABASE_KEY", "service-role-key")

    app = build_trade_oracle_ops_app(
        require_auth=False,
        phase2_scanner_runner=_fake_phase2_scanner_runner,
        live_scanner_runner=_fake_live_scanner_runner,
        match_trader_api_cls=_FakeMatchTraderAPI,
        state_manager_factory=_FailingStateManager,
    )
    client = TestClient(app)

    response = client.post(
        "/ops/account/state",
        json={
            "execution_backend": "match_trader",
            "broker_id": "broker",
            "email": "user@example.com",
            "password": "secret",
            "base_url": "https://example.test",
            "system_uuid": "SYSTEM_123",
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["result"]["high_watermark"] == 5125.0
    assert body["result"]["high_watermark_source"] == "fallback_current_equity"
    assert "Supabase unavailable for test" in body["result"]["fallback_reason"]


def test_ops_service_writes_benchmark_events_for_risk_and_transmit():
    cycle_id = "cycle-ops-001"
    app = build_trade_oracle_ops_app(
        require_auth=False,
        phase2_scanner_runner=_fake_phase2_scanner_runner,
        live_scanner_runner=_fake_live_scanner_runner,
        mt5_bridge_cls=_FakeMT5Bridge,
        benchmark_db_path="results/test_trade_oracle_ops_benchmark.sqlite",
    )
    client = TestClient(app)

    risk_response = client.post(
        "/ops/risk/evaluate",
        json={
            "symbol": "AVAX/USDT",
            "current_balance": 5100.0,
            "highest_equity": 5150.0,
            "active_trades_count": 1,
            "entry_price": 41.25,
            "atr": 1.35,
            "direction": "BUY",
            "run_id": "run-ops-risk-001",
            "cycle_id": cycle_id,
            "benchmark_variant": "super_brain",
        },
    )
    risk_body = risk_response.json()

    assert risk_response.status_code == 200
    assert risk_body["result"]["cycle_id"] == cycle_id

    transmit_response = client.post(
        "/ops/execution/transmit-limit-order",
        json={
            "execution_backend": "mt5",
            "mt5_login": 12345678,
            "mt5_password": "secret",
            "mt5_server": "Maven-Demo",
            "mt5_terminal_path": "C:\\MT5\\terminal64.exe",
            "symbol": "AVAX/USDT",
            "direction": "BUY",
            "size": 4.93827,
            "size_mode": "units",
            "limit_price": 41.25,
            "stop_loss": 39.225,
            "take_profit": 43.95,
            "run_id": "run-ops-transmit-001",
            "cycle_id": cycle_id,
            "benchmark_variant": "super_brain",
        },
    )
    transmit_body = transmit_response.json()

    assert transmit_response.status_code == 200
    assert transmit_body["result"]["cycle_id"] == cycle_id

    store = TradeOracleBenchmarkStore("results/test_trade_oracle_ops_benchmark.sqlite")
    cycle_events = store.list_cycle_events(cycle_id, limit=20)
    event_types = {event.event_type for event in cycle_events}

    assert "risk_check" in event_types
    assert "order_transmit_attempt" in event_types
    assert "order_transmit_result" in event_types
    assert any(
        event.execution_backend == "mt5" and event.symbol == "AVAX/USDT"
        for event in cycle_events
        if event.event_type == "order_transmit_result"
    )
