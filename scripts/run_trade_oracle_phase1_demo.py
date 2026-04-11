"""
CLI runner for the TRADE_ORACLE LangGraph Phase 1 demo.

This stays intentionally small: it uses the fixed final 3-pair scanner payload,
can optionally point the graph at the FastAPI MCP service, and prints the
interrupt/final decision path in a readable way.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ai.trade_oracle_langgraph_phase1 import (
    DEFAULT_CHECKPOINTER_PATH,
    TradeOracleMCPHttpClient,
    run_phase1_demo_from_scanner,
    run_phase1_demo,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the TRADE_ORACLE LangGraph Phase 1 demo.")
    parser.add_argument(
        "--checkpointer-path",
        default=str(DEFAULT_CHECKPOINTER_PATH),
        help="SQLite checkpointer path for the LangGraph thread.",
    )
    parser.add_argument(
        "--mcp-service-url",
        default=None,
        help="Optional FastAPI MCP base URL. If omitted, the graph uses local deterministic tool stubs.",
    )
    parser.add_argument(
        "--mcp-api-key",
        default=None,
        help="Optional MCP API key header for authenticated FastAPI service calls.",
    )
    parser.add_argument(
        "--enable-live-llm",
        action="store_true",
        help="Enable live Gemini/OpenRouter model invocation instead of deterministic fallbacks.",
    )
    parser.add_argument(
        "--hydrate-account-state",
        action="store_true",
        help="Hydrate account context from Match-Trader and Supabase when credentials and dependencies are available.",
    )
    parser.add_argument(
        "--thread-id",
        default=None,
        help="Optional explicit thread id. A unique id is generated automatically when omitted.",
    )
    parser.add_argument(
        "--from-scanner",
        action="store_true",
        help="Build the raw_setup from the existing Phase 2 MarketScanner instead of the fixed demo payload.",
    )
    parser.add_argument(
        "--scanner-limit",
        type=int,
        default=None,
        help="Optional cap on the number of adapted scanner setups to fetch before selecting one.",
    )
    parser.add_argument(
        "--scanner-setup-index",
        type=int,
        default=0,
        help="Zero-based index of the adapted scanner setup to route through the graph.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client: TradeOracleMCPHttpClient | None = None
    try:
        if args.mcp_service_url:
            client = TradeOracleMCPHttpClient(
                base_url=args.mcp_service_url,
                api_key=args.mcp_api_key,
            )

        if args.from_scanner:
            selected_setup, first_pass, final_pass = run_phase1_demo_from_scanner(
                checkpointer_path=Path(args.checkpointer_path),
                enable_live_llm=args.enable_live_llm,
                hydrate_account_state=args.hydrate_account_state,
                scanner_limit=args.scanner_limit,
                scanner_setup_index=args.scanner_setup_index,
                thread_id=args.thread_id,
                mcp_service_base_url=args.mcp_service_url,
                mcp_http_client=client,
            )
            print("SELECTED_SETUP")
            print(json.dumps(selected_setup, indent=2, default=str))
            print()
        else:
            first_pass, final_pass = run_phase1_demo(
                checkpointer_path=Path(args.checkpointer_path),
                enable_live_llm=args.enable_live_llm,
                hydrate_account_state=args.hydrate_account_state,
                thread_id=args.thread_id,
                mcp_service_base_url=args.mcp_service_url,
                mcp_http_client=client,
            )

        print("FIRST_PASS")
        print(json.dumps(first_pass, indent=2, default=str))
        if final_pass is not None:
            print("\nFINAL_PASS")
            print(json.dumps(final_pass, indent=2, default=str))
        else:
            print("\nFINAL_PASS")
            print("null")
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()
