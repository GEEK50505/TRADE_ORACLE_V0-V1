"""
Deployable platform entrypoint for the TRADE_ORACLE LangGraph stack.

This app keeps the unified Super Brain routes at the top level for n8n while
mounting the legacy-compatible brain, ops, and MCP services under one shared
container boundary for Railway/Render-style hosting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, Query
from pydantic import BaseModel, ConfigDict, Field

from ai.trade_oracle_storage import (
    TradeOracleAuditStoreProtocol,
    TradeOracleBenchmarkStoreProtocol,
    build_trade_oracle_audit_store,
    build_trade_oracle_benchmark_store,
)
from config import settings

from .trade_oracle_brain_service import build_trade_oracle_brain_app
from .trade_oracle_mcp_service import build_trade_oracle_mcp_app
from .trade_oracle_ops_service import LiveScannerRequest, build_trade_oracle_ops_app
from .trade_oracle_super_brain_service import build_trade_oracle_super_brain_app


class PlatformHealthResponse(BaseModel):
    """Platform-level deployment health payload."""

    model_config = ConfigDict(extra="forbid")

    status: str
    service: str
    deployment_mode: str
    primary_entrypoint: str
    mounted_services: dict[str, str] = Field(default_factory=dict)
    checkpointer_path: str
    mcp_mode: str


class PlatformCapabilitiesResponse(BaseModel):
    """n8n-facing capabilities inventory for the unified platform service."""

    model_config = ConfigDict(extra="forbid")

    service: str
    description: str
    n8n_entrypoints: dict[str, str] = Field(default_factory=dict)
    mounted_services: dict[str, dict[str, Any]] = Field(default_factory=dict)
    auth: dict[str, Any] = Field(default_factory=dict)
    deployment: dict[str, Any] = Field(default_factory=dict)


class PlatformAuditResponse(BaseModel):
    """Platform audit/event lookup response."""

    model_config = ConfigDict(extra="forbid")

    service: str
    count: int
    events: list[dict[str, Any]] = Field(default_factory=list)


class PlatformBenchmarkResponse(BaseModel):
    """Platform benchmark/event lookup response."""

    model_config = ConfigDict(extra="forbid")

    service: str
    count: int
    events: list[dict[str, Any]] = Field(default_factory=list)


class PlatformBenchmarkSummaryResponse(BaseModel):
    """Platform benchmark summary response."""

    model_config = ConfigDict(extra="forbid")

    service: str
    summary: dict[str, Any] = Field(default_factory=dict)


class PlatformBenchmarkCycleResponse(BaseModel):
    """Platform benchmark recent-cycle summary response."""

    model_config = ConfigDict(extra="forbid")

    service: str
    count: int
    cycles: list[dict[str, Any]] = Field(default_factory=list)


def build_trade_oracle_platform_app(
    *,
    require_auth: bool | None = None,
    api_key: str | None = None,
    checkpointer_path: str | Path = settings.TRADE_ORACLE_LANGGRAPH_CHECKPOINTER_PATH,
    mcp_service_base_url: str | None = None,
    audit_backend: str = settings.TRADE_ORACLE_AUDIT_BACKEND,
    audit_db_path: str | Path = settings.TRADE_ORACLE_AUDIT_DB_PATH,
    benchmark_backend: str = settings.TRADE_ORACLE_BENCHMARK_BACKEND,
    benchmark_db_path: str | Path = settings.TRADE_ORACLE_BENCHMARK_DB_PATH,
    scanner_runner: Callable[..., Awaitable[list[dict[str, Any]]]] | None = None,
    phase2_scanner_runner: Callable[[list[str]], Awaitable[list[dict[str, Any]]]] | None = None,
    live_scanner_runner: Callable[[LiveScannerRequest], Awaitable[dict[str, Any]]] | None = None,
    match_trader_api_cls: type[Any] | None = None,
    mt5_bridge_cls: type[Any] | None = None,
) -> FastAPI:
    """Create the single FastAPI deployment surface for the LangGraph stack."""

    resolved_api_key = api_key if api_key is not None else settings.TRADE_ORACLE_PLATFORM_API_KEY
    resolved_require_auth = (
        require_auth
        if require_auth is not None
        else (settings.TRADE_ORACLE_PLATFORM_REQUIRE_AUTH or bool(resolved_api_key))
    )
    resolved_checkpointer_path = str(checkpointer_path)
    resolved_audit_db_path = str(audit_db_path)
    resolved_benchmark_db_path = str(benchmark_db_path)
    audit_store: TradeOracleAuditStoreProtocol = build_trade_oracle_audit_store(
        resolved_audit_db_path,
        backend=audit_backend,
    )
    benchmark_store: TradeOracleBenchmarkStoreProtocol = build_trade_oracle_benchmark_store(
        resolved_benchmark_db_path,
        backend=benchmark_backend,
    )

    app = build_trade_oracle_super_brain_app(
        require_auth=resolved_require_auth,
        api_key=resolved_api_key,
        checkpointer_path=resolved_checkpointer_path,
        audit_backend=audit_backend,
        audit_db_path=resolved_audit_db_path,
        benchmark_backend=benchmark_backend,
        benchmark_db_path=resolved_benchmark_db_path,
        mcp_service_base_url=mcp_service_base_url,
        scanner_runner=scanner_runner,
    )
    app.title = "TRADE_ORACLE Platform Service"
    app.description = (
        "Single-container deployment surface for the TRADE_ORACLE LangGraph Super Brain, "
        "operational HTTP tools, and MCP specialist adapters."
    )

    auxiliary_brain_app = build_trade_oracle_brain_app(
        require_auth=resolved_require_auth,
        api_key=resolved_api_key,
        checkpointer_path=resolved_checkpointer_path,
        audit_backend=audit_backend,
        audit_db_path=resolved_audit_db_path,
        mcp_service_base_url=mcp_service_base_url,
    )
    auxiliary_ops_app = build_trade_oracle_ops_app(
        require_auth=resolved_require_auth,
        api_key=resolved_api_key,
        phase2_scanner_runner=phase2_scanner_runner,
        live_scanner_runner=live_scanner_runner,
        match_trader_api_cls=match_trader_api_cls,
        mt5_bridge_cls=mt5_bridge_cls,
        benchmark_backend=benchmark_backend,
        benchmark_db_path=resolved_benchmark_db_path,
    )
    auxiliary_mcp_app = build_trade_oracle_mcp_app(
        require_auth=resolved_require_auth,
        api_key=resolved_api_key,
    )

    app.mount("/services/brain", auxiliary_brain_app)
    app.mount("/services/ops", auxiliary_ops_app)
    app.mount("/services/mcp", auxiliary_mcp_app)

    @app.get("/system/health", response_model=PlatformHealthResponse)
    def system_health() -> PlatformHealthResponse:
        return PlatformHealthResponse(
            status="ok",
            service="trade_oracle_platform",
            deployment_mode="single_container",
            primary_entrypoint="/superbrain/run-once",
            mounted_services={
                "brain": "/services/brain",
                "ops": "/services/ops",
                "mcp": "/services/mcp",
            },
            checkpointer_path=resolved_checkpointer_path,
            mcp_mode="external_http_service" if mcp_service_base_url else "local_tools",
        )

    @app.get("/system/audit/recent", response_model=PlatformAuditResponse)
    def system_audit_recent(
        limit: int = Query(default=20, ge=1, le=200),
        event_type: str = Query(default=""),
        status: str = Query(default=""),
    ) -> PlatformAuditResponse:
        events = audit_store.list_recent_events(limit=limit, event_type=event_type, status=status)
        return PlatformAuditResponse(
            service="trade_oracle_platform",
            count=len(events),
            events=[event.model_dump() for event in events],
        )

    @app.get("/system/audit/thread/{thread_id}", response_model=PlatformAuditResponse)
    def system_audit_thread(thread_id: str, limit: int = Query(default=100, ge=1, le=500)) -> PlatformAuditResponse:
        events = audit_store.list_thread_events(thread_id=thread_id, limit=limit)
        return PlatformAuditResponse(
            service="trade_oracle_platform",
            count=len(events),
            events=[event.model_dump() for event in events],
        )

    @app.get("/system/benchmark/recent", response_model=PlatformBenchmarkResponse)
    def system_benchmark_recent(
        limit: int = Query(default=20, ge=1, le=200),
        event_type: str = Query(default=""),
        benchmark_variant: str = Query(default=""),
        cycle_id: str = Query(default=""),
        status: str = Query(default=""),
    ) -> PlatformBenchmarkResponse:
        events = benchmark_store.list_recent_events(
            limit=limit,
            event_type=event_type,
            benchmark_variant=benchmark_variant,
            cycle_id=cycle_id,
            status=status,
        )
        return PlatformBenchmarkResponse(
            service="trade_oracle_platform",
            count=len(events),
            events=[event.model_dump() for event in events],
        )

    @app.get("/system/benchmark/cycle/{cycle_id}", response_model=PlatformBenchmarkResponse)
    def system_benchmark_cycle(
        cycle_id: str,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> PlatformBenchmarkResponse:
        events = benchmark_store.list_cycle_events(cycle_id=cycle_id, limit=limit)
        return PlatformBenchmarkResponse(
            service="trade_oracle_platform",
            count=len(events),
            events=[event.model_dump() for event in events],
        )

    @app.get("/system/benchmark/cycles/recent", response_model=PlatformBenchmarkCycleResponse)
    def system_benchmark_cycles_recent(
        limit: int = Query(default=20, ge=1, le=100),
        benchmark_variant: str = Query(default=""),
        execution_backend: str = Query(default=""),
    ) -> PlatformBenchmarkCycleResponse:
        cycles = benchmark_store.list_recent_cycle_summaries(
            limit=limit,
            benchmark_variant=benchmark_variant,
            execution_backend=execution_backend,
        )
        return PlatformBenchmarkCycleResponse(
            service="trade_oracle_platform",
            count=len(cycles),
            cycles=cycles,
        )

    @app.get("/system/benchmark/summary", response_model=PlatformBenchmarkSummaryResponse)
    def system_benchmark_summary(
        benchmark_variant: str = Query(default=""),
        execution_backend: str = Query(default=""),
    ) -> PlatformBenchmarkSummaryResponse:
        summary = benchmark_store.build_summary(
            benchmark_variant=benchmark_variant,
            execution_backend=execution_backend,
        )
        return PlatformBenchmarkSummaryResponse(
            service="trade_oracle_platform",
            summary=summary,
        )

    @app.get("/system/capabilities", response_model=PlatformCapabilitiesResponse)
    def system_capabilities() -> PlatformCapabilitiesResponse:
        return PlatformCapabilitiesResponse(
            service="trade_oracle_platform",
            description=(
                "Single deployable LangGraph platform for n8n-triggered scan, review, "
                "resume, risk, execution, and specialist-tool workflows."
            ),
            n8n_entrypoints={
                "run_once": "/superbrain/run-once",
                "review_resume": "/superbrain/review-resume",
                "system_health": "/system/health",
                "system_capabilities": "/system/capabilities",
                "audit_recent": "/system/audit/recent",
                "audit_thread": "/system/audit/thread/{thread_id}",
                "benchmark_summary": "/system/benchmark/summary",
                "benchmark_recent": "/system/benchmark/recent",
                "benchmark_cycle": "/system/benchmark/cycle/{cycle_id}",
                "benchmark_cycles_recent": "/system/benchmark/cycles/recent",
            },
            mounted_services={
                "brain": {
                    "mount_path": "/services/brain",
                    "routes": {
                        "evaluate_setup": "/services/brain/brain/evaluate-setup",
                        "evaluate_batch": "/services/brain/brain/evaluate-batch",
                        "resume_review": "/services/brain/brain/resume-review",
                    },
                },
                "ops": {
                    "mount_path": "/services/ops",
                    "routes": {
                        "phase2_scanner": "/services/ops/ops/scanner/phase2/run",
                        "live_scanner": "/services/ops/ops/scanner/live/run",
                        "account_state": "/services/ops/ops/account/state",
                        "risk_evaluate": "/services/ops/ops/risk/evaluate",
                        "execution_symbol_status": "/services/ops/ops/execution/symbol-status",
                        "execution_platform_details": "/services/ops/ops/execution/platform-details",
                        "execution_transmit_limit_order": "/services/ops/ops/execution/transmit-limit-order",
                    },
                },
                "mcp": {
                    "mount_path": "/services/mcp",
                    "routes": {
                        "provider_status": "/services/mcp/mcp/providers/status",
                        "macro_snapshot": "/services/mcp/mcp/macro-snapshot",
                        "fundamental_snapshot": "/services/mcp/mcp/fundamental-snapshot",
                        "tokenomics_snapshot": "/services/mcp/mcp/tokenomics-snapshot",
                        "technical_snapshot": "/services/mcp/mcp/technical-snapshot",
                        "risk_guardrails": "/services/mcp/mcp/risk-guardrails",
                    },
                },
            },
            auth={
                "shared_platform_auth": resolved_require_auth,
                "auth_header": "X-Trade-Oracle-API-Key",
                "api_key_env": "TRADE_ORACLE_PLATFORM_API_KEY",
            },
            deployment={
                "container_entrypoint": "uvicorn api.trade_oracle_platform_service:app --host 0.0.0.0 --port ${PORT:-8000}",
                "dockerfile": "Dockerfile.langgraph",
                "checkpointer_path": resolved_checkpointer_path,
                "audit_db_path": resolved_audit_db_path,
                "benchmark_db_path": resolved_benchmark_db_path,
                "required_env": [
                    "TRADE_ORACLE_PLATFORM_API_KEY",
                    "TRADE_ORACLE_PLATFORM_REQUIRE_AUTH",
                    "TRADE_ORACLE_LANGGRAPH_CHECKPOINTER_PATH",
                    "TRADE_ORACLE_AUDIT_BACKEND",
                    "TRADE_ORACLE_AUDIT_DB_PATH",
                    "TRADE_ORACLE_BENCHMARK_BACKEND",
                    "TRADE_ORACLE_BENCHMARK_DB_PATH",
                ],
            },
        )

    return app


app = build_trade_oracle_platform_app()


__all__ = [
    "PlatformHealthResponse",
    "PlatformCapabilitiesResponse",
    "PlatformAuditResponse",
    "PlatformBenchmarkResponse",
    "PlatformBenchmarkSummaryResponse",
    "PlatformBenchmarkCycleResponse",
    "build_trade_oracle_platform_app",
    "app",
]
