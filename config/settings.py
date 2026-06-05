"""
Phase 1 Deliverable: config/settings.py
This module establishes the immutable parameters, asset watchlists, and secure API 
credentials required to govern the TRADE_ORACLE system. It translates Maven Trading's 
proprietary firm rules into strict numerical thresholds to prevent algorithmic failure.
"""


# config/settings.py
import os
import json
from dotenv import load_dotenv

# Initialize environmental variables for secure credential routing
# Guarantees environment determinism and prevents key leakage in version control
load_dotenv()


def _parse_list_env(name: str, default: list[str]) -> list[str]:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return list(default)
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [item.strip() for item in raw_value.split(",") if item.strip()]

# ==============================================================================
# MAVEN TRADING PROPRIETARY FIRM RISK PARAMETERS
# ==============================================================================
# Baseline simulated account funding allocation
INITIAL_BALANCE = 5000.0

# Strategic Risk Pivot: Hardcoded to exactly $10.00 to maximize drawdown survival.
# Mathematically permits 15 consecutive losses before the $150 trailing limit is breached.
RISK_AMOUNT_USD = float(os.getenv("TRADE_ORACLE_RISK_AMOUNT_USD", "20.00")) 

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
DEFAULT_WATCHLIST = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 'AVAX/USDT', 'LINK/USDT', 'TON/USDT', 'ADA/USDT', 'BNB/USDT']
WATCHLIST = _parse_list_env("TRADE_ORACLE_WATCHLIST", DEFAULT_WATCHLIST)
TRADE_ORACLE_DAEMON_WATCHLIST = _parse_list_env("TRADE_ORACLE_DAEMON_WATCHLIST", WATCHLIST)

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
TRADE_ORACLE_AUDIT_BACKEND = os.getenv("TRADE_ORACLE_AUDIT_BACKEND", "sqlite").strip().lower()
TRADE_ORACLE_AUDIT_DB_PATH = os.getenv("TRADE_ORACLE_AUDIT_DB_PATH", "results/trade_oracle_audit.sqlite")
TRADE_ORACLE_BENCHMARK_BACKEND = os.getenv("TRADE_ORACLE_BENCHMARK_BACKEND", "sqlite").strip().lower()
TRADE_ORACLE_BENCHMARK_DB_PATH = os.getenv("TRADE_ORACLE_BENCHMARK_DB_PATH", "results/trade_oracle_benchmark.sqlite")
TRADE_ORACLE_RUNTIME_STATE_BACKEND = os.getenv("TRADE_ORACLE_RUNTIME_STATE_BACKEND", "sqlite").strip().lower()
TRADE_ORACLE_RUNTIME_STATE_DB_PATH = os.getenv("TRADE_ORACLE_RUNTIME_STATE_DB_PATH", "results/trade_oracle_runtime_state.sqlite")
TRADE_ORACLE_BENCHMARK_VARIANT = os.getenv("TRADE_ORACLE_BENCHMARK_VARIANT", "super_brain").strip().lower() or "super_brain"
TRADE_ORACLE_SUPABASE_AUDIT_TABLE = os.getenv("TRADE_ORACLE_SUPABASE_AUDIT_TABLE", "trade_oracle_audit_events")
TRADE_ORACLE_SUPABASE_BENCHMARK_TABLE = os.getenv("TRADE_ORACLE_SUPABASE_BENCHMARK_TABLE", "trade_oracle_benchmark_events")
TRADE_ORACLE_SUPABASE_PENDING_REVIEW_TABLE = os.getenv("TRADE_ORACLE_SUPABASE_PENDING_REVIEW_TABLE", "trade_oracle_pending_reviews")
TRADE_ORACLE_SUPABASE_FORWARD_JOURNAL_TABLE = os.getenv("TRADE_ORACLE_SUPABASE_FORWARD_JOURNAL_TABLE", "trade_oracle_forward_journal")
TRADE_ORACLE_SUPABASE_DAEMON_CHECKPOINT_TABLE = os.getenv("TRADE_ORACLE_SUPABASE_DAEMON_CHECKPOINT_TABLE", "trade_oracle_daemon_checkpoints")
TRADE_ORACLE_CURRENT_BALANCE = float(os.getenv("TRADE_ORACLE_CURRENT_BALANCE", str(INITIAL_BALANCE)))
TRADE_ORACLE_HIGHEST_EQUITY = float(os.getenv("TRADE_ORACLE_HIGHEST_EQUITY", str(INITIAL_BALANCE)))
TRADE_ORACLE_ACTIVE_TRADES_COUNT = int(os.getenv("TRADE_ORACLE_ACTIVE_TRADES_COUNT", "0"))
TRADE_ORACLE_TELEGRAM_BOT_TOKEN = (
    os.getenv("TRADE_ORACLE_TELEGRAM_BOT_TOKEN")
    or os.getenv("TRADE_ORACLE_ALERT_TELEGRAM_BOT_TOKEN")
    or ""
)
TRADE_ORACLE_TELEGRAM_CHAT_ID = os.getenv("TRADE_ORACLE_TELEGRAM_CHAT_ID", "").strip()
TRADE_ORACLE_DAEMON_CYCLE_INTERVAL_SECONDS = int(os.getenv("TRADE_ORACLE_DAEMON_CYCLE_INTERVAL_SECONDS", "3600"))
TRADE_ORACLE_DAEMON_TELEGRAM_POLL_TIMEOUT_SECONDS = int(
    os.getenv("TRADE_ORACLE_DAEMON_TELEGRAM_POLL_TIMEOUT_SECONDS", "20")
)
TRADE_ORACLE_DAEMON_IDLE_SLEEP_SECONDS = float(os.getenv("TRADE_ORACLE_DAEMON_IDLE_SLEEP_SECONDS", "2"))
TRADE_ORACLE_DAEMON_START_IMMEDIATELY = os.getenv("TRADE_ORACLE_DAEMON_START_IMMEDIATELY", "1").strip().lower() in {"1", "true", "yes", "y"}
TRADE_ORACLE_DAEMON_SEND_CYCLE_SUMMARY = os.getenv("TRADE_ORACLE_DAEMON_SEND_CYCLE_SUMMARY", "1").strip().lower() in {"1", "true", "yes", "y"}
TRADE_ORACLE_DAEMON_AUTO_APPROVE_REVIEWS = os.getenv(
    "TRADE_ORACLE_DAEMON_AUTO_APPROVE_REVIEWS",
    "0",
).strip().lower() in {"1", "true", "yes", "y"}
TRADE_ORACLE_DAEMON_TELEGRAM_REQUEST_ATTEMPTS = int(
    os.getenv("TRADE_ORACLE_DAEMON_TELEGRAM_REQUEST_ATTEMPTS", "3")
)
TRADE_ORACLE_DAEMON_TELEGRAM_RETRY_BASE_SECONDS = float(
    os.getenv("TRADE_ORACLE_DAEMON_TELEGRAM_RETRY_BASE_SECONDS", "2")
)
TRADE_ORACLE_DAEMON_CYCLE_LOCK_PATH = os.getenv(
    "TRADE_ORACLE_DAEMON_CYCLE_LOCK_PATH",
    "results/trade_oracle_cycle.lock",
)
TRADE_ORACLE_DAEMON_CYCLE_LOCK_STALE_SECONDS = int(
    os.getenv("TRADE_ORACLE_DAEMON_CYCLE_LOCK_STALE_SECONDS", "7200")
)
TRADE_ORACLE_DAEMON_RUNTIME_LOCK_PATH = os.getenv(
    "TRADE_ORACLE_DAEMON_RUNTIME_LOCK_PATH",
    "results/trade_oracle_daemon_runtime.lock",
)
TRADE_ORACLE_DAEMON_RUNTIME_LOCK_STALE_SECONDS = int(
    os.getenv("TRADE_ORACLE_DAEMON_RUNTIME_LOCK_STALE_SECONDS", "21600")
)

# Phase 1 Persistent State Memory (PostgreSQL Cluster)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Phase 4 Autonomous Execution Bridge (Match-Trader)
MATCH_TRADER_USER = os.getenv("MATCH_TRADER_USER")
MATCH_TRADER_PASS = os.getenv("MATCH_TRADER_PASS")
MATCH_TRADER_BROKER_ID = os.getenv("MATCH_TRADER_BROKER_ID")

# Fallback to the known production URL if the environment variable is missing
MATCH_TRADER_BASE_URL = os.getenv("MATCH_TRADER_BASE_URL", "https://mtr-api.match-trader.com")

# Phase 4 Execution Backend Selection
# FTMO MT5 is the primary operational default.
TRADE_ORACLE_EXECUTION_BACKEND = os.getenv("TRADE_ORACLE_EXECUTION_BACKEND", "mt5").strip().lower()

# Phase 4 Alternative Execution Bridge (MetaTrader 5)
MT5_LOGIN = os.getenv("MT5_LOGIN")
MT5_PASSWORD = os.getenv("MT5_PASSWORD")
MT5_SERVER = os.getenv("MT5_SERVER")
MT5_TERMINAL_PATH = os.getenv("MT5_TERMINAL_PATH", "")
MT5_SYMBOL_SUFFIX = os.getenv("MT5_SYMBOL_SUFFIX", "")
try:
    MT5_SYMBOL_MAP = json.loads(os.getenv("MT5_SYMBOL_MAP", "{}") or "{}")
except json.JSONDecodeError:
    MT5_SYMBOL_MAP = {}
TRADE_ORACLE_MT5_DUPLICATE_GUARD_ENABLED = os.getenv(
    "TRADE_ORACLE_MT5_DUPLICATE_GUARD_ENABLED",
    "1",
).strip().lower() in {"1", "true", "yes", "y"}
TRADE_ORACLE_MT5_PRICE_TOLERANCE_POINTS = int(os.getenv("TRADE_ORACLE_MT5_PRICE_TOLERANCE_POINTS", "2"))

# Phase 4 Live Demo Execution Policy
# Keep the first supervised live phase simple unless partial-close support is proven.
TRADE_ORACLE_LIVE_TP_MODE = os.getenv("TRADE_ORACLE_LIVE_TP_MODE", "tp1_only").strip().lower()

# ==============================================================================
# PHASE 3 SHADOW MODE — Live LLM counterfactual A/B evaluation
# The shadow engine calls Google AI Studio on every cycle but NEVER transmits
# orders to MT5. Decisions are logged to Supabase under benchmark_variant
# 'v1_live_llm_shadow' for MAE/MFE tracking.
# ==============================================================================

# Master switch — set to "0" to disable the entire shadow path
TRADE_ORACLE_SHADOW_MODE_ENABLED: bool = (
    os.getenv("TRADE_ORACLE_SHADOW_MODE_ENABLED", "1").strip().lower()
    in {"1", "true", "yes", "y"}
)

# Google AI Studio key (the model registry reads GOOGLE_API_KEY; GEMINI_API_KEY
# is the legacy name used by inference.py standalone diagnostics only)
GOOGLE_API_KEY: str | None = os.getenv("GOOGLE_API_KEY")

# Inter-call cooldown enforced by asyncio.Lock — prevents >9 RPM under any load
TRADE_ORACLE_SHADOW_LLM_COOLDOWN_SECONDS: float = float(
    os.getenv("TRADE_ORACLE_SHADOW_LLM_COOLDOWN_SECONDS", "6.5")
)

# Worker-bee model for standard cycles (15 RPM free tier)
TRADE_ORACLE_SHADOW_LLM_MODEL_WORKER: str = os.getenv(
    "TRADE_ORACLE_SHADOW_LLM_MODEL_WORKER", "gemini-2.0-flash"
)

# Synthesis model for high-conviction setups (10 RPM free tier)
# gemini-2.5-pro is EXCLUDED to protect its much lower daily quota
TRADE_ORACLE_SHADOW_LLM_MODEL_SYNTHESIS: str = os.getenv(
    "TRADE_ORACLE_SHADOW_LLM_MODEL_SYNTHESIS", "gemini-2.5-flash"
)

# Confidence threshold above which the synthesis model is preferred
TRADE_ORACLE_SHADOW_LLM_CONFIDENCE_THRESHOLD: float = float(
    os.getenv("TRADE_ORACLE_SHADOW_LLM_CONFIDENCE_THRESHOLD", "0.75")
)

# Supabase benchmark_variant tag for shadow journal entries
TRADE_ORACLE_SHADOW_BENCHMARK_VARIANT: str = os.getenv(
    "TRADE_ORACLE_SHADOW_BENCHMARK_VARIANT", "v1_live_llm_shadow"
)
