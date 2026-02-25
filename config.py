# config.py - All your settings in one place

# Your watchlist (add more alts as you like)
WATCHLIST = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", 
    "XRP/USDT", "DOGE/USDT", "AVAX/USDT", 
    "LINK/USDT", "TON/USDT", "ADA/USDT", "BNB/USDT"
]

# Timeframes
TIMEFRAMES = {
    "weekly": "1w",
    "daily": "1d",
    "4h": "4h"
}

# Risk settings
RISK_PER_TRADE = 0.005   # 0.5%
MAX_OPEN_TRADES = 1

# Trading parameters
MIN_CONFIDENCE_SCORE = 8.0
HOLD_PERIOD_DAYS = 7     # Average target

# API settings (if you add more later)
API_RATE_LIMIT_DELAY = 1.0  # seconds between requests