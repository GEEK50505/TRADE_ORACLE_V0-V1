"""
Operational FastAPI service for scanner, risk, and execution endpoints.

This service is the n8n-friendly HTTP/webhook layer around the existing Python
modules. It calls the real modules directly and avoids subprocess indirection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from config import settings
from execution.runtime import build_execution_client, resolve_execution_backend

from .trade_oracle_mcp_service import _authorization_dependency, _error_response, _response_meta


class OpsServiceResponse(BaseModel):
    """Uniform REST envelope for operational scanner/risk/execution endpoints."""

    model_config = ConfigDict(extra="forbid")

    operation: str
    status: Literal["ok", "error"]
    detail: str
    result: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class Phase2ScannerRequest(BaseModel):
    """Request contract for the core Phase 2 watchlist scanner."""

    model_config = ConfigDict(extra="forbid")

    watchlist: list[str] = Field(default_factory=lambda: list(settings.WATCHLIST))


class LiveScannerRequest(BaseModel):
    """Request contract for the final-shortlist live scanner."""

    model_config = ConfigDict(extra="forbid")

    shortlist_path: str = "results/backtrader_combined_final_shortlist.csv"
    ranking_path: str = "results/backtrader_combined_survivor_ranking.csv"
    daily_data_path: str = "data/market_data_multi_1D.parquet"
    intraday_data_path: str = "data/market_data_multi_4H.parquet"
    top_n: int = 5
    mode: Literal["live", "test"] = "live"


class RiskEvaluateRequest(BaseModel):
    """RiskManager REST request with optional position sizing context."""

    model_config = ConfigDict(extra="forbid")

    current_balance: float
    highest_equity: float
    active_trades_count: int = 0
    entry_price: float | None = None
    atr: float | None = None
    direction: Literal["LONG", "SHORT", "BUY", "SELL"] = "LONG"


class ExecutionConnectionRequest(BaseModel):
    """Reusable execution-bridge connection fields with env-backed fallbacks."""

    model_config = ConfigDict(extra="forbid")

    execution_backend: Literal["match_trader", "mt5"] = Field(default_factory=resolve_execution_backend)

    # Match-Trader fields
    broker_id: str | None = None
    email: str | None = None
    password: str | None = None
    base_url: str | None = None
    system_uuid: str | None = None

    # MetaTrader 5 fields
    mt5_login: int | str | None = None
    mt5_password: str | None = None
    mt5_server: str | None = None
    mt5_terminal_path: str | None = None
    mt5_symbol_suffix: str | None = None
    mt5_symbol_map: dict[str, str] = Field(default_factory=dict)


class ExecutionPlatformDetailsRequest(ExecutionConnectionRequest):
    """Fetch platform state from the configured execution backend."""


class AccountStateRequest(ExecutionConnectionRequest):
    """Fetch live account oversight state for trailing-drawdown monitoring."""


class ExecutionSymbolStatusRequest(ExecutionConnectionRequest):
    """Inspect whether one execution symbol is available and quoted on the backend."""

    symbol: str


class ExecutionTransmitOrderRequest(ExecutionConnectionRequest):
    """Transmit one limit order through the configured execution bridge."""

    symbol: str
    direction: Literal["BUY", "SELL"]
    size: float
    size_mode: Literal["units", "broker_volume"] = "units"
    limit_price: float
    stop_loss: float
    take_profit: float


def _ops_response(
    *,
    operation: str,
    detail: str,
    result: dict[str, Any],
    request: Request | None = None,
) -> OpsServiceResponse:
    return OpsServiceResponse(
        operation=operation,
        status="ok",
        detail=detail,
        result=result,
        meta={
            **_response_meta(request=request, tool_name=operation),
            "service": "trade_oracle_ops",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )


def _normalize_risk_direction(direction: str) -> str:
    return "LONG" if direction.upper() in {"BUY", "LONG"} else "SHORT"


async def _default_phase2_scanner_runner(watchlist: list[str]) -> list[dict[str, Any]]:
    from data.scanner import MarketScanner

    scanner = MarketScanner(watchlist)
    return await scanner.run_scan()


async def _default_live_scanner_runner(request: LiveScannerRequest) -> dict[str, Any]:
    from backtrader_evaluate_combined import MarketDataCatalog
    from scripts.scanner_live import build_header, resolve_final_pairs, scan_live_pairs

    final_pairs, resolved_df = resolve_final_pairs(
        shortlist_path=request.shortlist_path,
        ranking_path=request.ranking_path,
        top_n=request.top_n,
    )
    catalog = MarketDataCatalog(
        daily_path=request.daily_data_path,
        intraday_path=request.intraday_data_path,
    )
    setups = scan_live_pairs(final_pairs, resolved_df, catalog)
    return {
        "mode": request.mode,
        "active_pairs": len(final_pairs),
        "header": build_header(request.mode, len(final_pairs), catalog),
        "setups": setups,
    }


def _resolve_high_watermark(
    *,
    current_equity: float,
    state_manager_factory: Callable[[], Any] | None = None,
) -> tuple[float, str, str]:
    """Resolve the persisted peak equity, falling back safely when state storage is unavailable."""

    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        return current_equity, "fallback_current_equity", "Supabase credentials are not configured."

    try:
        resolved_state_manager_factory = state_manager_factory
        if resolved_state_manager_factory is None:
            from journal.supabase_client import StateManager as resolved_state_manager_factory

        state_manager = resolved_state_manager_factory()
        high_watermark = float(state_manager.update_high_watermark(current_equity))
        return high_watermark, "supabase", ""
    except Exception as exc:  # pragma: no cover - defensive fail-safe for live env drift
        return current_equity, "fallback_current_equity", str(exc)


def build_trade_oracle_ops_app(
    *,
    require_auth: bool = settings.TRADE_ORACLE_OPS_REQUIRE_AUTH,
    api_key: str | None = settings.TRADE_ORACLE_OPS_API_KEY,
    phase2_scanner_runner: Callable[[list[str]], Awaitable[list[dict[str, Any]]]] | None = None,
    live_scanner_runner: Callable[[LiveScannerRequest], Awaitable[dict[str, Any]]] | None = None,
    match_trader_api_cls: type[Any] | None = None,
    mt5_bridge_cls: type[Any] | None = None,
    state_manager_factory: Callable[[], Any] | None = None,
) -> FastAPI:
    """Create the webhook-safe operational service for scanner/risk/execution flows."""

    authorize_request = _authorization_dependency(
        require_auth=require_auth,
        expected_api_key=api_key,
    )
    resolved_phase2_scanner_runner = phase2_scanner_runner or _default_phase2_scanner_runner
    resolved_live_scanner_runner = live_scanner_runner or _default_live_scanner_runner

    app = FastAPI(
        title="TRADE_ORACLE Operational Service",
        version="0.1.0",
        description=(
            "REST/webhook facade for the Phase 2 scanner, RiskManager, and broker execution bridges."
        ),
    )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        body = _error_response(
            tool_name="ops_validation_error",
            detail="Invalid operational service request payload.",
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
            tool_name="ops_internal_error",
            detail="Unhandled exception in the TRADE_ORACLE operational service.",
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

    @app.post("/ops/scanner/phase2/run", response_model=OpsServiceResponse)
    async def run_phase2_scanner(
        payload: Phase2ScannerRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> OpsServiceResponse:
        setups = await resolved_phase2_scanner_runner(list(payload.watchlist))
        return _ops_response(
            operation="run_phase2_scanner",
            detail="Phase 2 structural watchlist scan completed.",
            result={
                "watchlist_size": len(payload.watchlist),
                "setup_count": len(setups),
                "setups": setups,
            },
            request=http_request,
        )

    @app.post("/ops/scanner/live/run", response_model=OpsServiceResponse)
    async def run_live_scanner(
        payload: LiveScannerRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> OpsServiceResponse:
        result = await resolved_live_scanner_runner(payload)
        return _ops_response(
            operation="run_live_scanner",
            detail="Final-shortlist live scanner completed.",
            result=result,
            request=http_request,
        )

    @app.post("/ops/risk/evaluate", response_model=OpsServiceResponse)
    async def evaluate_risk(
        payload: RiskEvaluateRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> OpsServiceResponse:
        from risk.manager import RiskManager

        manager = RiskManager(
            current_balance=payload.current_balance,
            highest_equity=payload.highest_equity,
            active_trades_count=payload.active_trades_count,
        )
        can_open_new_trade = manager.can_open_new_trade()
        position_size = None
        if payload.entry_price is not None and payload.atr is not None:
            position_size = manager.calculate_position_size(
                entry_price=payload.entry_price,
                atr=payload.atr,
                direction=_normalize_risk_direction(payload.direction),
            )

        return _ops_response(
            operation="evaluate_risk",
            detail="RiskManager gatekeeping and sizing check completed.",
            result={
                "can_open_new_trade": can_open_new_trade,
                "position_size": position_size,
                "risk_amount_usd": manager.risk_usd,
                "max_concurrent_trades": settings.MAX_CONCURRENT_TRADES,
                "max_trailing_drawdown_pct": settings.MAX_TRAILING_DRAWDOWN_PCT,
            },
            request=http_request,
        )

    @app.post("/ops/execution/platform-details", response_model=OpsServiceResponse)
    async def execution_platform_details(
        payload: ExecutionPlatformDetailsRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> OpsServiceResponse:
        execution_backend = resolve_execution_backend(payload.execution_backend)
        client = build_execution_client(
            execution_backend=execution_backend,
            broker_id=payload.broker_id,
            email=payload.email,
            password=payload.password,
            base_url=payload.base_url,
            system_uuid=payload.system_uuid,
            mt5_login=payload.mt5_login,
            mt5_password=payload.mt5_password,
            mt5_server=payload.mt5_server,
            mt5_terminal_path=payload.mt5_terminal_path,
            mt5_symbol_suffix=payload.mt5_symbol_suffix,
            mt5_symbol_map=payload.mt5_symbol_map,
            match_trader_api_cls=match_trader_api_cls,
            mt5_bridge_cls=mt5_bridge_cls,
        )
        authenticated = await client.authenticate()
        if not authenticated:
            raise ValueError(f"{execution_backend} authentication failed.")

        details = await client.get_platform_details()
        return _ops_response(
            operation="execution_platform_details",
            detail="Retrieved platform equity and active-trade state from the configured execution backend.",
            result={
                "execution_backend": execution_backend,
                "authenticated": authenticated,
                "platform_details": details,
            },
            request=http_request,
        )

    @app.post("/ops/account/state", response_model=OpsServiceResponse)
    async def account_state(
        payload: AccountStateRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> OpsServiceResponse:
        execution_backend = resolve_execution_backend(payload.execution_backend)
        client = build_execution_client(
            execution_backend=execution_backend,
            broker_id=payload.broker_id,
            email=payload.email,
            password=payload.password,
            base_url=payload.base_url,
            system_uuid=payload.system_uuid,
            mt5_login=payload.mt5_login,
            mt5_password=payload.mt5_password,
            mt5_server=payload.mt5_server,
            mt5_terminal_path=payload.mt5_terminal_path,
            mt5_symbol_suffix=payload.mt5_symbol_suffix,
            mt5_symbol_map=payload.mt5_symbol_map,
            match_trader_api_cls=match_trader_api_cls,
            mt5_bridge_cls=mt5_bridge_cls,
        )
        authenticated = await client.authenticate()
        if not authenticated:
            raise ValueError(f"{execution_backend} authentication failed.")

        details = await client.get_platform_details()
        if not details:
            raise ValueError(f"{execution_backend} platform state could not be retrieved.")

        current_equity = float(details.get("equity", 0.0))
        active_trades = int(details.get("active_trades", 0))
        high_watermark, high_watermark_source, fallback_reason = _resolve_high_watermark(
            current_equity=current_equity,
            state_manager_factory=state_manager_factory,
        )

        max_allowed_drawdown_usd = float(high_watermark) * settings.MAX_TRAILING_DRAWDOWN_PCT
        current_drawdown_usd = max(float(high_watermark) - current_equity, 0.0)
        distance_to_failure_usd = max_allowed_drawdown_usd - current_drawdown_usd
        distance_to_failure_pct = (
            distance_to_failure_usd / float(high_watermark)
            if float(high_watermark) > 0
            else 0.0
        )

        from risk.manager import RiskManager

        risk_manager = RiskManager(
            current_balance=current_equity,
            highest_equity=float(high_watermark),
            active_trades_count=active_trades,
        )

        return _ops_response(
            operation="account_state",
            detail="Resolved live account oversight state from the configured execution backend and persistent memory.",
            result={
                "execution_backend": execution_backend,
                "authenticated": authenticated,
                "current_equity": current_equity,
                "active_trades": active_trades,
                "high_watermark": float(high_watermark),
                "high_watermark_source": high_watermark_source,
                "fallback_reason": fallback_reason,
                "max_trailing_drawdown_pct": settings.MAX_TRAILING_DRAWDOWN_PCT,
                "max_allowed_drawdown_usd": round(max_allowed_drawdown_usd, 2),
                "current_drawdown_usd": round(current_drawdown_usd, 2),
                "distance_to_failure_usd": round(distance_to_failure_usd, 2),
                "distance_to_failure_pct": round(distance_to_failure_pct, 6),
                "warning_buffer_usd": 15.0,
                "warning_buffer_triggered": distance_to_failure_usd <= 15.0,
                "can_open_new_trade": risk_manager.can_open_new_trade(),
            },
            request=http_request,
        )

    @app.post("/ops/execution/symbol-status", response_model=OpsServiceResponse)
    async def execution_symbol_status(
        payload: ExecutionSymbolStatusRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> OpsServiceResponse:
        execution_backend = resolve_execution_backend(payload.execution_backend)
        client = build_execution_client(
            execution_backend=execution_backend,
            broker_id=payload.broker_id,
            email=payload.email,
            password=payload.password,
            base_url=payload.base_url,
            system_uuid=payload.system_uuid,
            mt5_login=payload.mt5_login,
            mt5_password=payload.mt5_password,
            mt5_server=payload.mt5_server,
            mt5_terminal_path=payload.mt5_terminal_path,
            mt5_symbol_suffix=payload.mt5_symbol_suffix,
            mt5_symbol_map=payload.mt5_symbol_map,
            match_trader_api_cls=match_trader_api_cls,
            mt5_bridge_cls=mt5_bridge_cls,
        )
        authenticated = await client.authenticate()
        if not authenticated:
            raise ValueError(f"{execution_backend} authentication failed.")
        if not hasattr(client, "get_symbol_status"):
            raise ValueError(f"{execution_backend} symbol inspection is not implemented.")

        symbol_status = await client.get_symbol_status(payload.symbol)
        return _ops_response(
            operation="execution_symbol_status",
            detail="Resolved symbol availability on the configured execution backend.",
            result={
                "execution_backend": execution_backend,
                "authenticated": authenticated,
                "symbol_status": symbol_status,
            },
            request=http_request,
        )

    @app.post("/ops/execution/transmit-limit-order", response_model=OpsServiceResponse)
    async def execution_transmit_limit_order(
        payload: ExecutionTransmitOrderRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> OpsServiceResponse:
        execution_backend = resolve_execution_backend(payload.execution_backend)
        client = build_execution_client(
            execution_backend=execution_backend,
            broker_id=payload.broker_id,
            email=payload.email,
            password=payload.password,
            base_url=payload.base_url,
            system_uuid=payload.system_uuid,
            mt5_login=payload.mt5_login,
            mt5_password=payload.mt5_password,
            mt5_server=payload.mt5_server,
            mt5_terminal_path=payload.mt5_terminal_path,
            mt5_symbol_suffix=payload.mt5_symbol_suffix,
            mt5_symbol_map=payload.mt5_symbol_map,
            match_trader_api_cls=match_trader_api_cls,
            mt5_bridge_cls=mt5_bridge_cls,
        )
        authenticated = await client.authenticate()
        if not authenticated:
            raise ValueError(f"{execution_backend} authentication failed.")

        transmitted = await client.transmit_limit_order(
            symbol=payload.symbol,
            direction=payload.direction,
            size=payload.size,
            size_mode=payload.size_mode,
            limit_price=payload.limit_price,
            stop_loss=payload.stop_loss,
            take_profit=payload.take_profit,
        )
        return _ops_response(
            operation="execution_transmit_limit_order",
            detail="Execution-backend limit order transmission completed.",
            result={
                "execution_backend": execution_backend,
                "authenticated": authenticated,
                "order_transmitted": bool(transmitted),
                "symbol": payload.symbol,
                "direction": payload.direction,
            },
            request=http_request,
        )

    return app


app = build_trade_oracle_ops_app()


__all__ = [
    "OpsServiceResponse",
    "Phase2ScannerRequest",
    "LiveScannerRequest",
    "RiskEvaluateRequest",
    "AccountStateRequest",
    "ExecutionPlatformDetailsRequest",
    "ExecutionSymbolStatusRequest",
    "ExecutionTransmitOrderRequest",
    "build_trade_oracle_ops_app",
    "app",
]
