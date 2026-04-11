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


class MatchTraderConnectionRequest(BaseModel):
    """Reusable Match-Trader connection fields with env-backed fallbacks."""

    model_config = ConfigDict(extra="forbid")

    broker_id: str | None = None
    email: str | None = None
    password: str | None = None
    base_url: str | None = None
    system_uuid: str | None = None


class ExecutionPlatformDetailsRequest(MatchTraderConnectionRequest):
    """Fetch platform state from Match-Trader via HTTP."""


class ExecutionTransmitOrderRequest(MatchTraderConnectionRequest):
    """Transmit one limit order through the Match-Trader execution bridge."""

    symbol: str
    direction: Literal["BUY", "SELL"]
    size: float
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


def _build_match_trader_client(
    request: MatchTraderConnectionRequest,
    *,
    match_trader_api_cls: type[Any] | None = None,
) -> Any:
    resolved_broker_id = request.broker_id or settings.MATCH_TRADER_BROKER_ID
    resolved_email = request.email or settings.MATCH_TRADER_USER
    resolved_password = request.password or settings.MATCH_TRADER_PASS
    resolved_base_url = request.base_url or settings.MATCH_TRADER_BASE_URL

    missing = [
        name
        for name, value in {
            "broker_id": resolved_broker_id,
            "email": resolved_email,
            "password": resolved_password,
            "base_url": resolved_base_url,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(
            "Missing Match-Trader connection fields: " + ", ".join(missing)
        )

    if match_trader_api_cls is None:
        from execution.match_trader import MatchTraderAPI as resolved_match_trader_api_cls

        match_trader_api_cls = resolved_match_trader_api_cls

    client = match_trader_api_cls(
        broker_id=resolved_broker_id,
        email=resolved_email,
        password=resolved_password,
        base_url=resolved_base_url,
    )
    if request.system_uuid:
        client.system_uuid = request.system_uuid
    return client


def build_trade_oracle_ops_app(
    *,
    require_auth: bool = settings.TRADE_ORACLE_OPS_REQUIRE_AUTH,
    api_key: str | None = settings.TRADE_ORACLE_OPS_API_KEY,
    phase2_scanner_runner: Callable[[list[str]], Awaitable[list[dict[str, Any]]]] | None = None,
    live_scanner_runner: Callable[[LiveScannerRequest], Awaitable[dict[str, Any]]] | None = None,
    match_trader_api_cls: type[Any] | None = None,
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
            "REST/webhook facade for the Phase 2 scanner, RiskManager, and Match-Trader execution bridge."
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
        client = _build_match_trader_client(payload, match_trader_api_cls=match_trader_api_cls)
        authenticated = await client.authenticate()
        if not authenticated:
            raise ValueError("Match-Trader authentication failed.")

        details = await client.get_platform_details()
        return _ops_response(
            operation="execution_platform_details",
            detail="Retrieved platform equity and active-trade state from Match-Trader.",
            result={
                "authenticated": authenticated,
                "platform_details": details,
            },
            request=http_request,
        )

    @app.post("/ops/execution/transmit-limit-order", response_model=OpsServiceResponse)
    async def execution_transmit_limit_order(
        payload: ExecutionTransmitOrderRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> OpsServiceResponse:
        client = _build_match_trader_client(payload, match_trader_api_cls=match_trader_api_cls)
        authenticated = await client.authenticate()
        if not authenticated:
            raise ValueError("Match-Trader authentication failed.")

        transmitted = await client.transmit_limit_order(
            symbol=payload.symbol,
            direction=payload.direction,
            size=payload.size,
            limit_price=payload.limit_price,
            stop_loss=payload.stop_loss,
            take_profit=payload.take_profit,
        )
        return _ops_response(
            operation="execution_transmit_limit_order",
            detail="Match-Trader limit order transmission completed.",
            result={
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
    "ExecutionPlatformDetailsRequest",
    "ExecutionTransmitOrderRequest",
    "build_trade_oracle_ops_app",
    "app",
]
