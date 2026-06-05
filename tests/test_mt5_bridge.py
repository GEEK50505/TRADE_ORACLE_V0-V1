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
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TYPE_BUY_LIMIT = 2
    ORDER_TYPE_SELL_LIMIT = 3
    ORDER_TYPE_BUY_STOP = 4
    ORDER_TYPE_SELL_STOP = 5
    TRADE_ACTION_DEAL = 1
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
            point=0.01,
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


class _FakeMT5DuplicatePendingOrderModule(_FakeMT5OrderModule):
    def __init__(self):
        super().__init__()
        self.order_send_called = False

    def orders_get(self, symbol=None):
        return (
            SimpleNamespace(
                symbol="AVAUSD",
                magic=26042026,
                type=self.ORDER_TYPE_BUY_LIMIT,
                price_open=9.40,
                volume_initial=0.01,
                sl=8.83,
                tp=10.30,
                comment="TRADE_ORACLE_BUY_LIMIT",
            ),
        )

    def order_send(self, request):
        self.order_send_called = True
        return super().order_send(request)


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


def test_mt5_bridge_routes_near_market_buy_to_market_order(monkeypatch):
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
    assert fake_module.request["action"] == fake_module.TRADE_ACTION_DEAL
    assert fake_module.request["type"] == fake_module.ORDER_TYPE_BUY
    assert fake_module.request["price"] == 9.46


def test_mt5_bridge_routes_buy_above_market_to_buy_stop(monkeypatch):
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
            9.60,
            8.83,
            10.30,
            "units",
        )
        is True
    )
    assert fake_module.request["action"] == fake_module.TRADE_ACTION_PENDING
    assert fake_module.request["type"] == fake_module.ORDER_TYPE_BUY_STOP
    assert fake_module.request["price"] == 9.60


def test_mt5_bridge_treats_existing_matching_pending_order_as_idempotent_success(monkeypatch):
    fake_module = _FakeMT5DuplicatePendingOrderModule()
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
            9.40,
            8.83,
            10.30,
            "units",
        )
        is True
    )
    assert fake_module.order_send_called is False


def test_mt5_bridge_rejects_invalid_buy_levels_before_order_send(monkeypatch):
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
            9.80,
            10.30,
            "units",
        )
        is False
    )
    assert fake_module.request is None


def test_mt5_bridge_floors_volume_when_below_minimum_but_low_risk(monkeypatch):
    fake_module = _FakeMT5OrderModule()
    monkeypatch.setattr("execution.mt5_bridge._mt5", fake_module)
    monkeypatch.setattr("config.settings.RISK_AMOUNT_USD", 10.00)

    bridge = MetaTraderBridge(
        login=1513212902,
        password="secret",
        server="FTMO-Demo",
        terminal_path=r"C:\Program Files\MetaTrader 5\terminal64.exe",
        symbol_map={"AVAX/USDT": "AVAUSD"},
    )

    # 5.55556 units with entry=9.46, sl=8.83 resolves to raw volume 0.00555 (below minimum volume 0.01)
    # Resulting risk = 0.01 * 1000 * abs(9.46 - 8.83) = $6.30 (within $20.00 max risk)
    assert (
        bridge._transmit_limit_order_sync(
            "AVAX/USDT",
            "BUY",
            5.55556,
            9.46,
            8.83,
            10.30,
            "units",
        )
        is True
    )
    assert fake_module.request["volume"] == 0.01


def test_mt5_bridge_rejects_floored_volume_when_risk_exceeds_max(monkeypatch):
    fake_module = _FakeMT5OrderModule()
    monkeypatch.setattr("execution.mt5_bridge._mt5", fake_module)
    monkeypatch.setattr("config.settings.RISK_AMOUNT_USD", 10.00)

    bridge = MetaTraderBridge(
        login=1513212902,
        password="secret",
        server="FTMO-Demo",
        terminal_path=r"C:\Program Files\MetaTrader 5\terminal64.exe",
        symbol_map={"AVAX/USDT": "AVAUSD"},
    )

    # 5.55556 units with entry=9.46, sl=7.00 resolves to raw volume 0.00555
    # Resulting risk = 0.01 * 1000 * abs(9.46 - 7.00) = $24.60 (exceeds $20.00 max risk)
    assert (
        bridge._transmit_limit_order_sync(
            "AVAX/USDT",
            "BUY",
            5.55556,
            9.46,
            7.00,
            10.30,
            "units",
        )
        is False
    )
    assert fake_module.request is None
