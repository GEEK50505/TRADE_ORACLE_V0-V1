"""
FastAPI webhook service for the TRADE_ORACLE LangGraph supervisor.

This gives n8n a clean HTTP boundary for:
1. submitting scanner setups to the LangGraph brain,
2. receiving pending human-review interrupts, and
3. resuming the same thread after an APPROVE / HALT_SYSTEM decision.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ai.langgraph_orchestrator import (
    LangGraphExecutionCandidate,
    LangGraphSupervisorOrchestrator,
)
from ai.trade_oracle_langgraph_phase1 import HumanReviewDecision, Phase2ScannerSetup
from config import settings

from .trade_oracle_mcp_service import _authorization_dependency, _error_response, _response_meta


class BrainAccountState(BaseModel):
    """Live account context supplied by the outer scheduler or broker sync layer."""

    model_config = ConfigDict(extra="forbid")

    current_balance: float
    highest_equity: float
    active_trades_count: int = 0


class BrainEvaluateSetupRequest(BaseModel):
    """One scanner setup routed through the LangGraph supervisor."""

    model_config = ConfigDict(extra="forbid")

    scanner_setup: Phase2ScannerSetup
    account_state: BrainAccountState
    auto_approve: bool = False
    enable_live_llm: bool = False
    run_id: str = ""
    thread_id: str | None = None
    human_decision: HumanReviewDecision | None = None


class BrainEvaluateBatchRequest(BaseModel):
    """Batch scanner payload for ranked execution-candidate generation."""

    model_config = ConfigDict(extra="forbid")

    scanner_setups: list[Phase2ScannerSetup]
    account_state: BrainAccountState
    auto_approve: bool = False
    enable_live_llm: bool = False
    run_id: str = ""


class BrainResumeReviewRequest(BaseModel):
    """Resume one interrupted LangGraph thread after human review in n8n/OpenClaw."""

    model_config = ConfigDict(extra="forbid")

    thread_id: str
    human_decision: HumanReviewDecision
    enable_live_llm: bool = False
    run_id: str = ""


class BrainServiceResponse(BaseModel):
    """Uniform envelope returned by the LangGraph brain service."""

    model_config = ConfigDict(extra="forbid")

    operation: str
    status: str
    detail: str
    result: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


def _brain_response(
    *,
    operation: str,
    detail: str,
    result: dict[str, Any],
    request: Request | None = None,
) -> BrainServiceResponse:
    return BrainServiceResponse(
        operation=operation,
        status="ok",
        detail=detail,
        result=result,
        meta={
            **_response_meta(request=request, tool_name=operation),
            "service": "trade_oracle_brain",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )


def build_trade_oracle_brain_app(
    *,
    require_auth: bool = settings.TRADE_ORACLE_BRAIN_REQUIRE_AUTH,
    api_key: str | None = settings.TRADE_ORACLE_BRAIN_API_KEY,
    checkpointer_path: str | Path = settings.TRADE_ORACLE_LANGGRAPH_CHECKPOINTER_PATH,
    audit_backend: str = settings.TRADE_ORACLE_AUDIT_BACKEND,
    audit_db_path: str | Path = settings.TRADE_ORACLE_AUDIT_DB_PATH,
    mcp_service_base_url: str | None = None,
) -> FastAPI:
    """Create the n8n-facing FastAPI wrapper for the LangGraph supervisor."""

    authorize_request = _authorization_dependency(
        require_auth=require_auth,
        expected_api_key=api_key,
    )
    resolved_checkpointer_path = str(checkpointer_path)
    resolved_audit_db_path = str(audit_db_path)
    orchestrator_cache: dict[tuple[bool, bool], LangGraphSupervisorOrchestrator] = {}

    def resolve_orchestrator(*, auto_approve: bool, enable_live_llm: bool) -> LangGraphSupervisorOrchestrator:
        cache_key = (auto_approve, enable_live_llm)
        if cache_key not in orchestrator_cache:
            orchestrator_cache[cache_key] = LangGraphSupervisorOrchestrator(
                checkpointer_path=resolved_checkpointer_path,
                audit_backend=audit_backend,
                audit_db_path=resolved_audit_db_path,
                auto_approve=auto_approve,
                enable_live_llm=enable_live_llm,
                mcp_service_base_url=mcp_service_base_url,
            )
        return orchestrator_cache[cache_key]

    app = FastAPI(
        title="TRADE_ORACLE LangGraph Brain Service",
        version="0.1.0",
        description=(
            "n8n-facing webhook layer for the TRADE_ORACLE LangGraph supervisor. "
            "Supports single-setup evaluation, batch ranking, and human-review resume."
        ),
    )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        body = _error_response(
            tool_name="brain_validation_error",
            detail="Invalid LangGraph brain request payload.",
            payload={},
            code="validation_error",
            request=request,
            status_code=422,
            error={"issues": exc.errors()},
        )
        return JSONResponse(status_code=422, content=body.model_dump())

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        body = _error_response(
            tool_name="brain_internal_error",
            detail="Unhandled exception in the LangGraph brain service.",
            payload={},
            code="internal_error",
            request=request,
            status_code=500,
            error={"type": type(exc).__name__, "message": str(exc)},
        )
        return JSONResponse(status_code=500, content=body.model_dump())

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/brain/evaluate-setup", response_model=BrainServiceResponse)
    async def evaluate_setup(
        payload: BrainEvaluateSetupRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> BrainServiceResponse:
        orchestrator = resolve_orchestrator(
            auto_approve=payload.auto_approve,
            enable_live_llm=payload.enable_live_llm,
        )
        outcome = await orchestrator.evaluate_setup(
            payload.scanner_setup.model_dump(),
            current_balance=payload.account_state.current_balance,
            highest_equity=payload.account_state.highest_equity,
            active_trades_count=payload.account_state.active_trades_count,
            human_decision=payload.human_decision.model_dump() if payload.human_decision is not None else None,
            thread_id=payload.thread_id,
            run_id=payload.run_id or http_request.headers.get("X-Request-ID", ""),
            event_source="brain_service",
        )
        return _brain_response(
            operation="evaluate_setup",
            detail="LangGraph supervisor evaluated one scanner setup.",
            result=outcome.model_dump(),
            request=http_request,
        )

    @app.post("/brain/evaluate-batch", response_model=BrainServiceResponse)
    async def evaluate_batch(
        payload: BrainEvaluateBatchRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> BrainServiceResponse:
        orchestrator = resolve_orchestrator(
            auto_approve=payload.auto_approve,
            enable_live_llm=payload.enable_live_llm,
        )
        evaluations = await orchestrator.evaluate_batch(
            [row.model_dump() for row in payload.scanner_setups],
            current_balance=payload.account_state.current_balance,
            highest_equity=payload.account_state.highest_equity,
            active_trades_count=payload.account_state.active_trades_count,
            run_id=payload.run_id or http_request.headers.get("X-Request-ID", ""),
            event_source="brain_service",
        )
        candidates = [
            evaluation.candidate
            for evaluation in evaluations
            if evaluation.candidate is not None
        ]
        ranked_candidates = sorted(
            candidates,
            key=lambda candidate: (
                int(candidate.execute_trade),
                candidate.confidence,
                float(candidate.position_sizing.get("usd_value", 0.0)),
                candidate.symbol,
            ),
            reverse=True,
        )
        return _brain_response(
            operation="evaluate_batch",
            detail="LangGraph supervisor ranked the submitted scanner setups.",
            result={
                "evaluation_count": len(evaluations),
                "evaluations": [evaluation.model_dump() for evaluation in evaluations],
                "candidate_count": len(ranked_candidates),
                "candidates": [candidate.model_dump() for candidate in ranked_candidates],
            },
            request=http_request,
        )

    @app.post("/brain/resume-review", response_model=BrainServiceResponse)
    async def resume_review(
        payload: BrainResumeReviewRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> BrainServiceResponse:
        orchestrator = resolve_orchestrator(
            auto_approve=False,
            enable_live_llm=payload.enable_live_llm,
        )
        outcome = await orchestrator.resume_review(
            thread_id=payload.thread_id,
            human_decision=payload.human_decision.model_dump(),
            run_id=payload.run_id or http_request.headers.get("X-Request-ID", ""),
            event_source="brain_service",
        )
        return _brain_response(
            operation="resume_review",
            detail="LangGraph supervisor resumed a pending human-review thread.",
            result=outcome.model_dump(),
            request=http_request,
        )

    return app


app = build_trade_oracle_brain_app()


__all__ = [
    "BrainAccountState",
    "BrainEvaluateSetupRequest",
    "BrainEvaluateBatchRequest",
    "BrainResumeReviewRequest",
    "BrainServiceResponse",
    "LangGraphExecutionCandidate",
    "build_trade_oracle_brain_app",
    "app",
]
