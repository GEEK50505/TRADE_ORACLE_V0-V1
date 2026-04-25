"""Focused tests for the LangGraph execution bridge."""

import asyncio
from pathlib import Path

from ai.langgraph_orchestrator import LangGraphSupervisorOrchestrator, resolve_live_take_profit


def test_langgraph_supervisor_orchestrator_returns_execution_candidate_when_auto_approved():
    checkpointer_path = Path("results/test_langgraph_orchestrator_auto.sqlite")
    orchestrator = LangGraphSupervisorOrchestrator(
        checkpointer_path=checkpointer_path,
        auto_approve=True,
    )

    candidates = asyncio.run(
        orchestrator.evaluate_and_rank(
            [
                {
                    "symbol": "SOL/USDT",
                    "regime": "BULLISH",
                    "current_price": 145.0,
                    "atr": 9.25,
                    "fibonacci_convergence_proximity": 0.011,
                    "ema_cluster_distance": 0.007,
                    "setup_quality": 0.88,
                }
            ],
            current_balance=5200.0,
            highest_equity=5300.0,
            active_trades_count=1,
        )
    )

    assert len(candidates) == 1
    assert candidates[0].execute_trade is True
    assert candidates[0].symbol == "SOL/USDT"
    assert candidates[0].direction == "BUY"
    assert candidates[0].size_tokens > 0


def test_langgraph_supervisor_orchestrator_returns_no_candidates_without_approval():
    checkpointer_path = Path("results/test_langgraph_orchestrator_pending.sqlite")
    orchestrator = LangGraphSupervisorOrchestrator(
        checkpointer_path=checkpointer_path,
        auto_approve=False,
    )

    candidates = asyncio.run(
        orchestrator.evaluate_and_rank(
            [
                {
                    "symbol": "ETH/USDT",
                    "regime": "BEARISH",
                    "current_price": 2010.0,
                    "atr": 125.5,
                    "fibonacci_convergence_proximity": 0.012,
                    "ema_cluster_distance": 0.009,
                    "setup_quality": 0.81,
                }
            ],
            current_balance=5200.0,
            highest_equity=5300.0,
            active_trades_count=1,
        )
    )

    assert candidates == []


def test_resolve_live_take_profit_defaults_to_tp1(monkeypatch):
    monkeypatch.setattr("config.settings.TRADE_ORACLE_LIVE_TP_MODE", "tp1_only")

    take_profit, mode = resolve_live_take_profit(
        {"tp1": 10.25, "tp2": 10.91}
    )

    assert take_profit == 10.25
    assert mode == "tp1_only"


def test_resolve_live_take_profit_can_switch_to_tp2(monkeypatch):
    monkeypatch.setattr("config.settings.TRADE_ORACLE_LIVE_TP_MODE", "tp2_full")

    take_profit, mode = resolve_live_take_profit(
        {"tp1": 10.25, "tp2": 10.91}
    )

    assert take_profit == 10.91
    assert mode == "tp2_full"
