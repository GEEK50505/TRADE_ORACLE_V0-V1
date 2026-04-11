# main.py
import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Literal

from ai.langgraph_orchestrator import LangGraphSupervisorOrchestrator
from config import settings
from risk.manager import RiskManager

# Configure the root logger for the entire autonomous pipeline
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("TRADE_ORACLE.Core_Orchestrator")


@dataclass(slots=True)
class LegacyExecutionCandidate:
    """Normalized fallback candidate for the legacy AI orchestrator path."""

    execute_trade: bool
    symbol: str
    direction: Literal["BUY", "SELL"]
    entry_price: float
    rationale: str = ""


def _direction_from_scanner_regime(regime: str) -> Literal["BUY", "SELL"]:
    return "BUY" if str(regime).upper() == "BULLISH" else "SELL"


async def evaluate_setups_with_langgraph(
    raw_setups: list[dict[str, Any]],
    *,
    current_balance: float,
    highest_equity: float,
    active_trades_count: int,
) -> list[Any]:
    """Route scanner setups through the LangGraph supervisor bridge."""
    orchestrator = LangGraphSupervisorOrchestrator(
        checkpointer_path=settings.TRADE_ORACLE_LANGGRAPH_CHECKPOINTER_PATH,
        auto_approve=settings.TRADE_ORACLE_LANGGRAPH_AUTO_APPROVE,
        mcp_service_base_url=settings.TRADE_ORACLE_MCP_BASE_URL,
    )
    return await orchestrator.evaluate_and_rank(
        raw_setups,
        current_balance=current_balance,
        highest_equity=highest_equity,
        active_trades_count=active_trades_count,
    )


async def evaluate_setups_with_legacy_ai(raw_setups: list[dict[str, Any]]) -> list[LegacyExecutionCandidate]:
    """
    Fallback bridge for the legacy AIOrchestrator.

    The older module returns a single best setup, so this wrapper normalizes it into
    the list-based execution contract used by the Phase 4 loop.
    """
    from ai.inference import AIOrchestrator

    ai_agent = AIOrchestrator(model_provider="gemini")
    result = await ai_agent.generate_optimal_setup(raw_setups)
    if not result or not result.execute_trade:
        return []

    matched_row = next((row for row in raw_setups if row.get("symbol") == result.asset_ticker), None)
    if matched_row is None:
        logger.warning("Legacy AI selected %s, but no matching scanner row was found.", result.asset_ticker)
        return []

    return [
        LegacyExecutionCandidate(
            execute_trade=bool(result.execute_trade),
            symbol=str(result.asset_ticker),
            direction=_direction_from_scanner_regime(str(matched_row.get("regime", ""))),
            entry_price=float(result.entry_price),
            rationale=str(result.compliance_proof),
        )
    ]


async def autonomous_execution_loop():
    logger.info("Initializing TRADE_ORACLE Phase 4 Autonomous Pipeline...")

    from data.scanner import MarketScanner
    from execution.match_trader import MatchTraderAPI
    from journal.supabase_client import StateManager

    # -----------------------------------------------------------------------
    # 1. Platform Authentication and State Verification
    # -----------------------------------------------------------------------
    trader_api = MatchTraderAPI(
        broker_id=settings.MATCH_TRADER_BROKER_ID,
        email=settings.MATCH_TRADER_USER,
        password=settings.MATCH_TRADER_PASS,
        base_url=settings.MATCH_TRADER_BASE_URL,
    )

    if not await trader_api.authenticate():
        logger.critical("Fatal Error: Authentication with Match-Trader failed. Terminating pipeline.")
        return

    platform_data = await trader_api.get_platform_details()
    if not platform_data:
        logger.error("Failed to retrieve platform state from the broker ledger. Halting to prevent state corruption.")
        return

    current_live_equity = platform_data["equity"]
    active_trades = platform_data["active_trades"]

    # Initialize Phase 1 Supabase Persistent Memory State
    state_db = StateManager()

    # The database native GREATEST trigger ensures the watermark only ratchets upwards
    historical_peak_equity = state_db.update_high_watermark(current_live_equity)
    logger.info(
        "Supabase Synchronization Complete. Peak Watermark Locked at: $%.2f | Active Trades: %s",
        historical_peak_equity,
        active_trades,
    )

    # -----------------------------------------------------------------------
    # 2. Institutional Risk Audit (Phase 4)
    # -----------------------------------------------------------------------
    risk_engine = RiskManager(
        current_balance=current_live_equity,
        highest_equity=historical_peak_equity,
        active_trades_count=active_trades,
    )

    if not risk_engine.can_open_new_trade():
        logger.warning(
            "Pipeline halted: System is currently at concurrency capacity or residing in critical drawdown territory."
        )
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

    logger.info("Scanner successfully detected %s potential structural setups.", len(raw_setups))

    # -----------------------------------------------------------------------
    # 4. Phase 3 Orchestration
    # -----------------------------------------------------------------------
    if settings.TRADE_ORACLE_USE_LANGGRAPH:
        logger.info("Routing setups to the LangGraph supervisor bridge...")
        try:
            optimal_setups = await evaluate_setups_with_langgraph(
                raw_setups,
                current_balance=current_live_equity,
                highest_equity=historical_peak_equity,
                active_trades_count=active_trades,
            )
        except ImportError as exc:
            logger.warning(
                "LangGraph supervisor unavailable in this environment. Falling back to legacy AI path. Details: %s",
                exc,
            )
            optimal_setups = await evaluate_setups_with_legacy_ai(raw_setups)
    else:
        logger.info("Routing setups to the legacy AI orchestrator...")
        optimal_setups = await evaluate_setups_with_legacy_ai(raw_setups)

    if not optimal_setups:
        logger.info("No execution-ready setups were returned by the selected orchestration path.")
        return

    # -----------------------------------------------------------------------
    # 5. Position Sizing & Iterative Execution Routing (Phase 4)
    # -----------------------------------------------------------------------
    for setup in optimal_setups:
        if not setup.execute_trade or not risk_engine.can_open_new_trade():
            continue

        execution_params = None
        position_sizing = getattr(setup, "position_sizing", None)
        if isinstance(position_sizing, dict) and position_sizing.get("tokens"):
            execution_params = {
                "tokens": position_sizing.get("tokens"),
                "usd_value": position_sizing.get("usd_value"),
                "entry_price": position_sizing.get("entry_price", setup.entry_price),
                "stop_loss": position_sizing.get("stop_loss"),
                "tp1": position_sizing.get("tp1", getattr(setup, "take_profit", 0.0)),
                "tp2": position_sizing.get("tp2", getattr(setup, "take_profit", 0.0)),
            }
        else:
            target_atr = next((item["atr"] for item in raw_setups if item["symbol"] == setup.symbol), 0)
            execution_params = risk_engine.calculate_position_size(
                entry_price=setup.entry_price,
                atr=target_atr,
                direction=setup.direction,
            )

        if not execution_params:
            logger.error("Failed to generate valid mathematical position sizing for %s.", setup.symbol)
            continue

        logger.info(
            "Calculated Parameters for %s: Vol=%s | TP1 Target=%s",
            setup.symbol,
            execution_params["tokens"],
            execution_params["tp1"],
        )

        order_success = await trader_api.transmit_limit_order(
            symbol=setup.symbol,
            direction=setup.direction,
            size=execution_params["tokens"],
            limit_price=execution_params["entry_price"],
            stop_loss=execution_params["stop_loss"],
            take_profit=execution_params["tp1"],
        )

        if order_success:
            risk_engine.active_trades += 1
            logger.info("Order Successfully Transmitted. Portfolio Concurrency updated to: %s", risk_engine.active_trades)


if __name__ == "__main__":
    # Ensure Windows operating system compatibility for complex asynchronous event loops
    # Bypasses the known aiohttp/Windows ProactorEventLoop teardown exception
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass

    asyncio.run(autonomous_execution_loop())
