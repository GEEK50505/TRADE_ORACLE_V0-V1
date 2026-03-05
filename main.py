# main.py
import asyncio
import logging
from config import settings
from data.scanner import MarketScanner
from ai.inference import AIOrchestrator
from risk.manager import RiskManager
from execution.match_trader import MatchTraderAPI
from journal.supabase_client import StateManager

# Configure the root logger for the entire autonomous pipeline
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("TRADE_ORACLE.Core_Orchestrator")

async def autonomous_execution_loop():
    logger.info("Initializing TRADE_ORACLE Phase 4 Autonomous Pipeline...")
    
    # -----------------------------------------------------------------------
    # 1. Platform Authentication and State Verification
    # -----------------------------------------------------------------------
    trader_api = MatchTraderAPI(
        broker_id=settings.MATCH_TRADER_BROKER_ID,
        email=settings.MATCH_TRADER_USER,
        password=settings.MATCH_TRADER_PASS,
        base_url=settings.MATCH_TRADER_BASE_URL
    )
    
    if not await trader_api.authenticate():
        logger.critical("Fatal Error: Authentication with Match-Trader failed. Terminating pipeline.")
        return
        
    platform_data = await trader_api.get_platform_details()
    if not platform_data:
        logger.error("Failed to retrieve platform state from the broker ledger. Halting to prevent state corruption.")
        return
        
    current_live_equity = platform_data['equity']
    active_trades = platform_data['active_trades']
    
    # Initialize Phase 1 Supabase Persistent Memory State
    state_db = StateManager()
    
    # The database native GREATEST trigger ensures the watermark only ratchets upwards
    historical_peak_equity = state_db.update_high_watermark(current_live_equity)
    logger.info(f"Supabase Synchronization Complete. Peak Watermark Locked at: ${historical_peak_equity:.2f} | Active Trades: {active_trades}")
    
    # -----------------------------------------------------------------------
    # 2. Institutional Risk Audit (Phase 4)
    # -----------------------------------------------------------------------
    risk_engine = RiskManager(
        current_balance=current_live_equity, 
        highest_equity=historical_peak_equity,
        active_trades_count=active_trades
    )
    
    if not risk_engine.can_open_new_trade():
        logger.warning("Pipeline halted: System is currently at concurrency capacity or residing in critical drawdown territory.")
        return

    # -----------------------------------------------------------------------
    # 3. Quantitative Market Scanning (Phase 2)
    # -----------------------------------------------------------------------
    logger.info("Initiating Phase 2 Quantitative Market Scan...")
    scanner = MarketScanner(settings.WATCHLIST)
    raw_setups = await scanner.run_scan()
    
    if not raw_setups:
        logger.info("No valid structural confluences detected across the liquidity matrix. System remaining in cash.")
        return
        
    logger.info(f"Scanner successfully detected {len(raw_setups)} potential structural setups.")

    # -----------------------------------------------------------------------
    # 4. AI Contextual Synthesis & Validation (Phase 3)
    # -----------------------------------------------------------------------
    logger.info("Routing setups to Phase 3 Artificial Intelligence Orchestrator...")
    ai_agent = AIOrchestrator(api_key=settings.AI_API_KEY)
    
    # The orchestrator returns an array of Pydantic validated objects containing ranked setups
    optimal_setups = await ai_agent.evaluate_and_rank(raw_setups)
    
    if not optimal_setups:
        logger.info("AI Orchestrator rejected all setups based on fundamental headwinds or structural anomalies.")
        return

    # -----------------------------------------------------------------------
    # 5. Position Sizing & Iterative Execution Routing (Phase 4)
    # -----------------------------------------------------------------------
    for setup in optimal_setups:
        # Check authorization and ensure the loop hasn't breached the 4-trade maximum
        if not setup.execute_trade or not risk_engine.can_open_new_trade():
            continue
            
        # Extract the precise dynamic ATR generated during the Phase 2 localized scan
        target_atr = next((item['atr'] for item in raw_setups if item['symbol'] == setup.symbol), 0)
        
        execution_params = risk_engine.calculate_position_size(
            entry_price=setup.entry_price,
            atr=target_atr,
            direction=setup.direction
        )
        
        if not execution_params:
            logger.error(f"Failed to generate valid mathematical position sizing for {setup.symbol}.")
            continue
            
        logger.info(f"Calculated Parameters for {setup.symbol}: Vol={execution_params['tokens']} | TP1 Target={execution_params['tp1']}")
        
        # Transmit the finalized order via the REST API bridge
        order_success = await trader_api.transmit_limit_order(
            symbol=setup.symbol,
            direction=setup.direction,
            size=execution_params['tokens'],
            limit_price=execution_params['entry_price'],
            stop_loss=execution_params['stop_loss'],
            take_profit=execution_params['tp1']  # Target exactly TP1 to force fractional scale-out logic
        )
        
        if order_success:
            # Increment the local counter to prevent subsequent iterations from breaching the limit
            risk_engine.active_trades += 1
            logger.info(f"Order Successfully Transmitted. Portfolio Concurrency updated to: {risk_engine.active_trades}")

if __name__ == "__main__":
    # Ensure Windows operating system compatibility for complex asynchronous event loops
    # Bypasses the known aiohttp/Windows ProactorEventLoop teardown exception
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass
        
    # Execute the master coroutine
    asyncio.run(autonomous_execution_loop())