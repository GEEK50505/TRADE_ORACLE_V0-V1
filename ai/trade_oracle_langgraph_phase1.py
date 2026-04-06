"""
Phase 1 LangGraph scaffold for the TRADE_ORACLE multi-agent supervisor graph.

Blueprint alignment:
- Blueprint Section 2: Best Overall Architecture
- Blueprint Section 2: State Schema and Graph Structure
- Blueprint Section 2: Human-in-the-Loop and Approval Mechanisms
- Blueprint Section 3: Detailed Agent Roles and Responsibilities
- Blueprint Section 5: Phase 1 Core Graph + Supervisor
- Blueprint Section 6: Pregel runtime, interrupt(), RetryPolicy, model tiering
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from operator import add
from pathlib import Path
from typing import Annotated, Any, Literal, NotRequired, TypedDict, cast

from pydantic import BaseModel, ConfigDict, Field

from config import settings

LOGGER = logging.getLogger("TRADE_ORACLE.LangGraph.Phase1")

ROOT_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT_DIR / "results"
DEFAULT_CHECKPOINTER_PATH = RESULTS_DIR / "trade_oracle_phase1.sqlite"

INTENT_ROUTER_NODE = "intent_router"
MACRO_LIQUIDITY_ANALYST_NODE = "macro_liquidity_analyst"
FUNDAMENTAL_NARRATIVE_SPECIALIST_NODE = "fundamental_narrative_specialist"
TOKENOMICS_AUDITOR_NODE = "tokenomics_auditor"
TECHNICAL_CONFLUENCE_VALIDATOR_NODE = "technical_confluence_validator"
DEVILS_ADVOCATE_NODE = "devils_advocate"
PYDANTIC_JSON_GATEKEEPER_NODE = "pydantic_json_gatekeeper"
RESERVED_SPECIALIST_NODE = "reserved_specialist_placeholder"


try:
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
    from langchain_core.runnables import RunnableConfig
    from langchain_core.tools import StructuredTool
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, RetryPolicy, interrupt
except ImportError as exc:  # pragma: no cover - exercised only before deps are installed
    AIMessage = None
    BaseMessage = Any
    Command = Any
    END = "__end__"
    HumanMessage = None
    RetryPolicy = None
    RunnableConfig = dict[str, Any]
    SqliteSaver = None
    START = "__start__"
    StateGraph = None
    StructuredTool = None
    SystemMessage = None
    interrupt = None
    LANGGRAPH_IMPORT_ERROR: Exception | None = exc
else:  # pragma: no cover - only active once deps are installed
    LANGGRAPH_IMPORT_ERROR = None


try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:  # pragma: no cover - exercised only before deps are installed
    ChatGoogleGenerativeAI = None


try:
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover - exercised only before deps are installed
    ChatOpenAI = None


def merge_unique_strings(left: list[str] | None, right: list[str] | None) -> list[str]:
    """Reducer for list-like state channels that must preserve order without duplicates."""
    merged: list[str] = list(left or [])
    for item in right or []:
        if item not in merged:
            merged.append(item)
    return merged


def merge_catalog_rows(
    left: list[dict[str, Any]] | None,
    right: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Reducer for structured tool results and error rows."""
    merged: list[dict[str, Any]] = list(left or [])
    for row in right or []:
        if row not in merged:
            merged.append(row)
    return merged


def ensure_langgraph_dependencies() -> None:
    """Fail fast with a useful install message when the LangGraph stack is absent."""
    if LANGGRAPH_IMPORT_ERROR is None:
        return
    raise ImportError(
        "TRADE_ORACLE Phase 1 requires the LangGraph stack. "
        "Install langgraph, langgraph-checkpoint-sqlite, langchain-core, "
        "langchain-openai, and langchain-google-genai before building the graph."
    ) from LANGGRAPH_IMPORT_ERROR


def as_message(role: Literal["system", "human", "ai"], content: str) -> Any:
    """Create a LangChain message when available, otherwise fall back to a plain dict."""
    role_to_cls = {
        "system": SystemMessage,
        "human": HumanMessage,
        "ai": AIMessage,
    }
    message_cls = role_to_cls[role]
    if message_cls is None:
        return {"role": role, "content": content}
    return message_cls(content=content)


class FinalPairContext(BaseModel):
    """Compact representation of one surviving pair from the realistic shortlist."""

    model_config = ConfigDict(extra="forbid")

    param_id: str
    long_symbol: str
    short_symbol: str
    timeframe: str = "4h"
    expectancy: float
    max_dd_pct: float
    overall_survival: bool


class ScannerRawSetup(BaseModel):
    """Scanner payload carried into the LangGraph thread."""

    model_config = ConfigDict(extra="allow")

    asset_ticker: str
    setup_direction: Literal["BUY", "SELL", "PASS"]
    timeframe: str
    benchmark_regime_status: str
    current_price: float
    localized_atr: float
    fibonacci_convergence_proximity: float
    ema_cluster_distance: float = Field(default=0.0)
    setup_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    narrative_tags: list[str] = Field(default_factory=list)
    candidate_portfolio: list[FinalPairContext] = Field(default_factory=list)
    portfolio_expectancy: float = 0.0
    portfolio_max_dd_pct: float = 0.0
    portfolio_consistency_score: float = 0.0
    portfolio_overall_survival: bool = False
    scanner_metadata: dict[str, Any] = Field(default_factory=dict)
    tokenomics_watch: dict[str, Any] = Field(default_factory=dict)


class IntentRouterPlan(BaseModel):
    """Structured output contract for the Supervisor / Intent Router."""

    model_config = ConfigDict(extra="forbid")

    route_reason: str
    required_batches: list[list[str]]
    go_direct_to_gatekeeper: bool = False
    risk_posture: Literal["risk_on", "risk_off", "neutral"] = "neutral"


class HumanReviewDecision(BaseModel):
    """Resume payload injected back into LangGraph after interrupt()."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["APPROVE", "REJECT", "HALT_SYSTEM"]
    reviewer: str = "human_operator"
    notes: str = ""


class FinalTradeDecision(BaseModel):
    """Terminal schema emitted by the Pydantic JSON Gatekeeper."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["BUY", "SELL", "PASS"]
    asset_ticker: str
    timeframe: str
    entry_context: str
    confidence: float = Field(ge=0.0, le=1.0)
    macro_score: float
    fundamental_clearance: bool
    tokenomics_clearance: bool
    technical_validation: dict[str, Any]
    fundamental_catalysts: list[str]
    adversarial_review: str
    risk_budget_usd: float
    leverage_cap: float
    consistency_rule_limit: float
    execution_ready: bool
    execution_status: Literal["pending_human_review", "approved", "rejected", "halted", "pass"]
    operator_notes: str = ""


class MacroLiquidityReport(BaseModel):
    """Typed output for the Macro-Liquidity Analyst."""

    model_config = ConfigDict(extra="forbid")

    macro_score: float = Field(ge=0.0, le=1.0)
    macro_regime: Literal["risk_on", "risk_off", "neutral"]
    veto_trade: bool = False
    macro_summary: str
    risk_flags: list[str] = Field(default_factory=list)


class FundamentalNarrativeReport(BaseModel):
    """Typed output for the Fundamental Narrative Specialist."""

    model_config = ConfigDict(extra="forbid")

    fundamental_clearance: bool
    fundamental_summary: str
    fundamental_catalysts: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


class TokenomicsAuditReport(BaseModel):
    """Typed output for the Tokenomics and On-Chain Auditor."""

    model_config = ConfigDict(extra="forbid")

    tokenomics_clearance: bool
    tokenomics_summary: str
    dilutive_event_within_days: int = 999
    major_unlock_flag: bool = False
    risk_flags: list[str] = Field(default_factory=list)


class TechnicalConfluenceReport(BaseModel):
    """Typed output for the Technical Confluence Validator."""

    model_config = ConfigDict(extra="forbid")

    technical_validation: dict[str, Any]
    technical_summary: str
    risk_flags: list[str] = Field(default_factory=list)


class DevilsAdvocateReport(BaseModel):
    """Typed output for the Devil's Advocate."""

    model_config = ConfigDict(extra="forbid")

    adversarial_review: str
    failure_modes: list[str] = Field(default_factory=list)
    confidence_dampener: float = Field(default=0.0, ge=0.0, le=1.0)


class ToolStubArgs(BaseModel):
    """Generic MCP tool input envelope for future FastAPI integration."""

    model_config = ConfigDict(extra="allow")

    asset_ticker: str
    timeframe: str = "4h"
    benchmark_regime_status: str = ""
    localized_atr: float = 0.0
    fibonacci_convergence_proximity: float = 0.0


class TradeState(TypedDict, total=False):
    """
    Shared state for the supervisor-led specialist graph.

    Blueprint Section 2 includes the exact core fields below. Additional fields are
    required by other blueprint sections for routing, HITL, error capture, and
    specialist outputs, so they are included in the full Phase 1 schema here.
    """

    # Blueprint Section 2 table: exact canonical channels.
    messages: Annotated[list[BaseMessage], add]
    raw_setup: dict[str, Any]
    macro_score: float
    fundamental_catalysts: Annotated[list[str], merge_unique_strings]
    tokenomics_clearance: bool
    adversarial_review: str
    final_decision: dict[str, Any]

    # Blueprint Sections 2-4: operational channels needed for routing and guardrails.
    audit_trail: Annotated[list[str], add]
    tool_results: Annotated[list[dict[str, Any]], merge_catalog_rows]
    specialist_reports: Annotated[list[dict[str, Any]], merge_catalog_rows]
    errors: Annotated[list[dict[str, Any]], merge_catalog_rows]
    completed_agents: Annotated[list[str], merge_unique_strings]
    route_plan: dict[str, Any]
    macro_summary: str
    fundamental_clearance: bool
    fundamental_summary: str
    tokenomics_summary: str
    technical_validation: dict[str, Any]
    technical_summary: str
    gatekeeper_status: str
    execution_ready: bool
    review_required: bool
    review_context: dict[str, Any]
    human_decision: dict[str, Any]
    halt_reason: str
    reserved_specialist_output: str
    schema_version: str
    thread_metadata: dict[str, Any]
    next_node_hint: str
    interrupt_payload: dict[str, Any]

    # Phase 1 optional scratchpads.
    last_model_provider: NotRequired[str]
    last_model_name: NotRequired[str]


@dataclass(slots=True)
class ModelEndpointConfig:
    """Declarative LLM endpoint mapping aligned with blueprint model tiering."""

    provider: Literal["google_ai_studio", "openrouter"]
    model: str
    api_key_env: str
    temperature: float = 0.0
    base_url: str | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class TradeOracleModelRegistry:
    """
    Lazy model factory.

    Blueprint Section 6 requires Gemini for routing / structured JSON and DeepSeek
    for higher-reasoning nodes such as the Macro analyst and Devil's Advocate.
    """

    enable_live_llm: bool = False
    gemini_router: ModelEndpointConfig = field(
        default_factory=lambda: ModelEndpointConfig(
            provider="google_ai_studio",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY",
            temperature=0.0,
        )
    )
    gemini_gatekeeper: ModelEndpointConfig = field(
        default_factory=lambda: ModelEndpointConfig(
            provider="google_ai_studio",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY",
            temperature=0.0,
        )
    )
    deepseek_reasoner: ModelEndpointConfig = field(
        default_factory=lambda: ModelEndpointConfig(
            provider="openrouter",
            model="deepseek/deepseek-r1",
            api_key_env="OPENROUTER_API_KEY",
            temperature=0.1,
            base_url="https://openrouter.ai/api/v1",
            extra_headers={
                "HTTP-Referer": os.getenv("TRADE_ORACLE_APP_URL", "https://trade-oracle.local"),
                "X-OpenRouter-Title": os.getenv("TRADE_ORACLE_APP_NAME", "TRADE_ORACLE"),
            },
        )
    )

    def build_gemini_structured_model(self, schema: type[BaseModel], gatekeeper: bool = False) -> Any | None:
        """Return a Gemini model constrained to the provided schema when available."""
        if not self.enable_live_llm or ChatGoogleGenerativeAI is None:
            return None
        endpoint = self.gemini_gatekeeper if gatekeeper else self.gemini_router
        api_key = os.getenv(endpoint.api_key_env)
        if not api_key:
            return None
        model = ChatGoogleGenerativeAI(
            model=endpoint.model,
            google_api_key=api_key,
            temperature=endpoint.temperature,
        )
        return model.with_structured_output(schema, method="json_schema")

    def build_deepseek_reasoner(self) -> Any | None:
        """Return the DeepSeek-over-OpenRouter chat model when available."""
        if not self.enable_live_llm or ChatOpenAI is None:
            return None
        endpoint = self.deepseek_reasoner
        api_key = os.getenv(endpoint.api_key_env)
        if not api_key:
            return None
        return ChatOpenAI(
            model=endpoint.model,
            api_key=api_key,
            base_url=endpoint.base_url,
            temperature=endpoint.temperature,
            default_headers=endpoint.extra_headers,
        )

    def build_deepseek_structured_model(self, schema: type[BaseModel]) -> Any | None:
        """Return a DeepSeek model constrained to a Pydantic schema when available."""
        model = self.build_deepseek_reasoner()
        if model is None:
            return None
        return model.with_structured_output(schema, method="json_schema")


def build_default_route_batches(include_reserved_specialist: bool = False) -> list[list[str]]:
    """
    Blueprint Section 2 requires deterministic routing with optional fanout.

    The middle batch is intentionally parallel-friendly for the Pregel runtime.
    """
    middle_batch = [
        FUNDAMENTAL_NARRATIVE_SPECIALIST_NODE,
        TOKENOMICS_AUDITOR_NODE,
        TECHNICAL_CONFLUENCE_VALIDATOR_NODE,
    ]
    if include_reserved_specialist:
        # The blueprint names six specialists but says there are seven.
        middle_batch.append(RESERVED_SPECIALIST_NODE)
    return [
        [MACRO_LIQUIDITY_ANALYST_NODE],
        middle_batch,
        [DEVILS_ADVOCATE_NODE],
    ]


def build_intent_router_prompt(setup: ScannerRawSetup) -> str:
    """Blueprint Section 3: central supervisor prompt contract."""
    return (
        "You are the TRADE_ORACLE Intent Router. Follow the supervisor-led specialist "
        "subgraph pattern exactly. Decide which specialist batch(es) are required, "
        "whether the setup should short-circuit to the Pydantic JSON Gatekeeper, and "
        "return only structured routing output.\n\n"
        f"{setup.model_dump_json(indent=2)}"
    )


def build_macro_prompt(setup: ScannerRawSetup, tool_result: dict[str, Any]) -> str:
    """Blueprint Section 3: Macro-Liquidity Analyst prompt contract."""
    return (
        "You are the TRADE_ORACLE Macro-Liquidity Analyst. Evaluate whether the setup "
        "direction is compatible with the present macro regime. Respect Maven-style "
        "capital preservation. Return only structured analysis.\n\n"
        f"SETUP:\n{setup.model_dump_json(indent=2)}\n\n"
        f"TOOL_CONTEXT:\n{json.dumps(tool_result, indent=2)}"
    )


def build_fundamental_prompt(setup: ScannerRawSetup, tool_result: dict[str, Any]) -> str:
    """Blueprint Section 3: Fundamental Narrative Specialist prompt contract."""
    return (
        "You are the TRADE_ORACLE Fundamental Narrative Specialist. Evaluate the target "
        "asset against current crypto narratives and flag any contradictory catalysts. "
        "Return only structured analysis.\n\n"
        f"SETUP:\n{setup.model_dump_json(indent=2)}\n\n"
        f"TOOL_CONTEXT:\n{json.dumps(tool_result, indent=2)}"
    )


def build_tokenomics_prompt(setup: ScannerRawSetup, tool_result: dict[str, Any]) -> str:
    """Blueprint Section 3: Tokenomics Auditor prompt contract."""
    return (
        "You are the TRADE_ORACLE Tokenomics and On-Chain Auditor. Evaluate unlock risk, "
        "supply-side dilution, and on-chain distribution danger for the holding window. "
        "Return only structured analysis.\n\n"
        f"SETUP:\n{setup.model_dump_json(indent=2)}\n\n"
        f"TOOL_CONTEXT:\n{json.dumps(tool_result, indent=2)}"
    )


def build_technical_prompt(setup: ScannerRawSetup, tool_result: dict[str, Any]) -> str:
    """Blueprint Section 3: Technical Confluence Validator prompt contract."""
    return (
        "You are the TRADE_ORACLE Technical Confluence Validator. Confirm EMA/Fibonacci "
        "alignment and ATR sanity without inventing data. Return only structured analysis.\n\n"
        f"SETUP:\n{setup.model_dump_json(indent=2)}\n\n"
        f"TOOL_CONTEXT:\n{json.dumps(tool_result, indent=2)}"
    )


def build_devils_advocate_prompt(state: TradeState) -> str:
    """Blueprint Section 3: Devil's Advocate prompt contract."""
    return (
        "You are the TRADE_ORACLE Devil's Advocate. Produce the strongest skeptical case "
        "against the setup, focusing on hidden liquidity traps, false positives, and "
        "drawdown risks. Return only structured analysis.\n\n"
        f"STATE:\n{json.dumps(_state_to_prompt_context(state), indent=2)}"
    )


def build_gatekeeper_prompt(state: TradeState) -> str:
    """Blueprint Section 3: Pydantic JSON Gatekeeper prompt contract."""
    return (
        "You are the TRADE_ORACLE Pydantic JSON Gatekeeper. You do not reason broadly; "
        "you only compress specialist output into the final strict decision schema. "
        "Return only structured output.\n\n"
        f"STATE:\n{json.dumps(_state_to_prompt_context(state), indent=2)}"
    )


def _report_row(agent_name: str, report: BaseModel) -> dict[str, Any]:
    """Normalize specialist reports for durable state logging."""
    return {
        "agent_name": agent_name,
        "report_type": report.__class__.__name__,
        "report": report.model_dump(),
    }


def _state_to_prompt_context(state: TradeState) -> dict[str, Any]:
    """Compact state slice for structured prompts."""
    return {
        "raw_setup": state.get("raw_setup", {}),
        "route_plan": state.get("route_plan", {}),
        "macro_score": state.get("macro_score"),
        "fundamental_clearance": state.get("fundamental_clearance"),
        "fundamental_catalysts": state.get("fundamental_catalysts", []),
        "tokenomics_clearance": state.get("tokenomics_clearance"),
        "technical_validation": state.get("technical_validation", {}),
        "adversarial_review": state.get("adversarial_review", ""),
        "specialist_reports": state.get("specialist_reports", []),
    }


def _deterministic_macro_report(setup: ScannerRawSetup) -> MacroLiquidityReport:
    benchmark = setup.benchmark_regime_status.upper()
    macro_regime: Literal["risk_on", "risk_off", "neutral"] = "neutral"
    macro_score = 0.55
    veto_trade = False
    risk_flags: list[str] = []
    if "RISK_ON" in benchmark or "BULL" in benchmark:
        macro_regime = "risk_on"
        macro_score = 0.82 if setup.setup_direction == "BUY" else 0.38
    elif "RISK_OFF" in benchmark or "BEAR" in benchmark:
        macro_regime = "risk_off"
        macro_score = 0.26 if setup.setup_direction == "BUY" else 0.74

    if macro_regime == "risk_off" and setup.setup_direction == "BUY":
        veto_trade = True
        risk_flags.append("Macro regime is risk-off against a long-biased setup.")

    return MacroLiquidityReport(
        macro_score=macro_score,
        macro_regime=macro_regime,
        veto_trade=veto_trade,
        macro_summary=(
            f"Macro placeholder: benchmark regime '{setup.benchmark_regime_status}' implies "
            f"macro_score={macro_score:.2f} for a {setup.setup_direction} bias."
        ),
        risk_flags=risk_flags,
    )


def _deterministic_fundamental_report(setup: ScannerRawSetup) -> FundamentalNarrativeReport:
    catalysts = list(setup.narrative_tags) or [
        "High-liquidity majors remain preferred under Maven-style execution constraints."
    ]
    risk_flags = [tag for tag in catalysts if "regulatory" in tag.lower()]
    fundamental_clearance = not bool(risk_flags)
    return FundamentalNarrativeReport(
        fundamental_clearance=fundamental_clearance,
        fundamental_summary=(
            f"Fundamental placeholder cleared={fundamental_clearance}. "
            f"Catalysts tracked: {', '.join(catalysts)}"
        ),
        fundamental_catalysts=catalysts,
        risk_flags=risk_flags,
    )


def _deterministic_tokenomics_report(setup: ScannerRawSetup) -> TokenomicsAuditReport:
    dilutive_days = int(setup.tokenomics_watch.get("dilutive_event_within_days", 999))
    major_unlock_flag = bool(setup.tokenomics_watch.get("major_unlock_flag", False))
    clearance = dilutive_days > 10 and not major_unlock_flag
    risk_flags: list[str] = []
    if major_unlock_flag:
        risk_flags.append("Major unlock flag detected in the holding window.")
    if dilutive_days <= 10:
        risk_flags.append("Dilutive event falls inside the intended swing window.")
    return TokenomicsAuditReport(
        tokenomics_clearance=clearance,
        tokenomics_summary=(
            f"Tokenomics placeholder clearance={clearance}. "
            f"Next dilutive-event window={dilutive_days} days."
        ),
        dilutive_event_within_days=dilutive_days,
        major_unlock_flag=major_unlock_flag,
        risk_flags=risk_flags,
    )


def _deterministic_technical_report(setup: ScannerRawSetup) -> TechnicalConfluenceReport:
    fib_ok = setup.fibonacci_convergence_proximity <= 0.02
    atr_ok = 0.0 < setup.localized_atr < max(setup.current_price * 0.08, 0.5)
    validation = {
        "is_valid": bool(fib_ok and atr_ok),
        "fib_ok": fib_ok,
        "atr_ok": atr_ok,
        "localized_atr": setup.localized_atr,
        "fibonacci_convergence_proximity": setup.fibonacci_convergence_proximity,
    }
    risk_flags: list[str] = []
    if not fib_ok:
        risk_flags.append("Fibonacci confluence is too weak.")
    if not atr_ok:
        risk_flags.append("ATR regime is outside the safe structural band.")
    return TechnicalConfluenceReport(
        technical_validation=validation,
        technical_summary=(
            f"Technical placeholder validation={validation['is_valid']} "
            f"(fib_ok={fib_ok}, atr_ok={atr_ok})."
        ),
        risk_flags=risk_flags,
    )


def _deterministic_devils_advocate_report(setup: ScannerRawSetup) -> DevilsAdvocateReport:
    failure_modes = [
        "Volatility expansion can overwhelm the $10 flat-risk budget.",
        "Same-family concentration may create hidden correlation even with pair diversity penalties.",
    ]
    return DevilsAdvocateReport(
        adversarial_review=(
            f"Devil's Advocate placeholder: even with shortlist expectancy "
            f"{setup.portfolio_expectancy:.4f}, the setup can still fail if volatility expands "
            f"faster than the $10 flat-risk buffer can absorb."
        ),
        failure_modes=failure_modes,
        confidence_dampener=0.15,
    )


def _tool_payload_from_setup(setup: ScannerRawSetup) -> dict[str, Any]:
    """Normalize scanner setup data into the common StructuredTool envelope."""
    return ToolStubArgs(
        asset_ticker=setup.asset_ticker,
        timeframe=setup.timeframe,
        benchmark_regime_status=setup.benchmark_regime_status,
        localized_atr=setup.localized_atr,
        fibonacci_convergence_proximity=setup.fibonacci_convergence_proximity,
    ).model_dump()


def _stub_macro_snapshot(**kwargs: Any) -> dict[str, Any]:
    return {
        "tool_name": "macro_snapshot",
        "status": "stub",
        "detail": "Phase 1 StructuredTool placeholder. Replace with FastAPI + MCP macro endpoint in Phase 3.",
        "payload": kwargs,
    }


def _stub_fundamental_snapshot(**kwargs: Any) -> dict[str, Any]:
    return {
        "tool_name": "fundamental_snapshot",
        "status": "stub",
        "detail": "Phase 1 StructuredTool placeholder. Replace with FastAPI + MCP fundamentals endpoint in Phase 3.",
        "payload": kwargs,
    }


def _stub_tokenomics_snapshot(**kwargs: Any) -> dict[str, Any]:
    return {
        "tool_name": "tokenomics_snapshot",
        "status": "stub",
        "detail": "Phase 1 StructuredTool placeholder. Replace with FastAPI + MCP tokenomics endpoint in Phase 3.",
        "payload": kwargs,
    }


def _stub_technical_snapshot(**kwargs: Any) -> dict[str, Any]:
    return {
        "tool_name": "technical_snapshot",
        "status": "stub",
        "detail": "Phase 1 StructuredTool placeholder. Replace with FastAPI + MCP technical endpoint in Phase 3.",
        "payload": kwargs,
    }


def _stub_risk_guardrails(**kwargs: Any) -> dict[str, Any]:
    return {
        "tool_name": "risk_guardrails",
        "status": "stub",
        "detail": "Phase 1 StructuredTool placeholder. Replace with FastAPI + MCP risk endpoint in Phase 3.",
        "payload": kwargs,
    }


def build_mcp_tool_stubs() -> dict[str, Any]:
    """Prepare StructuredTool wrappers without invoking any external Python scripts yet."""
    if StructuredTool is None:
        return {
            "macro_snapshot": _stub_macro_snapshot,
            "fundamental_snapshot": _stub_fundamental_snapshot,
            "tokenomics_snapshot": _stub_tokenomics_snapshot,
            "technical_snapshot": _stub_technical_snapshot,
            "risk_guardrails": _stub_risk_guardrails,
        }
    return {
        "macro_snapshot": StructuredTool.from_function(
            func=_stub_macro_snapshot,
            name="macro_snapshot",
            description="Future FastAPI + MCP entrypoint for macro-liquidity data.",
            args_schema=ToolStubArgs,
        ),
        "fundamental_snapshot": StructuredTool.from_function(
            func=_stub_fundamental_snapshot,
            name="fundamental_snapshot",
            description="Future FastAPI + MCP entrypoint for narrative and sentiment data.",
            args_schema=ToolStubArgs,
        ),
        "tokenomics_snapshot": StructuredTool.from_function(
            func=_stub_tokenomics_snapshot,
            name="tokenomics_snapshot",
            description="Future FastAPI + MCP entrypoint for token unlock and on-chain supply checks.",
            args_schema=ToolStubArgs,
        ),
        "technical_snapshot": StructuredTool.from_function(
            func=_stub_technical_snapshot,
            name="technical_snapshot",
            description="Future FastAPI + MCP entrypoint for technical confluence validation.",
            args_schema=ToolStubArgs,
        ),
        "risk_guardrails": StructuredTool.from_function(
            func=_stub_risk_guardrails,
            name="risk_guardrails",
            description="Future FastAPI + MCP entrypoint for deterministic risk and sizing audits.",
            args_schema=ToolStubArgs,
        ),
    }


def invoke_tool_stub(tool_stubs: dict[str, Any], name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Invoke a StructuredTool when available, otherwise call the plain stub function."""
    tool = tool_stubs[name]
    if hasattr(tool, "invoke"):
        return cast(dict[str, Any], tool.invoke(payload))
    return cast(dict[str, Any], tool(**payload))


def _trim_messages(messages: list[Any], keep_last: int = 12) -> list[Any]:
    """Blueprint Section 6 calls out aggressive message trimming for long-running graphs."""
    if len(messages) <= keep_last:
        return messages
    return messages[-keep_last:]


def _state_setup(state: TradeState) -> ScannerRawSetup:
    return ScannerRawSetup.model_validate(state.get("raw_setup", {}))


def _deterministic_route_plan(setup: ScannerRawSetup, include_reserved_specialist: bool) -> IntentRouterPlan:
    risk_posture = "neutral"
    benchmark = setup.benchmark_regime_status.upper()
    if "RISK_ON" in benchmark or "BULL" in benchmark:
        risk_posture = "risk_on"
    elif "RISK_OFF" in benchmark or "BEAR" in benchmark:
        risk_posture = "risk_off"

    go_direct = setup.setup_direction == "PASS"
    if setup.tokenomics_watch.get("force_pass", False):
        go_direct = True

    return IntentRouterPlan(
        route_reason="Deterministic Phase 1 routing plan derived from scanner context.",
        required_batches=[] if go_direct else build_default_route_batches(include_reserved_specialist=include_reserved_specialist),
        go_direct_to_gatekeeper=go_direct,
        risk_posture=cast(Literal["risk_on", "risk_off", "neutral"], risk_posture),
    )


def _build_review_payload(state: TradeState, final_decision: FinalTradeDecision) -> dict[str, Any]:
    setup = _state_setup(state)
    return {
        "review_type": "trade_authorization",
        "asset_ticker": setup.asset_ticker,
        "setup_direction": setup.setup_direction,
        "timeframe": setup.timeframe,
        "risk_budget_usd": settings.RISK_AMOUNT_USD,
        "macro_score": state.get("macro_score", 0.0),
        "adversarial_review": state.get("adversarial_review", ""),
        "final_decision": final_decision.model_dump(),
    }


def _normalize_resume_value(value: Any) -> HumanReviewDecision:
    if isinstance(value, bool):
        return HumanReviewDecision(action="APPROVE" if value else "REJECT")
    if isinstance(value, str):
        return HumanReviewDecision(action=value.upper())
    return HumanReviewDecision.model_validate(value)


def build_initial_state(raw_setup: dict[str, Any]) -> TradeState:
    """Convenience initializer for callers that want a fully seeded state payload."""
    validated_setup = ScannerRawSetup.model_validate(raw_setup)
    return TradeState(
        raw_setup=validated_setup.model_dump(),
        messages=[as_message("human", "Evaluate this scanner setup with the TRADE_ORACLE supervisor graph.")],
        audit_trail=["Thread initialized with raw scanner payload."],
        completed_agents=[],
        fundamental_catalysts=[],
        tool_results=[],
        specialist_reports=[],
        errors=[],
        schema_version="trade_oracle.phase1.v1",
        thread_metadata={"source": "scanner", "architecture_phase": "phase_1"},
    )


def make_intent_router_node(
    model_registry: TradeOracleModelRegistry,
    include_reserved_specialist: bool,
) -> Any:
    """Blueprint Section 3: Intent Router as the central supervisor."""

    def intent_router_node(state: TradeState, config: RunnableConfig | None = None) -> TradeState:
        setup = _state_setup(state)
        structured_model = model_registry.build_gemini_structured_model(IntentRouterPlan)
        plan: IntentRouterPlan | None = None
        if structured_model is not None:
            try:
                prompt = build_intent_router_prompt(setup)
                response = structured_model.invoke(prompt)
                plan = response if isinstance(response, IntentRouterPlan) else IntentRouterPlan.model_validate(response)
            except Exception as exc:  # pragma: no cover - requires live dependencies / credentials
                LOGGER.warning("Gemini routing fallback activated: %s", exc)
        if plan is None:
            plan = _deterministic_route_plan(setup, include_reserved_specialist=include_reserved_specialist)

        batches = plan.required_batches
        next_hint = PYDANTIC_JSON_GATEKEEPER_NODE
        if batches:
            next_hint = batches[0][0]

        return TradeState(
            route_plan=plan.model_dump(),
            next_node_hint=next_hint,
            gatekeeper_status="pending_specialist_analysis",
            audit_trail=[
                "Intent Router created the Phase 1 route plan.",
            ],
            messages=[
                as_message(
                    "ai",
                    f"Intent Router set risk posture={plan.risk_posture} and "
                    f"{len(plan.required_batches)} specialist batch(es).",
                )
            ],
            last_model_provider="google_ai_studio" if structured_model is not None else "deterministic_fallback",
            last_model_name=model_registry.gemini_router.model if structured_model is not None else "phase1_router_rules",
        )

    return intent_router_node


def make_macro_liquidity_analyst_node(tool_stubs: dict[str, Any], model_registry: TradeOracleModelRegistry) -> Any:
    """Blueprint Section 3: Macro-Liquidity Analyst."""

    def macro_liquidity_analyst_node(state: TradeState, config: RunnableConfig | None = None) -> TradeState:
        setup = _state_setup(state)
        tool_payload = _tool_payload_from_setup(setup)
        tool_result = invoke_tool_stub(tool_stubs, "macro_snapshot", tool_payload)
        report = _deterministic_macro_report(setup)

        structured_model = model_registry.build_deepseek_structured_model(MacroLiquidityReport)
        if structured_model is not None:
            try:
                prompt = build_macro_prompt(setup, tool_result)
                response = structured_model.invoke(prompt)
                report = response if isinstance(response, MacroLiquidityReport) else MacroLiquidityReport.model_validate(response)
            except Exception as exc:  # pragma: no cover - requires live dependencies / credentials
                LOGGER.warning("DeepSeek macro fallback activated: %s", exc)

        return TradeState(
            macro_score=report.macro_score,
            macro_summary=report.macro_summary,
            completed_agents=[MACRO_LIQUIDITY_ANALYST_NODE],
            tool_results=[tool_result],
            specialist_reports=[_report_row(MACRO_LIQUIDITY_ANALYST_NODE, report)],
            audit_trail=["Macro-Liquidity Analyst completed."],
            messages=[as_message("ai", report.macro_summary)],
            last_model_provider="openrouter" if structured_model is not None else "deterministic_fallback",
            last_model_name=model_registry.deepseek_reasoner.model if structured_model is not None else "macro_placeholder",
        )

    return macro_liquidity_analyst_node


def make_fundamental_narrative_specialist_node(
    tool_stubs: dict[str, Any],
    model_registry: TradeOracleModelRegistry,
) -> Any:
    """Blueprint Section 3: Fundamental Narrative Specialist."""

    def fundamental_narrative_specialist_node(state: TradeState, config: RunnableConfig | None = None) -> TradeState:
        setup = _state_setup(state)
        tool_payload = _tool_payload_from_setup(setup)
        tool_result = invoke_tool_stub(tool_stubs, "fundamental_snapshot", tool_payload)
        report = _deterministic_fundamental_report(setup)
        structured_model = model_registry.build_gemini_structured_model(FundamentalNarrativeReport)
        if structured_model is not None:
            try:
                prompt = build_fundamental_prompt(setup, tool_result)
                response = structured_model.invoke(prompt)
                report = response if isinstance(response, FundamentalNarrativeReport) else FundamentalNarrativeReport.model_validate(response)
            except Exception as exc:  # pragma: no cover - requires live dependencies / credentials
                LOGGER.warning("Gemini fundamental fallback activated: %s", exc)

        return TradeState(
            fundamental_clearance=report.fundamental_clearance,
            fundamental_catalysts=report.fundamental_catalysts,
            fundamental_summary=report.fundamental_summary,
            completed_agents=[FUNDAMENTAL_NARRATIVE_SPECIALIST_NODE],
            tool_results=[tool_result],
            specialist_reports=[_report_row(FUNDAMENTAL_NARRATIVE_SPECIALIST_NODE, report)],
            audit_trail=["Fundamental Narrative Specialist completed."],
            messages=[as_message("ai", report.fundamental_summary)],
            last_model_provider="google_ai_studio" if structured_model is not None else "deterministic_fallback",
            last_model_name=model_registry.gemini_router.model if structured_model is not None else "fundamental_placeholder",
        )

    return fundamental_narrative_specialist_node


def make_tokenomics_auditor_node(
    tool_stubs: dict[str, Any],
    model_registry: TradeOracleModelRegistry,
) -> Any:
    """Blueprint Section 3: Tokenomics and On-Chain Auditor."""

    def tokenomics_auditor_node(state: TradeState, config: RunnableConfig | None = None) -> TradeState:
        setup = _state_setup(state)
        tool_payload = _tool_payload_from_setup(setup)
        tool_result = invoke_tool_stub(tool_stubs, "tokenomics_snapshot", tool_payload)
        report = _deterministic_tokenomics_report(setup)
        structured_model = model_registry.build_gemini_structured_model(TokenomicsAuditReport)
        if structured_model is not None:
            try:
                prompt = build_tokenomics_prompt(setup, tool_result)
                response = structured_model.invoke(prompt)
                report = response if isinstance(response, TokenomicsAuditReport) else TokenomicsAuditReport.model_validate(response)
            except Exception as exc:  # pragma: no cover - requires live dependencies / credentials
                LOGGER.warning("Gemini tokenomics fallback activated: %s", exc)

        return TradeState(
            tokenomics_clearance=report.tokenomics_clearance,
            tokenomics_summary=report.tokenomics_summary,
            completed_agents=[TOKENOMICS_AUDITOR_NODE],
            tool_results=[tool_result],
            specialist_reports=[_report_row(TOKENOMICS_AUDITOR_NODE, report)],
            audit_trail=["Tokenomics Auditor completed."],
            messages=[as_message("ai", report.tokenomics_summary)],
            last_model_provider="google_ai_studio" if structured_model is not None else "deterministic_fallback",
            last_model_name=model_registry.gemini_router.model if structured_model is not None else "tokenomics_placeholder",
        )

    return tokenomics_auditor_node


def make_technical_confluence_validator_node(
    tool_stubs: dict[str, Any],
    model_registry: TradeOracleModelRegistry,
) -> Any:
    """Blueprint Section 3: Technical Confluence Validator."""

    def technical_confluence_validator_node(state: TradeState, config: RunnableConfig | None = None) -> TradeState:
        setup = _state_setup(state)
        tool_payload = _tool_payload_from_setup(setup)
        tool_result = invoke_tool_stub(tool_stubs, "technical_snapshot", tool_payload)
        report = _deterministic_technical_report(setup)
        structured_model = model_registry.build_gemini_structured_model(TechnicalConfluenceReport)
        if structured_model is not None:
            try:
                prompt = build_technical_prompt(setup, tool_result)
                response = structured_model.invoke(prompt)
                report = response if isinstance(response, TechnicalConfluenceReport) else TechnicalConfluenceReport.model_validate(response)
            except Exception as exc:  # pragma: no cover - requires live dependencies / credentials
                LOGGER.warning("Gemini technical fallback activated: %s", exc)

        return TradeState(
            technical_validation=report.technical_validation,
            technical_summary=report.technical_summary,
            completed_agents=[TECHNICAL_CONFLUENCE_VALIDATOR_NODE],
            tool_results=[tool_result],
            specialist_reports=[_report_row(TECHNICAL_CONFLUENCE_VALIDATOR_NODE, report)],
            audit_trail=["Technical Confluence Validator completed."],
            messages=[as_message("ai", report.technical_summary)],
            last_model_provider="google_ai_studio" if structured_model is not None else "deterministic_fallback",
            last_model_name=model_registry.gemini_router.model if structured_model is not None else "technical_placeholder",
        )

    return technical_confluence_validator_node


def make_devils_advocate_node(model_registry: TradeOracleModelRegistry) -> Any:
    """Blueprint Section 3: Devil's Advocate / Red Teamer."""

    def devils_advocate_node(state: TradeState, config: RunnableConfig | None = None) -> TradeState:
        setup = _state_setup(state)
        report = _deterministic_devils_advocate_report(setup)
        structured_model = model_registry.build_deepseek_structured_model(DevilsAdvocateReport)
        if structured_model is not None:
            try:
                prompt = build_devils_advocate_prompt(state)
                response = structured_model.invoke(prompt)
                report = response if isinstance(response, DevilsAdvocateReport) else DevilsAdvocateReport.model_validate(response)
            except Exception as exc:  # pragma: no cover - requires live dependencies / credentials
                LOGGER.warning("DeepSeek adversarial fallback activated: %s", exc)

        return TradeState(
            adversarial_review=report.adversarial_review,
            completed_agents=[DEVILS_ADVOCATE_NODE],
            specialist_reports=[_report_row(DEVILS_ADVOCATE_NODE, report)],
            audit_trail=["Devil's Advocate completed."],
            messages=[as_message("ai", report.adversarial_review)],
            last_model_provider="openrouter" if structured_model is not None else "deterministic_fallback",
            last_model_name=model_registry.deepseek_reasoner.model if structured_model is not None else "devils_advocate_placeholder",
        )

    return devils_advocate_node


def make_reserved_specialist_node() -> Any:
    """
    Blueprint count mismatch safeguard.

    The document states there are seven specialists but names six. This placeholder
    preserves a clean extension point without inventing undocumented behavior.
    """

    def reserved_specialist_node(state: TradeState, config: RunnableConfig | None = None) -> TradeState:
        return TradeState(
            reserved_specialist_output="Reserved specialist slot not yet specified in the blueprint.",
            completed_agents=[RESERVED_SPECIALIST_NODE],
            audit_trail=["Reserved Specialist Placeholder completed."],
            messages=[as_message("ai", "Reserved specialist placeholder executed without side effects.")],
        )

    return reserved_specialist_node


def make_pydantic_json_gatekeeper_node(model_registry: TradeOracleModelRegistry) -> Any:
    """Blueprint Section 3: terminal structured-output gatekeeper with interrupt()."""

    def pydantic_json_gatekeeper_node(state: TradeState, config: RunnableConfig | None = None) -> TradeState:
        setup = _state_setup(state)
        macro_score = float(state.get("macro_score", 0.0))
        fundamental_clearance = bool(state.get("fundamental_clearance", True))
        tokenomics_clearance = bool(state.get("tokenomics_clearance", True))
        technical_validation = cast(dict[str, Any], state.get("technical_validation", {"is_valid": False}))
        technical_ok = bool(technical_validation.get("is_valid", False))

        default_decision = "PASS"
        if (
            setup.setup_direction in {"BUY", "SELL"}
            and macro_score >= 0.55
            and fundamental_clearance
            and tokenomics_clearance
            and technical_ok
        ):
            default_decision = cast(Literal["BUY", "SELL", "PASS"], setup.setup_direction)

        deterministic_output = FinalTradeDecision(
            decision=cast(Literal["BUY", "SELL", "PASS"], default_decision),
            asset_ticker=setup.asset_ticker,
            timeframe=setup.timeframe,
            entry_context=setup.rationale or "Phase 1 placeholder context derived from scanner payload.",
            confidence=round(min(max((macro_score + (0.2 if technical_ok else 0.0)), 0.0), 1.0), 4),
            macro_score=macro_score,
            fundamental_clearance=fundamental_clearance,
            tokenomics_clearance=tokenomics_clearance,
            technical_validation=technical_validation,
            fundamental_catalysts=list(state.get("fundamental_catalysts", [])),
            adversarial_review=state.get("adversarial_review", ""),
            risk_budget_usd=settings.RISK_AMOUNT_USD,
            leverage_cap=settings.MAX_CRYPTO_LEVERAGE,
            consistency_rule_limit=0.20,
            execution_ready=default_decision in {"BUY", "SELL"},
            execution_status="pending_human_review" if default_decision in {"BUY", "SELL"} else "pass",
            operator_notes="",
        )

        structured_model = model_registry.build_gemini_structured_model(FinalTradeDecision, gatekeeper=True)
        final_output = deterministic_output
        if structured_model is not None:
            try:
                prompt = build_gatekeeper_prompt(state)
                response = structured_model.invoke(prompt)
                final_output = response if isinstance(response, FinalTradeDecision) else FinalTradeDecision.model_validate(response)
            except Exception as exc:  # pragma: no cover - requires live dependencies / credentials
                LOGGER.warning("Gemini gatekeeper fallback activated: %s", exc)

        human_decision_row: dict[str, Any] = {}
        interrupt_payload: dict[str, Any] = {}
        halt_reason = state.get("halt_reason", "")
        execution_ready = final_output.execution_ready
        execution_status = final_output.execution_status
        operator_notes = final_output.operator_notes

        if final_output.execution_ready:
            review_payload = _build_review_payload(state, final_output)
            interrupt_payload = review_payload
            if state.get("human_decision"):
                human_decision = HumanReviewDecision.model_validate(state["human_decision"])
            else:
                if interrupt is None:  # pragma: no cover - only triggered before langgraph install
                    raise RuntimeError("interrupt() is unavailable because LangGraph is not installed.")
                resumed_value = interrupt(review_payload)
                human_decision = _normalize_resume_value(resumed_value)
                human_decision_row = human_decision.model_dump()

            if human_decision.action == "APPROVE":
                execution_status = "approved"
                execution_ready = True
                operator_notes = human_decision.notes
                human_decision_row = human_decision.model_dump()
            elif human_decision.action == "HALT_SYSTEM":
                execution_status = "halted"
                execution_ready = False
                halt_reason = human_decision.notes or "Human operator halted the system."
                operator_notes = halt_reason
                human_decision_row = human_decision.model_dump()
            else:
                execution_status = "rejected"
                execution_ready = False
                operator_notes = human_decision.notes
                human_decision_row = human_decision.model_dump()

        finalized = final_output.model_copy(
            update={
                "execution_ready": execution_ready,
                "execution_status": execution_status,
                "operator_notes": operator_notes,
            }
        )

        return TradeState(
            final_decision=finalized.model_dump(),
            execution_ready=execution_ready,
            review_required=final_output.execution_ready,
            review_context=interrupt_payload,
            human_decision=human_decision_row,
            interrupt_payload=interrupt_payload,
            halt_reason=halt_reason,
            gatekeeper_status="finalized",
            audit_trail=["Pydantic JSON Gatekeeper completed."],
            messages=[as_message("ai", json.dumps(finalized.model_dump(), indent=2))],
            last_model_provider="google_ai_studio" if structured_model is not None else "deterministic_fallback",
            last_model_name=model_registry.gemini_gatekeeper.model if structured_model is not None else "gatekeeper_rules",
        )

    return pydantic_json_gatekeeper_node


def route_from_intent_router(state: TradeState) -> str | list[str]:
    """
    Conditional router used by add_conditional_edges.

    Blueprint Section 2 requires the Supervisor to decide whether to continue
    through specialist batches, short-circuit on tokenomics failure, or force the
    terminal gatekeeper.
    """
    route_plan = cast(dict[str, Any], state.get("route_plan", {}))
    if route_plan.get("go_direct_to_gatekeeper", False):
        return PYDANTIC_JSON_GATEKEEPER_NODE

    if state.get("tokenomics_clearance") is False:
        return PYDANTIC_JSON_GATEKEEPER_NODE

    completed = set(state.get("completed_agents", []))
    batches = cast(list[list[str]], route_plan.get("required_batches", []))
    for batch in batches:
        pending = [node for node in batch if node not in completed]
        if pending:
            return pending if len(pending) > 1 else pending[0]
    return PYDANTIC_JSON_GATEKEEPER_NODE


def build_trade_oracle_graph(
    checkpointer_path: str | Path = DEFAULT_CHECKPOINTER_PATH,
    *,
    enable_live_llm: bool = False,
    include_reserved_specialist: bool = False,
) -> Any:
    """
    Build and compile the Phase 1 supervisor graph with durable SQLite state.

    Blueprint Section 5 explicitly calls for a StateGraph, add_conditional_edges,
    dummy specialist nodes for payload traversal, and persistent memory.
    """
    ensure_langgraph_dependencies()

    sqlite_path = Path(checkpointer_path)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(sqlite_path), check_same_thread=False)
    checkpointer = SqliteSaver(connection)

    tool_stubs = build_mcp_tool_stubs()
    model_registry = TradeOracleModelRegistry(enable_live_llm=enable_live_llm)
    retry_policy = RetryPolicy(max_attempts=3) if RetryPolicy is not None else None

    graph_builder = StateGraph(TradeState)

    graph_builder.add_node(
        INTENT_ROUTER_NODE,
        make_intent_router_node(
            model_registry=model_registry,
            include_reserved_specialist=include_reserved_specialist,
        ),
    )
    graph_builder.add_node(
        MACRO_LIQUIDITY_ANALYST_NODE,
        make_macro_liquidity_analyst_node(tool_stubs, model_registry),
        retry_policy=retry_policy,
    )
    graph_builder.add_node(
        FUNDAMENTAL_NARRATIVE_SPECIALIST_NODE,
        make_fundamental_narrative_specialist_node(tool_stubs, model_registry),
        retry_policy=retry_policy,
    )
    graph_builder.add_node(
        TOKENOMICS_AUDITOR_NODE,
        make_tokenomics_auditor_node(tool_stubs, model_registry),
        retry_policy=retry_policy,
    )
    graph_builder.add_node(
        TECHNICAL_CONFLUENCE_VALIDATOR_NODE,
        make_technical_confluence_validator_node(tool_stubs, model_registry),
        retry_policy=retry_policy,
    )
    graph_builder.add_node(
        DEVILS_ADVOCATE_NODE,
        make_devils_advocate_node(model_registry),
        retry_policy=retry_policy,
    )
    graph_builder.add_node(
        PYDANTIC_JSON_GATEKEEPER_NODE,
        make_pydantic_json_gatekeeper_node(model_registry),
    )

    if include_reserved_specialist:
        graph_builder.add_node(RESERVED_SPECIALIST_NODE, make_reserved_specialist_node())

    graph_builder.add_edge(START, INTENT_ROUTER_NODE)
    graph_builder.add_conditional_edges(INTENT_ROUTER_NODE, route_from_intent_router)

    for specialist_node in [
        MACRO_LIQUIDITY_ANALYST_NODE,
        FUNDAMENTAL_NARRATIVE_SPECIALIST_NODE,
        TOKENOMICS_AUDITOR_NODE,
        TECHNICAL_CONFLUENCE_VALIDATOR_NODE,
        DEVILS_ADVOCATE_NODE,
    ]:
        graph_builder.add_edge(specialist_node, INTENT_ROUTER_NODE)

    if include_reserved_specialist:
        graph_builder.add_edge(RESERVED_SPECIALIST_NODE, INTENT_ROUTER_NODE)

    graph_builder.add_edge(PYDANTIC_JSON_GATEKEEPER_NODE, END)

    compiled_graph = graph_builder.compile(checkpointer=checkpointer)
    setattr(compiled_graph, "_trade_oracle_checkpointer_connection", connection)
    setattr(compiled_graph, "_trade_oracle_tool_stubs", tool_stubs)
    return compiled_graph


def example_raw_setup_from_final_3pair() -> dict[str, Any]:
    """
    Demo payload using the final realistic 3-pair survivor context from the repo.

    The shortlist came from results/backtrader_combined_final_shortlist_survivor.csv
    after the clean rerun that landed at expectancy=1.0542 and max_dd_pct=2.9641.
    """
    return ScannerRawSetup(
        asset_ticker="AVAX/USDT",
        setup_direction="BUY",
        timeframe="4h",
        benchmark_regime_status="RISK_ON",
        current_price=41.25,
        localized_atr=1.35,
        fibonacci_convergence_proximity=0.012,
        ema_cluster_distance=0.008,
        setup_quality=0.84,
        rationale="Final 3-pair realistic survivor context promoted into the LangGraph Phase 1 demo.",
        narrative_tags=["high_liquidity_major", "swing_trend_alignment", "maven_rule_survivor"],
        candidate_portfolio=[
            FinalPairContext(
                param_id="combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004",
                long_symbol="AVAX/USDT",
                short_symbol="DOGE/USDT",
                expectancy=1.0542,
                max_dd_pct=1.7764,
                overall_survival=True,
            ),
            FinalPairContext(
                param_id="combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004",
                long_symbol="AVAX/USDT",
                short_symbol="DOGE/USDT",
                expectancy=1.0542,
                max_dd_pct=2.0279,
                overall_survival=True,
            ),
            FinalPairContext(
                param_id="combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004",
                long_symbol="AVAX/USDT",
                short_symbol="DOGE/USDT",
                expectancy=1.0542,
                max_dd_pct=2.1053,
                overall_survival=True,
            ),
        ],
        portfolio_expectancy=1.0542,
        portfolio_max_dd_pct=2.9641,
        portfolio_consistency_score=3.8893,
        portfolio_overall_survival=True,
        scanner_metadata={
            "source": "scanner",
            "validation_context": "final_3pair_realistic_survivor",
            "baseline_friction": True,
            "same_symbol_same_side_stacking": True,
        },
        tokenomics_watch={"dilutive_event_within_days": 45, "major_unlock_flag": False},
    ).model_dump()


def run_phase1_demo(
    raw_setup: dict[str, Any] | None = None,
    *,
    checkpointer_path: str | Path = DEFAULT_CHECKPOINTER_PATH,
    enable_live_llm: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """
    Minimal demo runner for the Phase 1 graph.

    First invocation halts at the gatekeeper interrupt if the final decision is GO.
    The helper auto-resumes with APPROVE so the end-to-end path is easy to smoke test.
    """
    ensure_langgraph_dependencies()

    graph = build_trade_oracle_graph(
        checkpointer_path=checkpointer_path,
        enable_live_llm=enable_live_llm,
    )
    state = build_initial_state(raw_setup or example_raw_setup_from_final_3pair())
    config = {
        "configurable": {"thread_id": "trade-oracle-phase1-demo"},
        "max_concurrency": 3,
    }

    first_result = graph.invoke(state, config=config)
    final_result: dict[str, Any] | None = None
    if isinstance(first_result, dict) and first_result.get("__interrupt__"):
        final_result = graph.invoke(
            Command(resume={"action": "APPROVE", "reviewer": "demo_runner", "notes": "Demo approval"}),
            config=config,
        )
    return cast(dict[str, Any], first_result), cast(dict[str, Any] | None, final_result)


__all__ = [
    "TradeState",
    "FinalPairContext",
    "ScannerRawSetup",
    "IntentRouterPlan",
    "HumanReviewDecision",
    "FinalTradeDecision",
    "MacroLiquidityReport",
    "FundamentalNarrativeReport",
    "TokenomicsAuditReport",
    "TechnicalConfluenceReport",
    "DevilsAdvocateReport",
    "build_initial_state",
    "build_mcp_tool_stubs",
    "build_default_route_batches",
    "route_from_intent_router",
    "build_trade_oracle_graph",
    "example_raw_setup_from_final_3pair",
    "run_phase1_demo",
]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    try:
        first_pass, final_pass = run_phase1_demo()
        print("FIRST_PASS")
        print(json.dumps(first_pass, indent=2, default=str))
        if final_pass is not None:
            print("\nFINAL_PASS")
            print(json.dumps(final_pass, indent=2, default=str))
    except ImportError as exc:
        print(
            "LangGraph dependencies are not installed in this environment yet. "
            "Install the Phase 1 dependency stack, then rerun this module.\n"
            f"Details: {exc}"
        )
