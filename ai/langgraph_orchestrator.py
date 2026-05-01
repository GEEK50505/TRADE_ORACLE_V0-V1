"""
Execution bridge that routes Phase 2 scanner setups through the LangGraph supervisor.

This module keeps the graph topology untouched. It adapts scanner rows into the
Phase 1 TradeState contract, optionally resumes human review with an injected
decision, and returns execution-ready candidates for the existing Phase 4 loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from config import settings
from .trade_oracle_storage import TradeOracleAuditStoreProtocol, build_trade_oracle_audit_store
from .trade_oracle_langgraph_phase1 import (
    AccountStateContext,
    build_initial_state,
    build_trade_oracle_graph,
    phase2_scanner_setup_to_raw_setup,
)


class LangGraphExecutionCandidate(BaseModel):
    """Normalized execution candidate emitted by the LangGraph supervisor bridge."""

    model_config = ConfigDict(extra="forbid")

    execute_trade: bool
    symbol: str
    direction: Literal["BUY", "SELL"]
    entry_price: float
    stop_loss: float
    take_profit: float
    size_tokens: float = 0.0
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    execution_status: str
    execution_tp_mode: str = ""
    review_required: bool = False
    rationale: str = ""
    position_sizing: dict[str, Any] = Field(default_factory=dict)
    final_decision: dict[str, Any] = Field(default_factory=dict)
    raw_setup: dict[str, Any] = Field(default_factory=dict)
    thread_id: str = ""


class LangGraphEvaluationResult(BaseModel):
    """Structured result for one LangGraph evaluation thread."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["pending_review", "completed", "no_trade"]
    thread_id: str
    interrupted: bool = False
    review_required: bool = False
    raw_setup: dict[str, Any] = Field(default_factory=dict)
    review_context: dict[str, Any] = Field(default_factory=dict)
    final_decision: dict[str, Any] = Field(default_factory=dict)
    gatekeeper_status: str = ""
    audit_trail: list[str] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    specialist_reports: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    thread_metadata: dict[str, Any] = Field(default_factory=dict)
    candidate: LangGraphExecutionCandidate | None = None


def resolve_live_take_profit(position_sizing: dict[str, Any]) -> tuple[float, str]:
    """Resolve the live-demo take-profit target from the configured execution policy."""

    tp_mode = str(settings.TRADE_ORACLE_LIVE_TP_MODE).strip().lower()
    tp1 = float(position_sizing.get("tp1", 0.0) or 0.0)
    tp2 = float(position_sizing.get("tp2", 0.0) or 0.0)

    if tp_mode == "tp2_full" and tp2 > 0.0:
        return tp2, "tp2_full"
    if tp1 > 0.0:
        return tp1, "tp1_only"
    if tp2 > 0.0:
        return tp2, "tp2_full"
    return 0.0, "unresolved"


@dataclass(slots=True)
class LangGraphSupervisorOrchestrator:
    """Small orchestration wrapper for using the LangGraph graph inside Phase 4."""

    checkpointer_path: str | Path = settings.TRADE_ORACLE_LANGGRAPH_CHECKPOINTER_PATH
    enable_live_llm: bool = False
    auto_approve: bool = False
    mcp_service_base_url: str | None = None
    mcp_http_client: Any | None = None
    audit_backend: str = settings.TRADE_ORACLE_AUDIT_BACKEND
    audit_db_path: str | Path = settings.TRADE_ORACLE_AUDIT_DB_PATH
    graph: Any = field(init=False, repr=False)
    command_cls: type[Any] = field(init=False, repr=False)
    audit_store: TradeOracleAuditStoreProtocol = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.graph = build_trade_oracle_graph(
            checkpointer_path=self.checkpointer_path,
            enable_live_llm=self.enable_live_llm,
            mcp_service_base_url=self.mcp_service_base_url,
            mcp_http_client=self.mcp_http_client,
        )
        self.command_cls = self._resolve_command_class()
        self.audit_store = build_trade_oracle_audit_store(
            self.audit_db_path,
            backend=self.audit_backend,
        )

    @staticmethod
    def _resolve_command_class() -> type[Any]:
        try:
            from langgraph.types import Command
        except ImportError as exc:  # pragma: no cover - depends on optional runtime env
            raise ImportError(
                "LangGraph runtime is required to use LangGraphSupervisorOrchestrator."
            ) from exc
        return Command

    @staticmethod
    def _account_state_context(
        *,
        current_balance: float,
        highest_equity: float,
        active_trades_count: int,
    ) -> AccountStateContext:
        return AccountStateContext(
            current_balance=current_balance,
            highest_equity=highest_equity,
            active_trades_count=active_trades_count,
            source="phase4_live_loop",
        )

    def _thread_config(self, *, thread_id: str) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": thread_id},
            "max_concurrency": 3,
        }

    def _raw_setup_with_account_state(
        self,
        scanner_row: dict[str, Any],
        *,
        current_balance: float,
        highest_equity: float,
        active_trades_count: int,
    ) -> dict[str, Any]:
        raw_setup = phase2_scanner_setup_to_raw_setup(
            scanner_row,
            account_state=self._account_state_context(
                current_balance=current_balance,
                highest_equity=highest_equity,
                active_trades_count=active_trades_count,
            ),
        )
        raw_setup["scanner_metadata"]["account_hydration_source"] = "phase4_live_loop"
        return raw_setup

    @staticmethod
    def _extract_review_context(first_result: dict[str, Any]) -> dict[str, Any]:
        interrupts = list(first_result.get("__interrupt__", []))
        if not interrupts:
            return {}

        payload = getattr(interrupts[0], "value", interrupts[0])
        if isinstance(payload, dict):
            return dict(payload)
        return {"value": payload}

    def _resume_if_needed(
        self,
        first_result: dict[str, Any],
        *,
        config: dict[str, Any],
        human_decision: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(first_result, dict) or not first_result.get("__interrupt__"):
            return first_result
        if human_decision is None and not self.auto_approve:
            return None
        decision = human_decision or {
            "action": "APPROVE",
            "reviewer": "langgraph_supervisor_orchestrator",
            "notes": "Auto-approved by Phase 4 LangGraph bridge.",
        }
        return self.graph.invoke(self.command_cls(resume=decision), config=config)

    @staticmethod
    def _candidate_from_result(
        *,
        raw_setup: dict[str, Any],
        thread_id: str,
        result: dict[str, Any] | None,
        interrupted: bool,
    ) -> LangGraphExecutionCandidate | None:
        if not result:
            return None

        final_decision = dict(result.get("final_decision", {}))
        if not final_decision:
            return None

        decision = str(final_decision.get("decision", "PASS")).upper()
        if decision not in {"BUY", "SELL"}:
            return None
        execution_status = str(final_decision.get("execution_status", "pass"))
        position_sizing = dict(final_decision.get("position_sizing", {}))
        execute_trade = decision in {"BUY", "SELL"} and execution_status == "approved"
        take_profit, execution_tp_mode = resolve_live_take_profit(position_sizing)

        return LangGraphExecutionCandidate(
            execute_trade=execute_trade,
            symbol=str(final_decision.get("asset_ticker", raw_setup.get("asset_ticker", ""))),
            direction="BUY" if decision == "BUY" else "SELL",
            entry_price=float(position_sizing.get("entry_price", raw_setup.get("current_price", 0.0))),
            stop_loss=float(position_sizing.get("stop_loss", 0.0)),
            take_profit=take_profit,
            size_tokens=float(position_sizing.get("tokens", 0.0)),
            confidence=float(final_decision.get("confidence", 0.0)),
            execution_status=execution_status,
            execution_tp_mode=execution_tp_mode,
            review_required=bool(result.get("review_required", interrupted and not execute_trade)),
            rationale=str(final_decision.get("entry_context", "")),
            position_sizing=position_sizing,
            final_decision=final_decision,
            raw_setup=raw_setup,
            thread_id=thread_id,
        )

    @classmethod
    def _resolved_state_lists(
        cls,
        *,
        resolved_result: dict[str, Any] | None,
        review_context: dict[str, Any],
        key: str,
    ) -> list[dict[str, Any]] | list[str]:
        if resolved_result and isinstance(resolved_result.get(key), list):
            return list(resolved_result.get(key, []))
        audit_snapshot = review_context.get("audit_snapshot", {})
        if isinstance(audit_snapshot, dict) and isinstance(audit_snapshot.get(key), list):
            return list(audit_snapshot.get(key, []))
        return []

    @classmethod
    def _resolved_state_dict(
        cls,
        *,
        resolved_result: dict[str, Any] | None,
        review_context: dict[str, Any],
        key: str,
    ) -> dict[str, Any]:
        if resolved_result and isinstance(resolved_result.get(key), dict):
            return dict(resolved_result.get(key, {}))
        audit_snapshot = review_context.get("audit_snapshot", {})
        if isinstance(audit_snapshot, dict) and isinstance(audit_snapshot.get(key), dict):
            return dict(audit_snapshot.get(key, {}))
        return {}

    @classmethod
    def _evaluation_result_from_graph(
        cls,
        *,
        raw_setup: dict[str, Any],
        thread_id: str,
        first_result: dict[str, Any],
        final_result: dict[str, Any] | None,
    ) -> LangGraphEvaluationResult:
        interrupted = bool(isinstance(first_result, dict) and first_result.get("__interrupt__"))
        review_context = cls._extract_review_context(first_result) if interrupted else {}
        resolved_result = final_result if final_result is not None else (None if interrupted else first_result)
        final_decision = dict((resolved_result or {}).get("final_decision", {}))
        audit_trail = [str(item) for item in cls._resolved_state_lists(resolved_result=resolved_result, review_context=review_context, key="audit_trail")]
        tool_results = [
            dict(item)
            for item in cls._resolved_state_lists(resolved_result=resolved_result, review_context=review_context, key="tool_results")
            if isinstance(item, dict)
        ]
        specialist_reports = [
            dict(item)
            for item in cls._resolved_state_lists(resolved_result=resolved_result, review_context=review_context, key="specialist_reports")
            if isinstance(item, dict)
        ]
        errors = [
            dict(item)
            for item in cls._resolved_state_lists(resolved_result=resolved_result, review_context=review_context, key="errors")
            if isinstance(item, dict)
        ]
        thread_metadata = cls._resolved_state_dict(
            resolved_result=resolved_result,
            review_context=review_context,
            key="thread_metadata",
        )
        candidate = cls._candidate_from_result(
            raw_setup=raw_setup,
            thread_id=thread_id,
            result=resolved_result,
            interrupted=interrupted,
        )

        if interrupted and final_result is None:
            status: Literal["pending_review", "completed", "no_trade"] = "pending_review"
        elif final_decision.get("decision") in {"BUY", "SELL"}:
            status = "completed"
        else:
            status = "no_trade"

        return LangGraphEvaluationResult(
            status=status,
            thread_id=thread_id,
            interrupted=interrupted,
            review_required=bool(
                interrupted and final_result is None or (resolved_result or {}).get("review_required", False)
            ),
            raw_setup=raw_setup,
            review_context=review_context,
            final_decision=final_decision,
            gatekeeper_status=str((resolved_result or {}).get("gatekeeper_status", "")),
            audit_trail=audit_trail,
            tool_results=tool_results,
            specialist_reports=specialist_reports,
            errors=errors,
            thread_metadata=thread_metadata,
            candidate=candidate,
        )

    def _record_audit_event(
        self,
        *,
        event_type: str,
        source: str,
        run_id: str,
        thread_id: str,
        status: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            self.audit_store.record_event(
                event_type=event_type,
                source=source,
                run_id=run_id,
                thread_id=thread_id,
                status=status,
                payload=payload,
            )
        except Exception:
            return

    async def evaluate_setup(
        self,
        scanner_row: dict[str, Any],
        *,
        current_balance: float,
        highest_equity: float,
        active_trades_count: int,
        human_decision: dict[str, Any] | None = None,
        thread_id: str | None = None,
        run_id: str = "",
        event_source: str = "langgraph_orchestrator",
    ) -> LangGraphEvaluationResult:
        """Evaluate one scanner setup and optionally resume through human review."""
        raw_setup = self._raw_setup_with_account_state(
            scanner_row,
            current_balance=current_balance,
            highest_equity=highest_equity,
            active_trades_count=active_trades_count,
        )
        resolved_thread_id = thread_id or f"trade-oracle-phase4-{uuid4().hex}"
        config = self._thread_config(thread_id=resolved_thread_id)
        first_result = self.graph.invoke(build_initial_state(raw_setup), config=config)
        final_result = self._resume_if_needed(first_result, config=config, human_decision=human_decision)
        evaluation = self._evaluation_result_from_graph(
            raw_setup=raw_setup,
            thread_id=resolved_thread_id,
            first_result=first_result,
            final_result=final_result,
        )
        self._record_audit_event(
            event_type="evaluate_setup",
            source=event_source,
            run_id=run_id,
            thread_id=evaluation.thread_id,
            status=evaluation.status,
            payload=evaluation.model_dump(),
        )
        return evaluation

    async def resume_review(
        self,
        *,
        thread_id: str,
        human_decision: dict[str, Any],
        run_id: str = "",
        event_source: str = "langgraph_orchestrator",
    ) -> LangGraphEvaluationResult:
        """Resume one interrupted LangGraph thread from a prior human review pause."""
        config = self._thread_config(thread_id=thread_id)
        final_result = self.graph.invoke(self.command_cls(resume=human_decision), config=config)
        raw_setup = dict(final_result.get("raw_setup", {}))
        evaluation = LangGraphEvaluationResult(
            status="completed" if final_result.get("final_decision", {}).get("decision") in {"BUY", "SELL"} else "no_trade",
            thread_id=thread_id,
            interrupted=True,
            review_required=bool(final_result.get("review_required", False)),
            raw_setup=raw_setup,
            review_context=dict(final_result.get("review_context", {})),
            final_decision=dict(final_result.get("final_decision", {})),
            gatekeeper_status=str(final_result.get("gatekeeper_status", "")),
            audit_trail=[str(item) for item in final_result.get("audit_trail", [])],
            tool_results=[dict(item) for item in final_result.get("tool_results", []) if isinstance(item, dict)],
            specialist_reports=[dict(item) for item in final_result.get("specialist_reports", []) if isinstance(item, dict)],
            errors=[dict(item) for item in final_result.get("errors", []) if isinstance(item, dict)],
            thread_metadata=dict(final_result.get("thread_metadata", {})),
            candidate=self._candidate_from_result(
                raw_setup=raw_setup,
                thread_id=thread_id,
                result=final_result,
                interrupted=True,
            ),
        )
        self._record_audit_event(
            event_type="resume_review",
            source=event_source,
            run_id=run_id,
            thread_id=thread_id,
            status=evaluation.status,
            payload=evaluation.model_dump(),
        )
        return evaluation

    async def evaluate_batch(
        self,
        scanner_rows: list[dict[str, Any]],
        *,
        current_balance: float,
        highest_equity: float,
        active_trades_count: int,
        human_decision: dict[str, Any] | None = None,
        run_id: str = "",
        event_source: str = "langgraph_orchestrator",
    ) -> list[LangGraphEvaluationResult]:
        """Evaluate a batch of scanner rows and preserve pending-review thread state."""
        evaluations: list[LangGraphEvaluationResult] = []

        for scanner_row in scanner_rows:
            evaluation = await self.evaluate_setup(
                scanner_row,
                current_balance=current_balance,
                highest_equity=highest_equity,
                active_trades_count=active_trades_count,
                human_decision=human_decision,
                run_id=run_id,
                event_source=event_source,
            )
            evaluations.append(evaluation)

        self._record_audit_event(
            event_type="evaluate_batch",
            source=event_source,
            run_id=run_id,
            thread_id="",
            status="completed",
            payload={
                "evaluation_count": len(evaluations),
                "status_counts": {
                    "pending_review": sum(1 for item in evaluations if item.status == "pending_review"),
                    "completed": sum(1 for item in evaluations if item.status == "completed"),
                    "no_trade": sum(1 for item in evaluations if item.status == "no_trade"),
                },
                "thread_ids": [item.thread_id for item in evaluations],
            },
        )
        return evaluations

    async def evaluate_and_rank(
        self,
        scanner_rows: list[dict[str, Any]],
        *,
        current_balance: float,
        highest_equity: float,
        active_trades_count: int,
        human_decision: dict[str, Any] | None = None,
        run_id: str = "",
        event_source: str = "langgraph_orchestrator",
    ) -> list[LangGraphExecutionCandidate]:
        """Evaluate Phase 2 setups through the LangGraph supervisor and rank the results."""
        evaluations = await self.evaluate_batch(
            scanner_rows,
            current_balance=current_balance,
            highest_equity=highest_equity,
            active_trades_count=active_trades_count,
            human_decision=human_decision,
            run_id=run_id,
            event_source=event_source,
        )
        candidates = [evaluation.candidate for evaluation in evaluations if evaluation.candidate is not None]
        ranked = sorted(
            candidates,
            key=lambda candidate: (
                int(candidate.execute_trade),
                candidate.confidence,
                float(candidate.position_sizing.get("usd_value", 0.0)),
                candidate.symbol,
            ),
            reverse=True,
        )
        self._record_audit_event(
            event_type="evaluate_and_rank",
            source=event_source,
            run_id=run_id,
            thread_id="",
            status="completed",
            payload={
                "candidate_count": len(ranked),
                "candidates": [candidate.model_dump() for candidate in ranked],
            },
        )
        return ranked


__all__ = [
    "LangGraphExecutionCandidate",
    "LangGraphEvaluationResult",
    "LangGraphSupervisorOrchestrator",
]
