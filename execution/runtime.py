"""Shared execution-backend selection and client factory helpers."""

from __future__ import annotations

from typing import Any

from config import settings

SUPPORTED_EXECUTION_BACKENDS = {"match_trader", "mt5"}


def resolve_execution_backend(explicit_backend: str | None = None) -> str:
    """Resolve the configured execution backend with a safe fallback."""

    raw_value = explicit_backend or settings.TRADE_ORACLE_EXECUTION_BACKEND or "match_trader"
    backend = str(raw_value).strip().lower()
    if backend in SUPPORTED_EXECUTION_BACKENDS:
        return backend
    return "match_trader"


def build_execution_client(
    *,
    execution_backend: str | None = None,
    broker_id: str | None = None,
    email: str | None = None,
    password: str | None = None,
    base_url: str | None = None,
    system_uuid: str | None = None,
    mt5_login: int | str | None = None,
    mt5_password: str | None = None,
    mt5_server: str | None = None,
    mt5_terminal_path: str | None = None,
    mt5_symbol_suffix: str | None = None,
    mt5_symbol_map: dict[str, str] | None = None,
    match_trader_api_cls: type[Any] | None = None,
    mt5_bridge_cls: type[Any] | None = None,
) -> Any:
    """Instantiate the selected execution bridge using explicit or env-backed fields."""

    backend = resolve_execution_backend(execution_backend)

    if backend == "match_trader":
        resolved_broker_id = broker_id or settings.MATCH_TRADER_BROKER_ID
        resolved_email = email or settings.MATCH_TRADER_USER
        resolved_password = password or settings.MATCH_TRADER_PASS
        resolved_base_url = base_url or settings.MATCH_TRADER_BASE_URL

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
            raise ValueError("Missing Match-Trader connection fields: " + ", ".join(missing))

        if match_trader_api_cls is None:
            from execution.match_trader import MatchTraderAPI as resolved_match_trader_api_cls

            match_trader_api_cls = resolved_match_trader_api_cls

        client = match_trader_api_cls(
            broker_id=resolved_broker_id,
            email=resolved_email,
            password=resolved_password,
            base_url=resolved_base_url,
        )
        if system_uuid and hasattr(client, "system_uuid"):
            client.system_uuid = system_uuid
        return client

    resolved_mt5_login = mt5_login or settings.MT5_LOGIN
    resolved_mt5_password = mt5_password or settings.MT5_PASSWORD
    resolved_mt5_server = mt5_server or settings.MT5_SERVER
    resolved_mt5_terminal_path = mt5_terminal_path or settings.MT5_TERMINAL_PATH
    resolved_mt5_symbol_suffix = mt5_symbol_suffix or settings.MT5_SYMBOL_SUFFIX
    resolved_mt5_symbol_map = mt5_symbol_map or settings.MT5_SYMBOL_MAP

    missing = [
        name
        for name, value in {
            "mt5_login": resolved_mt5_login,
            "mt5_password": resolved_mt5_password,
            "mt5_server": resolved_mt5_server,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError("Missing MT5 connection fields: " + ", ".join(missing))

    if mt5_bridge_cls is None:
        from execution.mt5_bridge import MetaTraderBridge as resolved_mt5_bridge_cls

        mt5_bridge_cls = resolved_mt5_bridge_cls

    return mt5_bridge_cls(
        login=resolved_mt5_login,
        password=resolved_mt5_password,
        server=resolved_mt5_server,
        terminal_path=resolved_mt5_terminal_path,
        symbol_suffix=resolved_mt5_symbol_suffix,
        symbol_map=resolved_mt5_symbol_map,
    )


def build_execution_client_from_settings(
    *,
    match_trader_api_cls: type[Any] | None = None,
    mt5_bridge_cls: type[Any] | None = None,
) -> Any:
    """Build the configured execution client directly from settings/env vars."""

    return build_execution_client(
        execution_backend=settings.TRADE_ORACLE_EXECUTION_BACKEND,
        match_trader_api_cls=match_trader_api_cls,
        mt5_bridge_cls=mt5_bridge_cls,
    )
