"""Generate a trading-health report for TRADE_ORACLE from benchmark, journal, and MT5 state."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def _int_value(value: Any, default: int = -1) -> int:
    if value is None:
        return default
    return int(value)


def _type_name(type_code: int) -> str:
    mapping = {
        0: "BUY",
        1: "SELL",
        2: "BUY_LIMIT",
        3: "SELL_LIMIT",
        4: "BUY_STOP",
        5: "SELL_STOP",
        6: "BUY_STOP_LIMIT",
        7: "SELL_STOP_LIMIT",
    }
    return mapping.get(int(type_code), f"TYPE_{type_code}")


def collect_report(env_file: str, *, cycle_limit: int, journal_limit: int) -> dict[str, Any]:
    load_dotenv(REPO_ROOT / env_file, override=True)

    from ai.trade_oracle_storage import build_trade_oracle_benchmark_store, build_trade_oracle_runtime_state_store
    from config import settings
    from execution.mt5_bridge import MetaTraderBridge

    benchmark_store = build_trade_oracle_benchmark_store(backend=settings.TRADE_ORACLE_BENCHMARK_BACKEND)
    runtime_store = build_trade_oracle_runtime_state_store(backend=settings.TRADE_ORACLE_RUNTIME_STATE_BACKEND)

    benchmark_summary = benchmark_store.build_summary(
        benchmark_variant=settings.TRADE_ORACLE_BENCHMARK_VARIANT,
        execution_backend=settings.TRADE_ORACLE_EXECUTION_BACKEND,
    )
    recent_cycles = benchmark_store.list_recent_cycle_summaries(
        limit=cycle_limit,
        benchmark_variant=settings.TRADE_ORACLE_BENCHMARK_VARIANT,
        execution_backend=settings.TRADE_ORACLE_EXECUTION_BACKEND,
        fetch_limit=max(5000, cycle_limit * 40),
    )
    forward_journal = runtime_store.list_forward_journal_entries(limit=journal_limit)
    pending_reviews = runtime_store.list_pending_reviews(limit=journal_limit)

    journal_outcomes = Counter(entry.outcome for entry in forward_journal)
    journal_symbols = defaultdict(Counter)
    for entry in forward_journal:
        if entry.symbol:
            journal_symbols[entry.symbol][entry.outcome] += 1

    cycle_decisions = Counter(cycle["latest_decision"] for cycle in recent_cycles)
    cycle_symbols = defaultdict(Counter)
    for cycle in recent_cycles:
        for symbol in cycle.get("symbols", []):
            cycle_symbols[str(symbol)][str(cycle["latest_decision"])] += 1

    cycle_funnel = {
        "total_cycles_observed": len(recent_cycles),
        "cycles_with_pending_review": sum(1 for cycle in recent_cycles if cycle.get("pending_review")),
        "cycles_with_transmit_attempt": sum(1 for cycle in recent_cycles if cycle.get("transmit_attempted")),
        "cycles_with_transmit_success": sum(1 for cycle in recent_cycles if cycle.get("transmit_succeeded")),
        "cycles_with_error_events": sum(1 for cycle in recent_cycles if int(cycle.get("error_event_count", 0)) > 0),
    }

    review_conversion = {
        "pending_review_runs": int(benchmark_summary.get("pending_review_runs", 0) or 0),
        "super_brain_resumes": int(benchmark_summary.get("super_brain_resumes", 0) or 0),
        "resume_to_pending_ratio": _safe_round(
            (int(benchmark_summary.get("super_brain_resumes", 0) or 0) / int(benchmark_summary.get("pending_review_runs", 0) or 1)),
            4,
        )
        if int(benchmark_summary.get("pending_review_runs", 0) or 0) > 0
        else 0.0,
    }

    mt5_state: dict[str, Any] = {
        "checked": False,
        "authenticated": False,
        "platform_details": {},
        "pending_orders": [],
        "open_positions": [],
    }

    if settings.TRADE_ORACLE_EXECUTION_BACKEND == "mt5":
        try:
            import asyncio
            import MetaTrader5 as mt5

            async def _load_mt5() -> dict[str, Any]:
                bridge = MetaTraderBridge(
                    login=settings.MT5_LOGIN,
                    password=settings.MT5_PASSWORD,
                    server=settings.MT5_SERVER,
                    terminal_path=settings.MT5_TERMINAL_PATH,
                    symbol_suffix=settings.MT5_SYMBOL_SUFFIX,
                    symbol_map=settings.MT5_SYMBOL_MAP,
                )
                authenticated = await bridge.authenticate()
                details = await bridge.get_platform_details()
                orders = mt5.orders_get() or ()
                positions = mt5.positions_get() or ()
                return {
                    "checked": True,
                    "authenticated": bool(authenticated),
                    "platform_details": details or {},
                    "pending_orders": [
                        {
                            "ticket": int(getattr(order, "ticket", 0) or 0),
                            "symbol": str(getattr(order, "symbol", "") or ""),
                            "type": _type_name(_int_value(getattr(order, "type", None))),
                            "volume_initial": float(getattr(order, "volume_initial", 0.0) or 0.0),
                            "price_open": float(getattr(order, "price_open", 0.0) or 0.0),
                            "sl": float(getattr(order, "sl", 0.0) or 0.0),
                            "tp": float(getattr(order, "tp", 0.0) or 0.0),
                            "comment": str(getattr(order, "comment", "") or ""),
                        }
                        for order in orders
                    ],
                    "open_positions": [
                        {
                            "ticket": int(getattr(position, "ticket", 0) or 0),
                            "symbol": str(getattr(position, "symbol", "") or ""),
                            "type": _type_name(_int_value(getattr(position, "type", None))),
                            "volume": float(getattr(position, "volume", 0.0) or 0.0),
                            "price_open": float(getattr(position, "price_open", 0.0) or 0.0),
                            "sl": float(getattr(position, "sl", 0.0) or 0.0),
                            "tp": float(getattr(position, "tp", 0.0) or 0.0),
                            "profit": float(getattr(position, "profit", 0.0) or 0.0),
                            "comment": str(getattr(position, "comment", "") or ""),
                        }
                        for position in positions
                    ],
                }

            mt5_state = asyncio.run(_load_mt5())
        except Exception as exc:  # pragma: no cover - live environment dependent
            mt5_state = {
                "checked": True,
                "authenticated": False,
                "error_type": type(exc).__name__,
                "message": str(exc),
                "platform_details": {},
                "pending_orders": [],
                "open_positions": [],
            }

    open_position_profit = sum(float(item.get("profit", 0.0) or 0.0) for item in mt5_state.get("open_positions", []))
    open_position_symbols = sorted({str(item.get("symbol", "")) for item in mt5_state.get("open_positions", []) if str(item.get("symbol", ""))})

    interpretation = {
        "cycle_engine_activity": "active" if int(benchmark_summary.get("total_cycles", 0) or 0) > 0 else "inactive",
        "execution_quality_assessment": (
            "some broker-side transmission is proven, but conversion from transmit attempt to successful transmit is still mixed"
            if float(benchmark_summary.get("broker_acceptance_rate", 0.0) or 0.0) < 0.75
            else "transmission quality appears strong for the observed sample"
        ),
        "risk_gate_assessment": (
            "recent flow is dominated by risk_rejected outcomes, so the system is trading conservatively or hitting broker/risk constraints before live placement"
            if journal_outcomes.get("risk_rejected", 0) >= max(3, journal_outcomes.get("resume_execution_result", 0) + 1)
            else "recent flow shows a more balanced mix of accepted and rejected cycles"
        ),
        "live_broker_exposure": {
            "open_position_count": len(mt5_state.get("open_positions", [])),
            "open_position_symbols": open_position_symbols,
            "aggregate_open_profit": _safe_round(open_position_profit, 2),
        },
        "missing_metrics": [
            "closed-trade realized PnL history is not yet pulled into this report",
            "implementation shortfall is not computed because decision-time and fill-time price attribution is not stored as a dedicated metric",
            "strategy expectancy from live realized closes is not yet available in a canonical report table",
        ],
    }

    return {
        "generated_at_utc": _utcnow_iso(),
        "env_file": str(REPO_ROOT / env_file),
        "execution_backend": settings.TRADE_ORACLE_EXECUTION_BACKEND,
        "benchmark_variant": settings.TRADE_ORACLE_BENCHMARK_VARIANT,
        "storage_backends": {
            "benchmark": settings.TRADE_ORACLE_BENCHMARK_BACKEND,
            "runtime_state": settings.TRADE_ORACLE_RUNTIME_STATE_BACKEND,
        },
        "benchmark_summary": benchmark_summary,
        "cycle_funnel": cycle_funnel,
        "review_conversion": review_conversion,
        "journal_outcomes": dict(journal_outcomes),
        "cycle_decisions": dict(cycle_decisions),
        "journal_symbol_outcomes": {symbol: dict(counter) for symbol, counter in journal_symbols.items()},
        "cycle_symbol_decisions": {symbol: dict(counter) for symbol, counter in cycle_symbols.items()},
        "recent_cycles": recent_cycles,
        "recent_forward_journal": [entry.model_dump() for entry in forward_journal],
        "pending_reviews": [entry.model_dump() for entry in pending_reviews],
        "mt5_state": mt5_state,
        "interpretation": interpretation,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    benchmark_summary = report["benchmark_summary"]
    cycle_funnel = report["cycle_funnel"]
    review_conversion = report["review_conversion"]
    mt5_state = report["mt5_state"]
    transmit_attempts = int(benchmark_summary.get("transmit_attempts", 0) or 0)
    transmit_successes = int(benchmark_summary.get("transmit_successes", 0) or 0)
    transmit_success_rate = _safe_round(transmit_successes / transmit_attempts, 4) if transmit_attempts > 0 else 0.0

    lines: list[str] = []
    lines.append("# TRADE_ORACLE Trading Health Report")
    lines.append("")
    lines.append(f"Generated at UTC: `{report['generated_at_utc']}`")
    lines.append("")
    lines.append("## Executive Snapshot")
    lines.append("")
    lines.append(f"- execution backend: `{report['execution_backend']}`")
    lines.append(f"- benchmark variant: `{report['benchmark_variant']}`")
    lines.append(f"- total cycles observed: `{benchmark_summary['total_cycles']}`")
    lines.append(f"- total benchmark events: `{benchmark_summary['total_events']}`")
    lines.append(f"- transmit attempts: `{benchmark_summary['transmit_attempts']}`")
    lines.append(f"- transmit successes: `{benchmark_summary['transmit_successes']}`")
    lines.append(f"- broker acceptance rate: `{benchmark_summary['broker_acceptance_rate']}`")
    lines.append(f"- transmit success rate from attempts: `{transmit_success_rate}`")
    lines.append(f"- pending review runs: `{benchmark_summary['pending_review_runs']}`")
    lines.append(f"- super brain resumes: `{benchmark_summary['super_brain_resumes']}`")
    lines.append(f"- error events: `{benchmark_summary['error_events']}`")
    lines.append("")
    lines.append("## Trading Journey Assessment")
    lines.append("")
    lines.append("This review follows a practical post-trade and trading-operations template built around:")
    lines.append("")
    lines.append("- trade lifecycle coverage: idea -> review -> risk gate -> transmit -> live broker exposure")
    lines.append("- execution-quality coverage: transmit attempts, successful transmissions, and observed broker acceptance")
    lines.append("- control coverage: pending-review handling, risk rejections, and operational error count")
    lines.append("- exposure coverage: what is currently open at the broker")
    lines.append("")
    lines.append("## Cycle Funnel")
    lines.append("")
    lines.append(f"- cycles observed in report window: `{cycle_funnel['total_cycles_observed']}`")
    lines.append(f"- cycles with pending review: `{cycle_funnel['cycles_with_pending_review']}`")
    lines.append(f"- cycles with transmit attempt: `{cycle_funnel['cycles_with_transmit_attempt']}`")
    lines.append(f"- cycles with transmit success: `{cycle_funnel['cycles_with_transmit_success']}`")
    lines.append(f"- cycles with error events: `{cycle_funnel['cycles_with_error_events']}`")
    lines.append("")
    lines.append("## Review Conversion")
    lines.append("")
    lines.append(f"- pending review runs: `{review_conversion['pending_review_runs']}`")
    lines.append(f"- resumed reviews: `{review_conversion['super_brain_resumes']}`")
    lines.append(f"- resume to pending ratio: `{review_conversion['resume_to_pending_ratio']}`")
    lines.append("")
    lines.append("## Forward Journal Outcomes")
    lines.append("")
    for outcome, count in sorted(report["journal_outcomes"].items()):
        lines.append(f"- `{outcome}`: `{count}`")
    lines.append("")
    lines.append("## Current Broker State")
    lines.append("")
    if mt5_state.get("checked") and mt5_state.get("authenticated"):
        details = mt5_state.get("platform_details") or {}
        lines.append(f"- authenticated: `true`")
        lines.append(f"- equity: `{details.get('equity', 'n/a')}`")
        lines.append(f"- active trades: `{details.get('active_trades', 'n/a')}`")
        lines.append(f"- pending orders: `{len(mt5_state.get('pending_orders', []))}`")
        lines.append(f"- open positions: `{len(mt5_state.get('open_positions', []))}`")
        for position in mt5_state.get("open_positions", []):
            lines.append(
                f"  - `{position['symbol']}` `{position['type']}` volume `{position['volume']}` open `{position['price_open']}` pnl `{position['profit']}`"
            )
    else:
        lines.append("- broker state could not be fully loaded")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append(f"- cycle engine activity: {report['interpretation']['cycle_engine_activity']}")
    lines.append(f"- execution quality: {report['interpretation']['execution_quality_assessment']}")
    lines.append(f"- risk gate behavior: {report['interpretation']['risk_gate_assessment']}")
    lines.append("")
    lines.append("## Missing Metrics")
    lines.append("")
    for item in report["interpretation"]["missing_metrics"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Recent Cycles")
    lines.append("")
    lines.append("| cycle_id | latest_decision | symbols | transmit_succeeded | pending_review | latest_event_at_utc |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for cycle in report["recent_cycles"][:15]:
        lines.append(
            f"| `{cycle['cycle_id']}` | `{cycle['latest_decision']}` | `{', '.join(cycle.get('symbols', []))}` | `{cycle['transmit_succeeded']}` | `{cycle['pending_review']}` | `{cycle['latest_event_at_utc']}` |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a TRADE_ORACLE trading-health report.")
    parser.add_argument("--env-file", default=".env.n8n.local", help="Env file to load before reading live state.")
    parser.add_argument("--cycle-limit", type=int, default=50, help="How many recent cycle summaries to include.")
    parser.add_argument("--journal-limit", type=int, default=100, help="How many forward-journal rows to include.")
    parser.add_argument("--json-output", default="", help="Optional path for JSON output.")
    parser.add_argument("--markdown-output", default="", help="Optional path for Markdown output.")
    args = parser.parse_args()

    report = collect_report(args.env_file, cycle_limit=max(1, args.cycle_limit), journal_limit=max(1, args.journal_limit))
    markdown = _render_markdown(report)

    if args.json_output:
        json_path = (REPO_ROOT / args.json_output).resolve()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.markdown_output:
        md_path = (REPO_ROOT / args.markdown_output).resolve()
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(markdown, encoding="utf-8")

    print(markdown)


if __name__ == "__main__":
    main()
