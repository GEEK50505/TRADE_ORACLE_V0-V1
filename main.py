import asyncio
from config import settings
from data.scanner import MarketScanner
from ai.inference import AIOrchestrator
from risk.manager import RiskManager
from quantum.optimizer import QuantumOptimizer
from journal.supabase_client import StateManager

async def main():
    print("Initializing TRADE_ORACLE Hybrid Architecture...")
    
    # 1. State Verification via Supabase
    state_db = StateManager()
    # (Mock live balance fetching for demonstration)
    current_live_balance = 5050.0 
    historical_peak_equity = state_db.update_high_watermark(current_live_balance)

    # 2. Quantitative Multidirectional Scanning
    scanner = MarketScanner(settings.WATCHLIST)
    raw_setups = await scanner.run_scan()
    
    if not raw_setups:
        print("No valid structural confluences detected. System remaining in cash.")
        return

    # 3. AI Contextual Synthesis & JSON Generation
    ai_agent = AIOrchestrator(settings.AI_API_KEY)
    structured_ai_output = await ai_agent.generate_optimal_setup(raw_setups)
    
    # 4. Optimization (Classical Heuristic now, QPU ready)
    optimizer = QuantumOptimizer(use_qpu=False)
    optimal_target = optimizer.solve_portfolio([structured_ai_output]) 
    
    # 5. Strict Risk Mathematics
    risk_engine = RiskManager(settings, current_live_balance, historical_peak_equity)
    risk_engine.validate_trailing_drawdown()
    
    final_position_size = risk_engine.calculate_position_size(
        entry_price=optimal_target.entry_price,
        stop_loss=optimal_target.stop_loss
    )
    
    print(f"Final Execution Approved: {optimal_target.ticker} - Size: {final_position_size}")
    # 6. Transmit to Match-Trader API

if __name__ == "__main__":
    asyncio.run(main())