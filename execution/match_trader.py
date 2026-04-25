# execution/match_trader.py
import aiohttp
import logging
from typing import Optional, Dict

class MatchTraderAPI:
    """
    Asynchronous REST API Bridge for the Match-Trader backend architecture.
    Handles token authentication, live concurrency tracking, and limit order routing
    directly to the simulated execution environment.
    """
    
    def __init__(self, broker_id: str, email: str, password: str, base_url: str):
        self.broker_id = broker_id
        self.email = email
        self.password = password
        self.base_url = base_url
        self.token = None
        # System UUID is required for order routing; sourced dynamically post-login in production
        self.system_uuid = "DEFAULT_SYSTEM_UUID" 
        self.headers = {"Content-Type": "application/json", "Accept": "application/json"}
        
        self.logger = logging.getLogger("TRADE_ORACLE.MatchTrader")
        if not self.logger.handlers:
            logging.basicConfig(level=logging.INFO)

    async def authenticate(self) -> bool:
        """
        Authenticates against the Match-Trader backend using the designated brokerId.
        Retrieves and stores the co-auth access token for subsequent REST routing.
        """
        # construct login endpoint (docs also mention /mtr-backend/login)
        endpoint = f"{self.base_url}/manager/co-login"
        payload = {
            "email": self.email,
            "password": self.password,
            "brokerId": self.broker_id
        }
        # DEBUG: show which URL and payload are being used
        self.logger.debug(f"Auth endpoint -> {endpoint}")
        self.logger.debug(f"Payload -> {payload}")
        
        try:
            # Utilize an asynchronous session context manager for connection pooling
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.token = data.get("token")
                        
                        # Platform API frequently utilizes cookie-based 'co-auth' or 'Auth-trading-api' headers
                        self.headers["Cookie"] = f"co-auth={self.token}" 
                        self.logger.info("Successfully authenticated with the Match-Trader API.")
                        return True
                    elif response.status in (401, 403):
                        self.logger.critical(f"Authentication Failed (HTTP {response.status}): Verify credentials or broker API access.")
                        return False
                    else:
                        self.logger.error(f"Unexpected Authentication Error: HTTP {response.status}")
                        return False
        except aiohttp.ClientError as e:
            self.logger.error(f"Network exception during authentication handshake: {e}")
            return False

    async def get_platform_details(self) -> Optional:
        """
        Retrieves real-time account equity and the count of currently open positions.
        This dual-fetch satisfies both the state memory trigger and the concurrency limiter.
        """
        if not self.token:
            return None
            
        # Abstracted unified endpoint for retrieving balance and active position count
        endpoint = f"{self.base_url}/mtr-api/{self.system_uuid}/platform-details"
        
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(endpoint) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Extract the current equity inclusive of floating unrealized PnL
                        equity = data.get("account", {}).get("equity", 0.0)
                        
                        # Calculate current concurrency footprint
                        open_positions = len(data.get("positions", []) or [])
                        
                        return {"equity": float(equity), "active_trades": open_positions}
                    elif response.status == 429:
                        self.logger.warning("Rate Limit Exceeded (HTTP 429). Throttling required.")
                        return None
                    else:
                        self.logger.error(f"Failed to fetch platform state: HTTP {response.status}")
                        return None
        except Exception as e:
            self.logger.error(f"Exception encountered while fetching state: {e}")
            return None

    async def transmit_limit_order(
        self,
        symbol: str,
        direction: str,
        size: float,
        limit_price: float,
        stop_loss: float,
        take_profit: float,
        size_mode: str = "units",
    ) -> bool:
        """
        Constructs and routes a pending Limit Order payload to the execution server.
        Adheres strictly to the expected REST payload format for the /pending-order/create endpoint.
        """
        if not self.token:
            self.logger.error("Cannot transmit order: API token is missing.")
            return False
            
        endpoint = f"{self.base_url}/mtr-api/{self.system_uuid}/pending-order/create"
        
        # Construct the specific JSON dictionary expected by Match-Trader
        payload = {
            "instrument": symbol.replace("/", ""), # Standardize ticker format (e.g., BTC/USDT to BTCUSDT)
            "orderSide": direction.upper(),        # Must be strictly "BUY" or "SELL"
            "volume": size,
            "price": limit_price,
            "type": "LIMIT",
            "slPrice": stop_loss,
            "tpPrice": take_profit,
            "isMobile": False
        }
        
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.post(endpoint, json=payload) as response:
                    if response.status in (200, 201):
                        self.logger.info(
                            "Order Transmitted: %s | Type: LIMIT | Vol: %s | Mode: %s | LMT: %s",
                            symbol,
                            size,
                            size_mode,
                            limit_price,
                        )
                        return True
                    else:
                        error_text = await response.text()
                        self.logger.error(f"Order Transmission Failed: HTTP {response.status} - Payload Rejected: {error_text}")
                        return False
        except Exception as e:
            self.logger.error(f"Fatal network exception during order routing: {e}")
            return False
