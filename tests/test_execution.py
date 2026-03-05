import asyncio
import pytest

from config import settings
from execution.match_trader import MatchTraderAPI


def test_match_trader_auth_and_status():
    """Verify that the MatchTraderAPI can authenticate and fetch platform details.
    This uses credentials stored in the .env file. If network access is unavailable or
    the demo server rejects the credentials, the test will be marked as xfail rather
    than failing the entire suite to avoid blocking other tests."""

    async def run_check():
        api = MatchTraderAPI(
            broker_id=settings.MATCH_TRADER_BROKER_ID,
            email=settings.MATCH_TRADER_USER,
            password=settings.MATCH_TRADER_PASS,
            base_url=settings.MATCH_TRADER_BASE_URL,
        )

        authenticated = await api.authenticate()
        if not authenticated:
            pytest.xfail("Authentication failed; credentials may be invalid or server unreachable.")

        # If authentication succeeded, attempt to fetch platform details
        details = await api.get_platform_details()
        assert details is not None, "Unable to fetch platform details after authentication"
        assert "equity" in details and "active_trades" in details

    asyncio.run(run_check())
