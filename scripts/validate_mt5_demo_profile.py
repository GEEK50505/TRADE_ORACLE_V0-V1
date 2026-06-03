"""Validate an MT5 demo profile against the local TRADE_ORACLE platform surface.

This script is intentionally safe by default:
- authenticates to the configured MT5 demo
- checks live account oversight state
- checks symbol availability / quote health
- does not transmit any orders
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_SYMBOLS = [
    "AVAX/USDT",
    "DOGE/USDT",
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "XRP/USDT",
]


def _parse_symbols(raw_symbols: str | None) -> list[str]:
    if not raw_symbols:
        return list(DEFAULT_SYMBOLS)
    return [item.strip() for item in raw_symbols.split(",") if item.strip()]


def _build_base_payload() -> dict[str, Any]:
    from config import settings

    missing = [
        name
        for name, value in {
            "MT5_LOGIN": settings.MT5_LOGIN,
            "MT5_PASSWORD": settings.MT5_PASSWORD,
            "MT5_SERVER": settings.MT5_SERVER,
            "MT5_TERMINAL_PATH": settings.MT5_TERMINAL_PATH,
        }.items()
        if not value
    ]
    if missing:
        raise SystemExit(
            "Missing required MT5 env vars for demo validation: " + ", ".join(missing)
        )

    payload: dict[str, Any] = {
        "execution_backend": "mt5",
        "mt5_login": settings.MT5_LOGIN,
        "mt5_password": settings.MT5_PASSWORD,
        "mt5_server": settings.MT5_SERVER,
        "mt5_terminal_path": settings.MT5_TERMINAL_PATH,
    }
    if settings.MT5_SYMBOL_SUFFIX:
        payload["mt5_symbol_suffix"] = settings.MT5_SYMBOL_SUFFIX
    if settings.MT5_SYMBOL_MAP:
        payload["mt5_symbol_map"] = settings.MT5_SYMBOL_MAP
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a local MT5 demo profile through the TRADE_ORACLE platform routes."
    )
    parser.add_argument(
        "--env-file",
        default=".env.n8n.local",
        help="Env file to load before validating the MT5 demo profile.",
    )
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated strategy symbols to inspect. Default audits the core watchlist subset.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional path to save the JSON summary.",
    )
    args = parser.parse_args()
    load_dotenv(REPO_ROOT / args.env_file, override=True)
    from api.trade_oracle_platform_service import build_trade_oracle_platform_app
    from config import settings

    symbols = _parse_symbols(args.symbols)
    payload = _build_base_payload()

    app = build_trade_oracle_platform_app(require_auth=False)
    client = TestClient(app)

    account_state_response = client.post("/services/ops/ops/account/state", json=payload)
    account_state_response.raise_for_status()
    account_state_result = account_state_response.json()["result"]

    symbol_results: list[dict[str, Any]] = []
    for symbol in symbols:
        symbol_response = client.post(
            "/services/ops/ops/execution/symbol-status",
            json={**payload, "symbol": symbol},
        )
        symbol_response.raise_for_status()
        symbol_results.append(symbol_response.json()["result"]["symbol_status"])

    summary = {
        "execution_backend": "mt5",
        "server": settings.MT5_SERVER,
        "terminal_path": settings.MT5_TERMINAL_PATH,
        "symbol_map": settings.MT5_SYMBOL_MAP,
        "account_state": account_state_result,
        "symbols": symbol_results,
        "next_step": (
            "If the intended symbols are available and have live ticks, proceed to the "
            "scanner -> superbrain -> review -> risk preflight before any demo transmit."
        ),
    }

    rendered = json.dumps(summary, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")

    print(rendered)


if __name__ == "__main__":
    main()
