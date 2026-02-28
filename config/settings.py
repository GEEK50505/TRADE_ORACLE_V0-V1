"""
Phase 1 Deliverable: config/settings.py
This module establishes the immutable parameters, asset watchlists, and secure API 
credentials required to govern the TRADE_ORACLE system. It translates Maven Trading's 
proprietary firm rules into strict numerical thresholds to prevent algorithmic failure.
"""

import os
from dotenv import load_dotenv

# Initialize runtime environment variables from the hidden.env file
load_dotenv()

# ==========================================
# MAVEN TRADING RISK & SURVIVAL PARAMETERS
# ==========================================

# The absolute baseline starting balance of the proprietary account allocation.
INITIAL_BALANCE = 5000.0

# Mathematical maximum risk allocated to any single structural confluence setup.
# Enforces a strict 0.5% cap per trade, equating to exactly $25 on the baseline balance.
# This prevents intraday flash crashes from triggering maximum loss parameters.
RISK_PER_TRADE = 0.005          

# Intraday Floating Loss Constraint.
# Maven Instant accounts dictate that an operator cannot experience more than a 1% loss 
# in floating Profit and Loss (PnL) at any given moment.
MAX_FLOATING_LOSS = 0.01        

# The Maximum Trailing Drawdown Limit.
# Denotes the highly aggressive 3% algorithmic lock mapped strictly against the absolute 
# highest equity watermark the account achieves, inclusive of open floating profits.
MAX_TRAILING_DRAWDOWN = 0.03    

# Cryptocurrency Margin and Leverage Allowance.
# Maven strictly caps cryptocurrency leverage on Instant accounts to protect against 
# high-variance asset swings. This caps position sizing math.
MAX_CRYPTO_LEVERAGE = 2.0       

# ==========================================
# ASSET UNIVERSE & QUANTITATIVE WATCHLIST
# ==========================================

# Focus strictly on major liquidity pools and established digital assets to minimize 
# execution slippage and guarantee optimal match-trader API routing.
WATCHLIST =

# ==========================================
# EXTERNAL API ROUTING CREDENTIALS
# ==========================================

# AI Inference Layer Authentication
AI_API_KEY = os.getenv("AI_API_KEY") 

# Match-Trader Execution Bridge Authentication
MATCH_TRADER_USER = os.getenv("MATCH_TRADER_USER")
MATCH_TRADER_PASS = os.getenv("MATCH_TRADER_PASS")
MATCH_TRADER_BROKER_ID = os.getenv("MATCH_TRADER_BROKER_ID")

# Quantum Processing Unit Authentication
DWAVE_API_TOKEN = os.getenv("DWAVE_API_TOKEN") 

# Persistent State Database Authentication
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")