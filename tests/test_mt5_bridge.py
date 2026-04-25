"""Focused tests for MT5 bridge authentication behavior."""

from types import SimpleNamespace

from execution.mt5_bridge import MetaTraderBridge


class _FakeMT5AttachedSession:
    def __init__(self):
        self._initialized = False

    def initialize(self, **kwargs):
        self._initialized = True
        return True

    def last_error(self):
        return (1, "Success")

    def account_info(self):
        return SimpleNamespace(login=1513212902, server="FTMO-Demo")

    def terminal_info(self):
        return SimpleNamespace(connected=True)

    def login(self, *args, **kwargs):
        return False

    def shutdown(self):
        self._initialized = False


class _FakeMT5OrderModule:
    ORDER_TYPE_BUY_LIMIT = 2
    ORDER_TYPE_SELL_LIMIT = 3
    TRADE_ACTION_PENDING = 5
    ORDER_TIME_GTC = 1
    ORDER_FILLING_RETURN = 2
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_PLACED = 10008

    def __init__(self):
        self.request = None

    def initialize(self, **kwargs):
        return True

    def last_error(self):
        return (1, "Success")

    def account_info(self):
        return SimpleNamespace(login=1513212902, server="FTMO-Demo")

    def terminal_info(self):
        return SimpleNamespace(connected=True)

    def login(self, *args, **kwargs):
        return True

    def symbol_info(self, symbol):
        return SimpleNamespace(
            visible=True,
            trade_contract_size=1000.0,
            volume_min=0.01,
            volume_step=0.01,
            volume_max=5.0,
        )

    def symbol_select(self, symbol, enabled):
        return True

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=9.44, ask=9.46, last=0.0)

    def order_send(self, request):
        self.request = request
        return SimpleNamespace(retcode=self.TRADE_RETCODE_PLACED, comment="Placed")

    def shutdown(self):
        return None


class _FakeMT5FailedAuth:
    def initialize(self, **kwargs):
        return True

    def last_error(self):
        return (-6, "Terminal: Authorization failed")

    def account_info(self):
        return SimpleNamespace(login=999999, server="Wrong-Server")

    def terminal_info(self):
        return SimpleNamespace(connected=True)

    def login(self, *args, **kwargs):
        return False

    def shutdown(self):
        return None


def test_mt5_bridge_accepts_matching_attached_terminal_session(monkeypatch):
    fake_module = _FakeMT5AttachedSession()
    monkeypatch.setattr("execution.mt5_bridge._mt5", fake_module)

    bridge = MetaTraderBridge(
        login=1513212902,
        password="secret",
        server="FTMO-Demo",
        terminal_path=r"C:\Program Files\MetaTrader 5\terminal64.exe",
    )

    assert bridge._authenticate_sync() is True


def test_mt5_bridge_rejects_when_attached_session_mismatches_and_login_fails(monkeypatch):
    fake_module = _FakeMT5FailedAuth()
    monkeypatch.setattr("execution.mt5_bridge._mt5", fake_module)

    bridge = MetaTraderBridge(
        login=1513212902,
        password="secret",
        server="FTMO-Demo",
        terminal_path=r"C:\Program Files\MetaTrader 5\terminal64.exe",
    )

    assert bridge._authenticate_sync() is False


def test_mt5_bridge_converts_strategy_units_to_broker_volume(monkeypatch):
    fake_module = _FakeMT5OrderModule()
    monkeypatch.setattr("execution.mt5_bridge._mt5", fake_module)

    bridge = MetaTraderBridge(
        login=1513212902,
        password="secret",
        server="FTMO-Demo",
        terminal_path=r"C:\Program Files\MetaTrader 5\terminal64.exe",
        symbol_map={"AVAX/USDT": "AVAUSD"},
    )

    assert (
        bridge._transmit_limit_order_sync(
            "AVAX/USDT",
            "BUY",
            15.87302,
            9.46,
            8.83,
            10.30,
            "units",
        )
        is True
    )
    assert fake_module.request["symbol"] == "AVAUSD"
    assert fake_module.request["volume"] == 0.01


def test_mt5_bridge_allows_explicit_broker_volume_mode(monkeypatch):
    fake_module = _FakeMT5OrderModule()
    monkeypatch.setattr("execution.mt5_bridge._mt5", fake_module)

    bridge = MetaTraderBridge(
        login=1513212902,
        password="secret",
        server="FTMO-Demo",
        terminal_path=r"C:\Program Files\MetaTrader 5\terminal64.exe",
        symbol_map={"AVAX/USDT": "AVAUSD"},
    )

    assert (
        bridge._transmit_limit_order_sync(
            "AVAX/USDT",
            "BUY",
            0.02,
            9.30,
            9.00,
            9.80,
            "broker_volume",
        )
        is True
    )
    assert fake_module.request["volume"] == 0.02
