"""
Unified FastAPI entrypoint for the TRADE_ORACLE LangGraph Super Brain.

This service gives n8n a single webhook boundary that can:
1. optionally run the Phase 2 scanner,
2. evaluate one or many setups through the LangGraph supervisor,
3. return pending review interrupts, and
4. resume the same thread after human approval.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ai.langgraph_orchestrator import LangGraphSupervisorOrchestrator
from ai.trade_oracle_langgraph_phase1 import HumanReviewDecision, Phase2ScannerSetup, fetch_phase2_scanner_setups
from config import settings

from .trade_oracle_mcp_service import _authorization_dependency, _error_response, _response_meta


class SuperBrainAccountState(BaseModel):
    """Live account context passed in by n8n or another outer scheduler."""

    model_config = ConfigDict(extra="forbid")

    current_balance: float
    highest_equity: float
    active_trades_count: int = 0


class SuperBrainRunRequest(BaseModel):
    """Run the full LangGraph brain on supplied setups or a live scanner watchlist."""

    model_config = ConfigDict(extra="forbid")

    scanner_setups: list[Phase2ScannerSetup] = Field(default_factory=list)
    watchlist: list[str] = Field(default_factory=lambda: list(settings.WATCHLIST))
    scanner_limit: int | None = None
    account_state: SuperBrainAccountState
    auto_approve: bool = False
    enable_live_llm: bool = False
    run_id: str = ""


class SuperBrainResumeRequest(BaseModel):
    """Resume one interrupted super-brain thread."""

    model_config = ConfigDict(extra="forbid")

    thread_id: str
    human_decision: HumanReviewDecision
    enable_live_llm: bool = False
    run_id: str = ""


class SuperBrainResponse(BaseModel):
    """Uniform envelope for super-brain REST responses."""

    model_config = ConfigDict(extra="forbid")

    operation: str
    status: str
    detail: str
    result: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


def _super_brain_response(
    *,
    operation: str,
    detail: str,
    result: dict[str, Any],
    request: Request | None = None,
) -> SuperBrainResponse:
    return SuperBrainResponse(
        operation=operation,
        status="ok",
        detail=detail,
        result=result,
        meta={
            **_response_meta(request=request, tool_name=operation),
            "service": "trade_oracle_super_brain",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )


async def _default_scanner_runner(
    *,
    watchlist: list[str],
    scanner_limit: int | None,
) -> list[dict[str, Any]]:
    rows = await fetch_phase2_scanner_setups(watchlist=watchlist)
    if scanner_limit is not None:
        return rows[: max(0, int(scanner_limit))]
    return rows


def build_trade_oracle_super_brain_app(
    *,
    require_auth: bool = settings.TRADE_ORACLE_BRAIN_REQUIRE_AUTH,
    api_key: str | None = settings.TRADE_ORACLE_BRAIN_API_KEY,
    checkpointer_path: str | Path = settings.TRADE_ORACLE_LANGGRAPH_CHECKPOINTER_PATH,
    audit_db_path: str | Path = settings.TRADE_ORACLE_AUDIT_DB_PATH,
    mcp_service_base_url: str | None = None,
    scanner_runner: Callable[..., Awaitable[list[dict[str, Any]]]] | None = None,
) -> FastAPI:
    """Create the single-service LangGraph Super Brain API."""

    authorize_request = _authorization_dependency(
        require_auth=require_auth,
        expected_api_key=api_key,
    )
    resolved_checkpointer_path = str(checkpointer_path)
    resolved_audit_db_path = str(audit_db_path)
    resolved_scanner_runner = scanner_runner or _default_scanner_runner
    orchestrator_cache: dict[tuple[bool, bool], LangGraphSupervisorOrchestrator] = {}

    def resolve_orchestrator(*, auto_approve: bool, enable_live_llm: bool) -> LangGraphSupervisorOrchestrator:
        cache_key = (auto_approve, enable_live_llm)
        if cache_key not in orchestrator_cache:
            orchestrator_cache[cache_key] = LangGraphSupervisorOrchestrator(
                checkpointer_path=resolved_checkpointer_path,
                audit_db_path=resolved_audit_db_path,
                auto_approve=auto_approve,
                enable_live_llm=enable_live_llm,
                mcp_service_base_url=mcp_service_base_url,
            )
        return orchestrator_cache[cache_key]

    app = FastAPI(
        title="TRADE_ORACLE LangGraph Super Brain",
        version="0.1.0",
        description=(
            "Unified LangGraph-first service for scanning, evaluating, human review, and thread resume."
        ),
    )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        body = _error_response(
            tool_name="super_brain_validation_error",
            detail="Invalid TRADE_ORACLE Super Brain request payload.",
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
            tool_name="super_brain_internal_error",
            detail="Unhandled exception in the TRADE_ORACLE Super Brain service.",
            payload={},
            code="internal_error",
            request=request,
            status_code=500,
            error={"type": type(exc).__name__, "message": str(exc)},
        )
        return JSONResponse(status_code=500, content=body.model_dump())

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "trade_oracle_super_brain",
            "checkpointer_path": resolved_checkpointer_path,
        }

    @app.post("/superbrain/run-once", response_model=SuperBrainResponse)
    async def run_once(
        payload: SuperBrainRunRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> SuperBrainResponse:
        scanner_rows = [row.model_dump() for row in payload.scanner_setups]
        scanner_source = "request_payload"
        if not scanner_rows:
            scanner_rows = await resolved_scanner_runner(
                watchlist=list(payload.watchlist),
                scanner_limit=payload.scanner_limit,
            )
            scanner_source = "phase2_scanner"

        orchestrator = resolve_orchestrator(
            auto_approve=payload.auto_approve,
            enable_live_llm=payload.enable_live_llm,
        )
        evaluations = await orchestrator.evaluate_batch(
            scanner_rows,
            current_balance=payload.account_state.current_balance,
            highest_equity=payload.account_state.highest_equity,
            active_trades_count=payload.account_state.active_trades_count,
            run_id=payload.run_id or http_request.headers.get("X-Request-ID", ""),
            event_source="super_brain_service",
        )
        candidates = [evaluation.candidate for evaluation in evaluations if evaluation.candidate is not None]
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
        return _super_brain_response(
            operation="run_once",
            detail="TRADE_ORACLE Super Brain completed a scan-and-evaluate cycle.",
            result={
                "run_id": payload.run_id or http_request.headers.get("X-Request-ID", ""),
                "scanner_source": scanner_source,
                "scanner_row_count": len(scanner_rows),
                "evaluation_count": len(evaluations),
                "evaluations": [evaluation.model_dump() for evaluation in evaluations],
                "candidate_count": len(ranked_candidates),
                "candidates": [candidate.model_dump() for candidate in ranked_candidates],
            },
            request=http_request,
        )

    @app.post("/superbrain/review-resume", response_model=SuperBrainResponse)
    async def review_resume(
        payload: SuperBrainResumeRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> SuperBrainResponse:
        orchestrator = resolve_orchestrator(
            auto_approve=False,
            enable_live_llm=payload.enable_live_llm,
        )
        evaluation = await orchestrator.resume_review(
            thread_id=payload.thread_id,
            human_decision=payload.human_decision.model_dump(),
            run_id=payload.run_id or http_request.headers.get("X-Request-ID", ""),
            event_source="super_brain_service",
        )
        return _super_brain_response(
            operation="review_resume",
            detail="TRADE_ORACLE Super Brain resumed a human-review thread.",
            result=evaluation.model_dump(),
            request=http_request,
        )

    return app


app = build_trade_oracle_super_brain_app()


__all__ = [
    "SuperBrainAccountState",
    "SuperBrainRunRequest",
    "SuperBrainResumeRequest",
    "SuperBrainResponse",
    "build_trade_oracle_super_brain_app",
    "app",
]
