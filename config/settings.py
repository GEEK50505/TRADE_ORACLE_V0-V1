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

# Phase 3 MCP FastAPI Bridge
TRADE_ORACLE_MCP_BASE_URL = os.getenv("TRADE_ORACLE_MCP_BASE_URL", "http://127.0.0.1:8000")
TRADE_ORACLE_MCP_API_KEY = os.getenv("TRADE_ORACLE_MCP_API_KEY")
TRADE_ORACLE_MCP_REQUIRE_AUTH = os.getenv("TRADE_ORACLE_MCP_REQUIRE_AUTH", "0").strip().lower() in {"1", "true", "yes", "y"}
TRADE_ORACLE_MCP_PROVIDER_MODE = os.getenv("TRADE_ORACLE_MCP_PROVIDER_MODE", "internal").strip().lower()
TRADE_ORACLE_MCP_PROVIDER_TIMEOUT = float(os.getenv("TRADE_ORACLE_MCP_PROVIDER_TIMEOUT", "10.0"))
TRADE_ORACLE_MCP_PROVIDER_API_KEY = os.getenv("TRADE_ORACLE_MCP_PROVIDER_API_KEY")
TRADE_ORACLE_MCP_MACRO_PROVIDER = os.getenv("TRADE_ORACLE_MCP_MACRO_PROVIDER", "coingecko").strip().lower()
TRADE_ORACLE_MCP_FUNDAMENTAL_PROVIDER = os.getenv("TRADE_ORACLE_MCP_FUNDAMENTAL_PROVIDER", "coingecko").strip().lower()
TRADE_ORACLE_MCP_TOKENOMICS_PROVIDER = os.getenv("TRADE_ORACLE_MCP_TOKENOMICS_PROVIDER", "coingecko").strip().lower()
TRADE_ORACLE_MCP_TECHNICAL_PROVIDER = os.getenv("TRADE_ORACLE_MCP_TECHNICAL_PROVIDER", "binance_public").strip().lower()
TRADE_ORACLE_MCP_MACRO_PROVIDER_MODE = os.getenv("TRADE_ORACLE_MCP_MACRO_PROVIDER_MODE", TRADE_ORACLE_MCP_PROVIDER_MODE).strip().lower()
TRADE_ORACLE_MCP_FUNDAMENTAL_PROVIDER_MODE = os.getenv("TRADE_ORACLE_MCP_FUNDAMENTAL_PROVIDER_MODE", TRADE_ORACLE_MCP_PROVIDER_MODE).strip().lower()
TRADE_ORACLE_MCP_TOKENOMICS_PROVIDER_MODE = os.getenv("TRADE_ORACLE_MCP_TOKENOMICS_PROVIDER_MODE", TRADE_ORACLE_MCP_PROVIDER_MODE).strip().lower()
TRADE_ORACLE_MCP_TECHNICAL_PROVIDER_MODE = os.getenv("TRADE_ORACLE_MCP_TECHNICAL_PROVIDER_MODE", TRADE_ORACLE_MCP_PROVIDER_MODE).strip().lower()
TRADE_ORACLE_MCP_MACRO_PROVIDER_URL = os.getenv("TRADE_ORACLE_MCP_MACRO_PROVIDER_URL", "")
TRADE_ORACLE_MCP_FUNDAMENTAL_PROVIDER_URL = os.getenv("TRADE_ORACLE_MCP_FUNDAMENTAL_PROVIDER_URL", "")
TRADE_ORACLE_MCP_TOKENOMICS_PROVIDER_URL = os.getenv("TRADE_ORACLE_MCP_TOKENOMICS_PROVIDER_URL", "")
TRADE_ORACLE_MCP_TECHNICAL_PROVIDER_URL = os.getenv("TRADE_ORACLE_MCP_TECHNICAL_PROVIDER_URL", "")
TRADE_ORACLE_COINGECKO_BASE_URL = os.getenv("TRADE_ORACLE_COINGECKO_BASE_URL", "https://api.coingecko.com/api/v3")
TRADE_ORACLE_COINGECKO_API_KEY = os.getenv("TRADE_ORACLE_COINGECKO_API_KEY")
TRADE_ORACLE_BINANCE_BASE_URL = os.getenv("TRADE_ORACLE_BINANCE_BASE_URL", "https://api.binance.com")
TRADE_ORACLE_BRAIN_API_KEY = os.getenv("TRADE_ORACLE_BRAIN_API_KEY")
TRADE_ORACLE_BRAIN_REQUIRE_AUTH = os.getenv("TRADE_ORACLE_BRAIN_REQUIRE_AUTH", "0").strip().lower() in {"1", "true", "yes", "y"}
TRADE_ORACLE_OPS_API_KEY = os.getenv("TRADE_ORACLE_OPS_API_KEY")
TRADE_ORACLE_OPS_REQUIRE_AUTH = os.getenv("TRADE_ORACLE_OPS_REQUIRE_AUTH", "0").strip().lower() in {"1", "true", "yes", "y"}
TRADE_ORACLE_PLATFORM_API_KEY = os.getenv("TRADE_ORACLE_PLATFORM_API_KEY")
TRADE_ORACLE_PLATFORM_REQUIRE_AUTH = os.getenv("TRADE_ORACLE_PLATFORM_REQUIRE_AUTH", "0").strip().lower() in {"1", "true", "yes", "y"}
TRADE_ORACLE_USE_LANGGRAPH = os.getenv("TRADE_ORACLE_USE_LANGGRAPH", "0").strip().lower() in {"1", "true", "yes", "y"}
TRADE_ORACLE_LANGGRAPH_AUTO_APPROVE = os.getenv("TRADE_ORACLE_LANGGRAPH_AUTO_APPROVE", "0").strip().lower() in {"1", "true", "yes", "y"}
TRADE_ORACLE_LANGGRAPH_CHECKPOINTER_PATH = os.getenv("TRADE_ORACLE_LANGGRAPH_CHECKPOINTER_PATH", "results/trade_oracle_phase1.sqlite")
TRADE_ORACLE_AUDIT_DB_PATH = os.getenv("TRADE_ORACLE_AUDIT_DB_PATH", "results/trade_oracle_audit.sqlite")

# Phase 1 Persistent State Memory (PostgreSQL Cluster)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Phase 4 Autonomous Execution Bridge (Match-Trader)
MATCH_TRADER_USER = os.getenv("MATCH_TRADER_USER")
MATCH_TRADER_PASS = os.getenv("MATCH_TRADER_PASS")
MATCH_TRADER_BROKER_ID = os.getenv("MATCH_TRADER_BROKER_ID")

# Fallback to the known production URL if the environment variable is missing
MATCH_TRADER_BASE_URL = os.getenv("MATCH_TRADER_BASE_URL", "https://mtr-api.match-trader.com")
