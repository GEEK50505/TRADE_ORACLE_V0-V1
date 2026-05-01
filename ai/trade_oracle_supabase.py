"""Shared Supabase client helpers for TRADE_ORACLE cloud-backed state."""

from __future__ import annotations

from typing import Any

from config import settings


def _patch_gotrue_sync_client() -> None:
    """Patch gotrue's SyncClient to ignore unsupported proxy kwargs."""

    try:
        from gotrue.http_clients import SyncClient as _GotrueSyncClient
    except ImportError:
        return

    if getattr(_GotrueSyncClient.__init__, "_trade_oracle_proxy_patch", False):
        return

    original_init = _GotrueSyncClient.__init__

    def _patched_init(self: Any, *args: Any, proxy: Any = None, **kwargs: Any) -> Any:
        return original_init(self, *args, **kwargs)

    setattr(_patched_init, "_trade_oracle_proxy_patch", True)
    _GotrueSyncClient.__init__ = _patched_init


def build_trade_oracle_supabase_client(
    *,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
) -> Any:
    """Build the shared Supabase client from explicit or env-backed settings."""

    _patch_gotrue_sync_client()

    from supabase import create_client

    resolved_url = (supabase_url or settings.SUPABASE_URL or "").strip()
    resolved_key = (supabase_key or settings.SUPABASE_KEY or "").strip()
    missing: list[str] = []
    if not resolved_url:
        missing.append("SUPABASE_URL")
    if not resolved_key:
        missing.append("SUPABASE_KEY")
    if missing:
        raise ValueError("Missing Supabase connection fields: " + ", ".join(missing))
    return create_client(resolved_url, resolved_key)


def coerce_supabase_rows(response: Any) -> list[dict[str, Any]]:
    """Normalize Supabase execute() responses into a list of row dictionaries."""

    data = getattr(response, "data", None)
    if not data:
        return []
    if isinstance(data, list):
        return [dict(item) for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [dict(data)]
    return []


__all__ = [
    "build_trade_oracle_supabase_client",
    "coerce_supabase_rows",
]
