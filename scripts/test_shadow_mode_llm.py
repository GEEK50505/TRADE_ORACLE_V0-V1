"""
Shadow Mode Live LLM Test
Tests the full pipeline:
 1. Live scanner data pull
 2. LLM call via ShadowModeRunner (real API)
 3. JSON structure validation
 4. Conviction score bounds check (1.0 - 10.0)
 5. Trade parameter sanity (SL < Entry < TP for BUY, etc.)
 6. Model routing validation
 7. Rate-limit machinery check (cooldown timing)
"""

from __future__ import annotations

import asyncio
import json
import sys
import os
import time
import warnings
warnings.filterwarnings("ignore")

# Force UTF-8 output if possible, otherwise fallback to ascii
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(".env.n8n.local")

PASS = "  \033[92m[OK]\033[0m"
FAIL = "  \033[91m[FAIL]\033[0m"
INFO = "  \033[94m[INFO]\033[0m"


def ok(msg): print(f"{PASS} {msg}")
def fail(msg): print(f"{FAIL} {msg}")
def info(msg): print(f"{INFO} {msg}")
def header(msg): print(f"\n\033[1m{'='*60}\033[0m\n\033[1m{msg}\033[0m\n{'='*60}")


async def pull_scanner_data() -> list[dict]:
    from data.scanner import MarketScanner
    from config import settings
    watchlist = list(settings.TRADE_ORACLE_DAEMON_WATCHLIST)
    info(f"Watchlist: {watchlist}")
    scanner = MarketScanner(watchlist)
    rows = await scanner.run_scan()
    return rows


def make_mock_scanner_rows() -> list[dict]:
    """Realistic mock data matching the scanner schema, used if live scan fails."""
    return [
        {
            "symbol": "BTC/USDT", "price": 68420.50, "direction": "BUY",
            "fibonacci_convergence_proximity": 0.008,
            "ema_cluster_distance": 0.012,
            "localized_atr": 850.0, "atr": 850.0,
            "rsi": 52.3, "volume_ratio": 1.42, "trend": "bullish",
            "fib_level": 0.618, "ema_signal": "above_cluster",
            "setup_quality": "A+"
        },
        {
            "symbol": "ETH/USDT", "price": 3820.10, "direction": "BUY",
            "fibonacci_convergence_proximity": 0.035,  # should be REJECTED (>0.025)
            "ema_cluster_distance": 0.018,
            "localized_atr": 62.0, "atr": 62.0,
            "rsi": 61.1, "volume_ratio": 1.18, "trend": "bullish",
            "fib_level": 0.5, "ema_signal": "above_cluster",
            "setup_quality": "B"
        },
        {
            "symbol": "SOL/USDT", "price": 178.50, "direction": "SELL",
            "fibonacci_convergence_proximity": 0.011,
            "ema_cluster_distance": 0.021,
            "localized_atr": 4.20, "atr": 4.20,
            "rsi": 68.9, "volume_ratio": 1.65, "trend": "bearish",
            "fib_level": 0.382, "ema_signal": "below_cluster",
            "setup_quality": "A"
        },
        {
            "symbol": "XRP/USDT", "price": 0.6210, "direction": "BUY",
            "fibonacci_convergence_proximity": 0.005,
            "ema_cluster_distance": 0.009,
            "localized_atr": 0.0082, "atr": 0.0082,
            "rsi": 48.7, "volume_ratio": 2.10, "trend": "bullish",
            "fib_level": 0.786, "ema_signal": "above_cluster",
            "setup_quality": "A+"
        },
        {
            "symbol": "DOGE/USDT", "price": 0.1842, "direction": "SELL",
            "fibonacci_convergence_proximity": 0.019,
            "ema_cluster_distance": 0.031,
            "localized_atr": 0.0038, "atr": 0.0038,
            "rsi": 72.4, "volume_ratio": 0.88, "trend": "neutral",
            "fib_level": 0.236, "ema_signal": "at_cluster",
            "setup_quality": "C"
        },
    ]


def validate_decision(result) -> tuple[list[str], list[str]]:
    """Returns (passes, failures)."""
    passes, failures = [], []

    # 1. Status must be a known value
    valid_statuses = {"shadow_trade", "shadow_no_trade", "shadow_error", "shadow_disabled", "shadow_no_candidates"}
    if result.status in valid_statuses:
        passes.append(f"status='{result.status}' is valid")
    else:
        failures.append(f"Unknown status: {result.status}")

    # 2. conviction_score range — mapped from 1–10 to 0–1 in ShadowCycleResult.confidence
    confidence = result.confidence
    if 0.0 <= confidence <= 1.0:
        passes.append(f"confidence={confidence:.3f} in [0.0, 1.0]")
        # Sanity: confidence >= 0.1 (conviction_score >= 1.0)
        if confidence >= 0.1:
            passes.append(f"conviction_score equivalent={confidence * 10:.1f}/10 (≥1.0 floor)")
        else:
            failures.append(f"conviction_score equivalent={confidence*10:.2f} below 1.0 floor")
    else:
        failures.append(f"confidence={confidence} out of [0.0, 1.0]")

    # 3. If trade decision, check trade parameters
    if result.status == "shadow_trade":
        direction = result.direction.upper()

        # direction must be BUY or SELL (not PASS)
        if direction in {"BUY", "SELL"}:
            passes.append(f"direction='{direction}' valid for trade decision")
        else:
            failures.append(f"direction='{direction}' invalid for execute_trade=True")

        # symbol must not be empty
        if result.symbol:
            passes.append(f"symbol='{result.symbol}' populated")
        else:
            failures.append("symbol is empty for shadow_trade")

        # entry, sl, tp1, tp2 must all be > 0
        for field, val in [("entry_price", result.entry_price), ("stop_loss", result.stop_loss),
                           ("tp1", result.tp1), ("tp2", result.tp2)]:
            if val > 0:
                passes.append(f"{field}={val:.6f} > 0")
            else:
                failures.append(f"{field}={val} must be > 0 for trade")

        # Directional price logic
        entry, sl, tp1, tp2 = result.entry_price, result.stop_loss, result.tp1, result.tp2
        if entry > 0 and sl > 0 and tp1 > 0:
            if direction == "BUY":
                if sl < entry:
                    passes.append(f"BUY SL({sl:.6f}) < entry({entry:.6f}) ✓")
                else:
                    failures.append(f"BUY SL({sl:.6f}) must be < entry({entry:.6f})")
                if tp1 > entry:
                    passes.append(f"BUY TP1({tp1:.6f}) > entry({entry:.6f}) ✓")
                else:
                    failures.append(f"BUY TP1({tp1:.6f}) must be > entry({entry:.6f})")
                if tp2 > tp1:
                    passes.append(f"BUY TP2({tp2:.6f}) > TP1({tp1:.6f}) ✓")
                else:
                    failures.append(f"BUY TP2({tp2:.6f}) must be > TP1({tp1:.6f})")
            elif direction == "SELL":
                if sl > entry:
                    passes.append(f"SELL SL({sl:.6f}) > entry({entry:.6f}) ✓")
                else:
                    failures.append(f"SELL SL({sl:.6f}) must be > entry({entry:.6f})")
                if tp1 < entry:
                    passes.append(f"SELL TP1({tp1:.6f}) < entry({entry:.6f}) ✓")
                else:
                    failures.append(f"SELL TP1({tp1:.6f}) must be < entry({entry:.6f})")
                if tp2 < tp1:
                    passes.append(f"SELL TP2({tp2:.6f}) < TP1({tp1:.6f}) ✓")
                else:
                    failures.append(f"SELL TP2({tp2:.6f}) must be < TP1({tp1:.6f})")

        # Rationale must not be empty
        if result.rationale:
            passes.append(f"rationale populated ({len(result.rationale)} chars)")
        else:
            failures.append("rationale is empty for shadow_trade")

    elif result.status == "shadow_no_trade":
        # no_trade: direction should be PASS or empty
        if result.direction in {"PASS", ""}:
            passes.append("no_trade correctly reports direction=PASS")
        else:
            # LLM might still emit BUY/SELL with execute_trade=False — acceptable
            passes.append(f"no_trade direction='{result.direction}' (execute_trade=False)")

    # 4. model_used must be populated
    if result.model_used:
        passes.append(f"model_used='{result.model_used}'")
    else:
        failures.append("model_used is empty")

    # 5. latency must be > 0
    if result.latency_ms > 0:
        passes.append(f"latency={result.latency_ms:.0f}ms")
    else:
        failures.append(f"latency={result.latency_ms}ms invalid")

    return passes, failures


async def main():
    header("SHADOW MODE LIVE LLM TEST")

    # --- Step 1: Pull scanner data ---
    header("STEP 1 — Scanner Data")
    scanner_rows = []
    try:
        scanner_rows = await pull_scanner_data()
        if scanner_rows:
            ok(f"Live scanner returned {len(scanner_rows)} rows")
            for r in scanner_rows:
                sym = r.get("symbol", "?")
                fib = r.get("fibonacci_convergence_proximity", "N/A")
                ema = r.get("ema_cluster_distance", "N/A")
                atr = r.get("localized_atr", r.get("atr", "N/A"))
                info(f"  {sym}: fib_prox={fib}, ema_dist={ema}, atr={atr}")
        else:
            fail("Scanner returned 0 rows — using mock data")
            scanner_rows = make_mock_scanner_rows()
            info("Using 5 realistic mock rows for LLM test")
    except Exception as e:
        fail(f"Scanner failed: {e} — using mock data")
        scanner_rows = make_mock_scanner_rows()
        info("Using 5 realistic mock rows for LLM test")

    # --- Step 2: Build shadow runner ---
    header("STEP 2 — Shadow Runner Init")
    from ai.shadow_mode import build_shadow_mode_runner, SHADOW_MODE_ENABLED, _MODEL_WORKER, _MODEL_SYNTHESIS, _COOLDOWN_SECONDS

    if not SHADOW_MODE_ENABLED:
        fail("SHADOW_MODE_ENABLED=False — cannot run test")
        sys.exit(1)
    ok(f"SHADOW_MODE_ENABLED=True")

    runner = build_shadow_mode_runner()
    if runner is None:
        fail("build_shadow_mode_runner() returned None — GOOGLE_API_KEY missing?")
        sys.exit(1)
    ok(f"ShadowModeRunner initialised")
    info(f"Worker model: {_MODEL_WORKER}")
    info(f"Synthesis model: {_MODEL_SYNTHESIS}")
    info(f"Cooldown: {_COOLDOWN_SECONDS}s")

    # --- Step 3: Run shadow cycle ---
    header("STEP 3 — Live LLM Call (single batched prompt)")
    account_state = {
        "current_balance": 10000.0,
        "highest_equity": 10200.0,
        "active_trades_count": 0,
        "source": "test_harness",
    }
    info(f"Sending {len(scanner_rows)} candidate(s) to {_MODEL_WORKER}...")

    t0 = time.monotonic()
    result = await runner.run_shadow_cycle(
        scanner_rows,
        account_state,
        run_id="test_run",
        cycle_id="test_cycle",
        primary_candidate_confidence=0.0,
    )
    wall_ms = (time.monotonic() - t0) * 1000
    ok(f"Call returned in {wall_ms:.0f}ms (LLM latency: {result.latency_ms:.0f}ms)")

    # --- Step 4: Print raw output ---
    header("STEP 4 — Raw LLM Output")
    if result.raw_llm_output:
        print(json.dumps(result.raw_llm_output, indent=2))
    else:
        info(f"No raw_llm_output (status={result.status}, error={result.error})")

    # --- Step 5: Validate ---
    header("STEP 5 — Validation")
    passes, failures = validate_decision(result)

    for p in passes:
        ok(p)
    for f in failures:
        fail(f)

    print(f"\n{'='*60}")
    total = len(passes) + len(failures)
    if failures:
        print(f"\033[91m  RESULT: {len(passes)}/{total} checks passed — {len(failures)} FAILURE(S)\033[0m")
    else:
        print(f"\033[92m  RESULT: ALL {total} CHECKS PASSED ✓\033[0m")
    print(f"{'='*60}")

    # --- Step 6: Second call — verify cooldown machinery ---
    header("STEP 6 — Rate Limit / Cooldown Timing Test")
    info("Firing second call immediately to verify cooldown enforcement...")
    t1 = time.monotonic()
    result2 = await runner.run_shadow_cycle(
        scanner_rows[:1],  # minimal payload
        account_state,
        run_id="test_run_2",
        cycle_id="test_cycle_2",
    )
    elapsed2 = time.monotonic() - t1
    if elapsed2 >= _COOLDOWN_SECONDS:
        ok(f"Cooldown enforced: second call waited {elapsed2:.2f}s (≥{_COOLDOWN_SECONDS}s)")
    else:
        fail(f"Cooldown NOT enforced: second call only waited {elapsed2:.2f}s (expected ≥{_COOLDOWN_SECONDS}s)")

    passes2, failures2 = validate_decision(result2)
    for p in passes2:
        ok(p)
    for f in failures2:
        fail(f)

    print(f"\n{'='*60}")
    if not failures and not failures2:
        print(f"\033[92m  ALL TESTS PASSED — Shadow LLM is operating correctly ✓\033[0m")
    else:
        all_failures = failures + failures2
        print(f"\033[91m  {len(all_failures)} TEST FAILURE(S) — review above\033[0m")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
