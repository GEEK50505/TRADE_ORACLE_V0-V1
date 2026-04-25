import asyncio

from execution.match_trader import MatchTraderAPI


class _FakeResponse:
    def __init__(self, body, status=200):
        self._body = body
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def json(self):
        return self._body


class _FakeClientSession:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def get(self, endpoint):
        return _FakeResponse({"account": {"equity": 5125.0}})


def test_match_trader_platform_details_handles_missing_positions(monkeypatch):
    monkeypatch.setattr("execution.match_trader.aiohttp.ClientSession", _FakeClientSession)

    api = MatchTraderAPI(
        broker_id="broker",
        email="user@example.com",
        password="secret",
        base_url="https://example.test",
    )
    api.token = "TOKEN"
    api.system_uuid = "SYSTEM_123"

    details = asyncio.run(api.get_platform_details())

    assert details is not None
    assert details["equity"] == 5125.0
    assert details["active_trades"] == 0
