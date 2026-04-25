"""Focused tests for execution backend selection and client construction."""

from execution.runtime import build_execution_client_from_settings, resolve_execution_backend


class _FakeMatchTraderAPI:
    def __init__(self, broker_id, email, password, base_url):
        self.broker_id = broker_id
        self.email = email
        self.password = password
        self.base_url = base_url
        self.system_uuid = ""


class _FakeMT5Bridge:
    def __init__(self, *, login, password, server, terminal_path=None, symbol_suffix="", symbol_map=None):
        self.login = int(login)
        self.password = password
        self.server = server
        self.terminal_path = terminal_path or ""
        self.symbol_suffix = symbol_suffix
        self.symbol_map = symbol_map or {}


def test_resolve_execution_backend_falls_back_to_match_trader_for_invalid_value():
    assert resolve_execution_backend("not_real") == "match_trader"


def test_build_execution_client_from_settings_uses_match_trader(monkeypatch):
    monkeypatch.setattr("config.settings.TRADE_ORACLE_EXECUTION_BACKEND", "match_trader")
    monkeypatch.setattr("config.settings.MATCH_TRADER_BROKER_ID", "broker")
    monkeypatch.setattr("config.settings.MATCH_TRADER_USER", "user@example.com")
    monkeypatch.setattr("config.settings.MATCH_TRADER_PASS", "secret")
    monkeypatch.setattr("config.settings.MATCH_TRADER_BASE_URL", "https://example.test")

    client = build_execution_client_from_settings(match_trader_api_cls=_FakeMatchTraderAPI)

    assert isinstance(client, _FakeMatchTraderAPI)
    assert client.broker_id == "broker"


def test_build_execution_client_from_settings_uses_mt5(monkeypatch):
    monkeypatch.setattr("config.settings.TRADE_ORACLE_EXECUTION_BACKEND", "mt5")
    monkeypatch.setattr("config.settings.MT5_LOGIN", "12345678")
    monkeypatch.setattr("config.settings.MT5_PASSWORD", "secret")
    monkeypatch.setattr("config.settings.MT5_SERVER", "Maven-Demo")
    monkeypatch.setattr("config.settings.MT5_TERMINAL_PATH", "C:\\MT5\\terminal64.exe")
    monkeypatch.setattr("config.settings.MT5_SYMBOL_SUFFIX", "")
    monkeypatch.setattr("config.settings.MT5_SYMBOL_MAP", {"ETH/USDT": "ETH"})

    client = build_execution_client_from_settings(mt5_bridge_cls=_FakeMT5Bridge)

    assert isinstance(client, _FakeMT5Bridge)
    assert client.login == 12345678
    assert client.server == "Maven-Demo"
    assert client.symbol_map["ETH/USDT"] == "ETH"
