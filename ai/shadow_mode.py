"""
Phase 3 Shadow Mode — Live LLM inference running in strict counterfactual mode.

SHADOW_MODE_ENABLED = True means the LLM evaluates every market cycle but
decisions are NEVER transmitted to the MT5 execution engine. Results are written
to the forward journal under benchmark_variant='v1_live_llm_shadow' for MAE/MFE
tracking and A/B comparison against the v0 deterministic engine.

Rate-limit mitigation targets Google AI Studio 2026 quotas:
  - gemini-2.0-flash : 15 RPM free tier
  - gemini-2.5-flash : 10 RPM free tier
  Daemon cycle = 60 min → effectively 1 RPM. The 6.5-second inter-call
  cooldown ensures safety even in manual/stress-test runs.

SDK: uses google-genai (google.genai) — the current supported package.
The legacy google.generativeai package is deprecated as of mid-2025.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
import warnings
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Suppress any residual google SDK warnings at import time
# ---------------------------------------------------------------------------
warnings.filterwarnings("ignore", category=FutureWarning, module="google")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="google")
warnings.filterwarnings("ignore", message=".*google.generativeai.*", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*google.generativeai.*", category=DeprecationWarning)

logger = logging.getLogger("TRADE_ORACLE.ShadowMode")

# ---------------------------------------------------------------------------
# Module-level guard — flip to False to disable the entire shadow path
# ---------------------------------------------------------------------------
SHADOW_MODE_ENABLED: bool = (
    os.getenv("TRADE_ORACLE_SHADOW_MODE_ENABLED", "1").strip().lower()
    in {"1", "true", "yes", "y"}
)

# ---------------------------------------------------------------------------
# Rate-limit constants (overridable via env)
# ---------------------------------------------------------------------------
_COOLDOWN_SECONDS: float = float(
    os.getenv("TRADE_ORACLE_SHADOW_LLM_COOLDOWN_SECONDS", "6.5")
)
_MODEL_WORKER: str = os.getenv(
    "TRADE_ORACLE_SHADOW_LLM_MODEL_WORKER", "gemini-2.0-flash"
)
_MODEL_SYNTHESIS: str = os.getenv(
    "TRADE_ORACLE_SHADOW_LLM_MODEL_SYNTHESIS", "gemini-2.5-flash"
)
_CONFIDENCE_THRESHOLD: float = float(
    os.getenv("TRADE_ORACLE_SHADOW_LLM_CONFIDENCE_THRESHOLD", "0.75")
)
_MAX_RETRY_ATTEMPTS: int = 5
_RETRY_BASE_SECONDS: float = 2.0
_RETRY_JITTER_MAX_MS: float = 500.0


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ShadowDecision(BaseModel):
    """Structured decision emitted by the LLM for one shadow cycle."""

    model_config = ConfigDict(extra="allow")

    execute_trade: bool = False
    asset_ticker: str = ""
    direction: Literal["BUY", "SELL", "PASS"] = "PASS"
    conviction_score: float = Field(default=1.0, ge=1.0, le=10.0)
    entry_price: float = 0.0
    stop_loss: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    rationale: str = ""
    compliance_proof: str = ""


class ShadowCycleResult(BaseModel):
    """Full result of one shadow evaluation cycle."""

    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "shadow_trade",
        "shadow_no_trade",
        "shadow_error",
        "shadow_disabled",
        "shadow_no_candidates",
    ] = "shadow_no_trade"
    symbol: str = ""
    direction: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    entry_price: float = 0.0
    stop_loss: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    rationale: str = ""
    compliance_proof: str = ""
    model_used: str = ""
    latency_ms: float = 0.0
    raw_llm_output: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


# ---------------------------------------------------------------------------
# Rate-limited Gemini client
# ---------------------------------------------------------------------------

class RateLimitedGeminiClient:
    """
    Async wrapper around google.generativeai with:
      - asyncio.Lock-gated per-call cooldown (prevents >9 RPM even under stress)
      - Exponential backoff + jitter on HTTP 429
      - Dynamic model routing (worker bee vs. synthesis)
      - Batched prompt: ALL scanner candidates in ONE API call
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._lock = asyncio.Lock()
        self._last_call_at: float = 0.0

        try:
            from google import genai  # type: ignore[import]
            self._client = genai.Client(api_key=api_key)
        except ImportError as exc:
            raise ImportError(
                "google-genai is required for shadow mode. "
                "Install it with: pip install google-genai"
            ) from exc

    @staticmethod
    def _build_shadow_prompt(
        scanner_rows: list[dict[str, Any]],
        account_state: dict[str, Any],
    ) -> str:
        return (
            "Role: You are an elite cryptocurrency swing trading quant operating within "
            "a proprietary trading desk under strict Maven Trading risk rules.\n\n"
            "Mandate: Evaluate the provided market setups and select the single highest-"
            "probability trade. Respect all account constraints below.\n\n"
            "Account Parameters:\n"
            f"  Balance: ${account_state.get('current_balance', 10000):.2f}\n"
            f"  High Watermark: ${account_state.get('highest_equity', 10000):.2f}\n"
            f"  Active Trades: {account_state.get('active_trades_count', 0)}\n"
            "  Risk Per Trade: $10.00 (0.1% of $10,000)\n"
            "  Max Trailing Drawdown: 3% from watermark\n"
            "  Max Concurrent Trades: 4\n\n"
            "Analytical Rules:\n"
            "1. Reject any setup where fibonacci_convergence_proximity > 0.025 (price too far from Fib)\n"
            "2. Reject if ema_cluster_distance > 0.04 (price too extended from cluster)\n"
            "3. Stop-Loss = Entry \u00b1 (1.5 \u00d7 localized_atr)\n"
            "4. TP1 = Entry \u00b1 (2.0 \u00d7 localized_atr), TP2 = Entry \u00b1 (3.5 \u00d7 localized_atr)\n"
            "5. conviction_score MUST be between 1.0 and 10.0. If no trade, set to 1.0.\n\n"
            "Output: Return ONLY a single valid JSON object with these exact keys:\n"
            "{\n"
            '  "execute_trade": boolean,\n'
            '  "asset_ticker": string,\n'
            '  "direction": "BUY" | "SELL" | "PASS",\n'
            '  "conviction_score": float (1.0-10.0),\n'
            '  "entry_price": float,\n'
            '  "stop_loss": float,\n'
            '  "tp1": float,\n'
            '  "tp2": float,\n'
            '  "rationale": string (max 120 chars),\n'
            '  "compliance_proof": string (brief math proof)\n'
            "}\n"
            "No markdown, no preamble, no extra keys.\n\n"
            "Market Setups to evaluate (JSON array):\n"
            + json.dumps(scanner_rows, indent=2)
        )

    async def _call_with_backoff(
        self,
        model_name: str,
        prompt: str,
    ) -> tuple[str, float]:
        """
        Call Gemini via the google.genai client with exponential backoff on 429.
        Returns (raw_text, latency_ms).
        Raises on non-retryable errors or after exhausting retries.
        """
        from google.genai import types as genai_types  # type: ignore[import]
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRY_ATTEMPTS + 1):
            t0 = time.monotonic()
            try:
                response = await self._client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.15,
                    ),
                )
                latency_ms = (time.monotonic() - t0) * 1000
                return response.text, latency_ms
            except Exception as exc:
                last_exc = exc
                exc_str = str(exc).lower()
                is_429 = (
                    "429" in exc_str
                    or "quota" in exc_str
                    or "resource exhausted" in exc_str
                    or "rate limit" in exc_str
                )
                if not is_429 or attempt >= _MAX_RETRY_ATTEMPTS:
                    break
                jitter = random.uniform(0, _RETRY_JITTER_MAX_MS) / 1000.0
                delay = (_RETRY_BASE_SECONDS * (2 ** (attempt - 1))) + jitter
                logger.warning(
                    "[ShadowMode] 429 on %s (attempt %s/%s). Backing off %.2fs.",
                    model_name,
                    attempt,
                    _MAX_RETRY_ATTEMPTS,
                    delay,
                )
                await asyncio.sleep(delay)

        raise last_exc or RuntimeError(f"Gemini call failed after {_MAX_RETRY_ATTEMPTS} attempts")

    async def batch_evaluate(
        self,
        scanner_rows: list[dict[str, Any]],
        account_state: dict[str, Any],
        *,
        force_synthesis_model: bool = False,
    ) -> tuple[ShadowDecision, str, float]:
        """
        Pack all scanner candidates into one prompt and call Gemini once.

        Returns (ShadowDecision, model_name_used, latency_ms).
        The asyncio.Lock + cooldown guarantee ≤ 9 RPM regardless of caller cadence.
        """
        async with self._lock:
            # -- Cooldown enforcement --
            elapsed = time.monotonic() - self._last_call_at
            if elapsed < _COOLDOWN_SECONDS:
                await asyncio.sleep(_COOLDOWN_SECONDS - elapsed)

            model_name = _MODEL_SYNTHESIS if force_synthesis_model else _MODEL_WORKER
            prompt = self._build_shadow_prompt(scanner_rows, account_state)

            logger.info(
                "[ShadowMode] Calling %s with %s candidate(s).",
                model_name,
                len(scanner_rows),
            )
            raw_text, latency_ms = await self._call_with_backoff(model_name, prompt)
            self._last_call_at = time.monotonic()

        parsed = json.loads(raw_text)
        # Enforce conviction_score floor
        if isinstance(parsed.get("conviction_score"), (int, float)):
            if parsed["conviction_score"] < 1.0:
                parsed["conviction_score"] = 1.0
        decision = ShadowDecision(**parsed)
        return decision, model_name, latency_ms


# ---------------------------------------------------------------------------
# Shadow Mode Runner (injected into the daemon)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ShadowModeRunner:
    """
    Wraps RateLimitedGeminiClient and exposes run_shadow_cycle().
    Never raises — all exceptions are caught and returned as shadow_error status.
    """

    api_key: str
    _client: RateLimitedGeminiClient = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = RateLimitedGeminiClient(api_key=self.api_key)

    @staticmethod
    def _should_use_synthesis_model(
        primary_candidate_confidence: float,
    ) -> bool:
        """Route to gemini-2.5-flash only when the deterministic engine also likes the setup."""
        return primary_candidate_confidence >= _CONFIDENCE_THRESHOLD

    async def run_shadow_cycle(
        self,
        scanner_rows: list[dict[str, Any]],
        account_state: dict[str, Any],
        *,
        run_id: str = "",
        cycle_id: str = "",
        primary_candidate_confidence: float = 0.0,
    ) -> ShadowCycleResult:
        """
        Evaluate scanner candidates through the live LLM.
        NEVER transmits orders — always returns ShadowCycleResult.
        """
        if not SHADOW_MODE_ENABLED:
            return ShadowCycleResult(status="shadow_disabled")

        if not scanner_rows:
            logger.info("[ShadowMode] No scanner rows — skipping shadow cycle.")
            return ShadowCycleResult(status="shadow_no_candidates")

        force_synthesis = self._should_use_synthesis_model(primary_candidate_confidence)

        t0 = time.monotonic()
        try:
            decision, model_used, latency_ms = await self._client.batch_evaluate(
                scanner_rows,
                account_state,
                force_synthesis_model=force_synthesis,
            )
        except Exception as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.warning(
                "[ShadowMode] LLM call failed for cycle %s: %s",
                cycle_id,
                exc,
            )
            return ShadowCycleResult(
                status="shadow_error",
                model_used=_MODEL_SYNTHESIS if force_synthesis else _MODEL_WORKER,
                latency_ms=elapsed_ms,
                error=str(exc),
            )

        if not decision.execute_trade or decision.direction == "PASS":
            logger.info(
                "[ShadowMode] LLM verdict: no_trade (conviction=%.1f, model=%s, latency=%.0fms)",
                decision.conviction_score,
                model_used,
                latency_ms,
            )
            return ShadowCycleResult(
                status="shadow_no_trade",
                symbol=decision.asset_ticker,
                direction=decision.direction,
                confidence=min(decision.conviction_score / 10.0, 1.0),
                entry_price=decision.entry_price,
                stop_loss=decision.stop_loss,
                tp1=decision.tp1,
                tp2=decision.tp2,
                rationale=decision.rationale,
                compliance_proof=decision.compliance_proof,
                model_used=model_used,
                latency_ms=latency_ms,
                raw_llm_output=decision.model_dump(),
            )

        logger.info(
            "[ShadowMode] LLM verdict: SHADOW_TRADE %s %s @ %.6f "
            "(conviction=%.1f, sl=%.6f, tp1=%.6f, tp2=%.6f, model=%s, latency=%.0fms)",
            decision.direction,
            decision.asset_ticker,
            decision.entry_price,
            decision.conviction_score,
            decision.stop_loss,
            decision.tp1,
            decision.tp2,
            model_used,
            latency_ms,
        )
        return ShadowCycleResult(
            status="shadow_trade",
            symbol=decision.asset_ticker,
            direction=decision.direction,
            confidence=min(decision.conviction_score / 10.0, 1.0),
            entry_price=decision.entry_price,
            stop_loss=decision.stop_loss,
            tp1=decision.tp1,
            tp2=decision.tp2,
            rationale=decision.rationale,
            compliance_proof=decision.compliance_proof,
            model_used=model_used,
            latency_ms=latency_ms,
            raw_llm_output=decision.model_dump(),
        )


def build_shadow_mode_runner() -> ShadowModeRunner | None:
    """
    Build a ShadowModeRunner from environment settings.
    Returns None if shadow mode is disabled or GOOGLE_API_KEY is missing.
    """
    if not SHADOW_MODE_ENABLED:
        logger.info("[ShadowMode] SHADOW_MODE_ENABLED=False — shadow runner not built.")
        return None

    api_key = (os.getenv("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        logger.warning(
            "[ShadowMode] GOOGLE_API_KEY is not set. Shadow mode will be inactive."
        )
        return None

    try:
        runner = ShadowModeRunner(api_key=api_key)
        logger.info(
            "[ShadowMode] Runner initialised. Worker=%s, Synthesis=%s, Cooldown=%.1fs",
            _MODEL_WORKER,
            _MODEL_SYNTHESIS,
            _COOLDOWN_SECONDS,
        )
        return runner
    except Exception as exc:
        logger.error("[ShadowMode] Failed to initialise runner: %s", exc)
        return None


__all__ = [
    "SHADOW_MODE_ENABLED",
    "ShadowCycleResult",
    "ShadowDecision",
    "ShadowModeRunner",
    "RateLimitedGeminiClient",
    "build_shadow_mode_runner",
]
