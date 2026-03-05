"""
Phase 1 Deliverable: config/settings.py
This module establishes the immutable parameters, asset watchlists, and secure API 
credentials required to govern the TRADE_ORACLE system. It translates Maven Trading's 
proprietary firm rules into strict numerical thresholds to prevent algorithmic failure.
"""


# config/settings.py
import os
from dotenv import load_dotenv

# Initialize environmental variables for secure credential routing
# Guarantees environment determinism and prevents key leakage in version control
load_dotenv()

# ==============================================================================
# MAVEN TRADING PROPRIETARY FIRM RISK PARAMETERS
# ==============================================================================
# Baseline simulated account funding allocation
INITIAL_BALANCE = 5000.0

# Strategic Risk Pivot: Hardcoded to exactly $10.00 to maximize drawdown survival.
# Mathematically permits 15 consecutive losses before the $150 trailing limit is breached.
RISK_AMOUNT_USD = 10.00 

# Institutional Limits & Mathematical Boundaries
MAX_FLOATING_LOSS_PCT = 0.01        # 1% max intraday drawdown limit ($50 absolute cap)
MAX_TRAILING_DRAWDOWN_PCT = 0.03    # 3% trailing from highest equity watermark ($150 limit)
MAX_CRYPTO_LEVERAGE = 2.0           # 1:2 strict proprietary leverage limit for digital assets

# Concurrency Limit Optimization
# While $50 / $10 theoretically allows 5 trades, a hard cap of 4 is instituted to
# reserve $10 of floating equity to absorb critical spread widening and slippage.
# This prevents the algorithm from breaching the firm's gambling and exposure rules.
MAX_CONCURRENT_TRADES = 4           

# Profit Taking and Consistency Rule Mitigation Parameters
# These multipliers dictate the fractional scale-out logic to bypass the 20% rule
TP1_ATR_MULTIPLIER = 2.0            # Scale out 50% of the active position at 2.0x ATR
TP2_ATR_MULTIPLIER = 3.5            # Close the remaining 50% of the position at 3.5x ATR
STOP_LOSS_ATR_MULTIPLIER = 1.5      # Structural invalidation point set to 1.5x ATR

# ==============================================================================
# ALGORITHMIC WATCHLIST (High-Liquidity Pairs)
# ==============================================================================
# Restricted entirely to major market capitalization assets to prevent execution slippage
WATCHLIST = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 'AVAX/USDT', 'LINK/USDT', 'TON/USDT', 'ADA/USDT', 'BNB/USDT']

# ==============================================================================
# SECURE API CREDENTIAL ROUTING
# ==============================================================================
# Artificial Intelligence Inference Engine (e.g., Grok 4.20 / DeepSeek-V3.2)
AI_API_KEY = os.getenv("AI_API_KEY")

# Phase 1 Persistent State Memory (PostgreSQL Cluster)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Phase 4 Autonomous Execution Bridge (Match-Trader)
MATCH_TRADER_USER = os.getenv("MATCH_TRADER_USER")
MATCH_TRADER_PASS = os.getenv("MATCH_TRADER_PASS")
MATCH_TRADER_BROKER_ID = os.getenv("MATCH_TRADER_BROKER_ID")

# Fallback to the known production URL if the environment variable is missing
MATCH_TRADER_BASE_URL = os.getenv("MATCH_TRADER_BASE_URL", "https://mtr-api.match-trader.com")