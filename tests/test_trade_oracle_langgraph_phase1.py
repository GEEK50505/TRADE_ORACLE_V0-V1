"""Focused tests for the TRADE_ORACLE LangGraph Phase 1 scaffold."""

import asyncio

from ai import trade_oracle_langgraph_phase1 as phase1


def _apply_state_patch(state, patch):
    merged = dict(state)
    additive_string_lists = {"messages", "audit_trail"}
    unique_string_lists = {"fundamental_catalysts", "completed_agents"}
    catalog_lists = {"tool_results", "specialist_reports", "errors"}

    for key, value in patch.items():
        if key in additive_string_lists:
            merged[key] = list(state.get(key, [])) + list(value)
        elif key in unique_string_lists:
            merged[key] = phase1.merge_unique_strings(state.get(key, []), value)
        elif key in catalog_lists:
            merged[key] = phase1.merge_catalog_rows(state.get(key, []), value)
        else:
            merged[key] = value
    return merged


def test_example_raw_setup_uses_final_3pair_context():
    raw_setup = phase1.example_raw_setup_from_final_3pair()

    assert raw_setup["asset_ticker"] == "AVAX/USDT"
    assert raw_setup["portfolio_expectancy"] == 1.0542
    assert raw_setup["portfolio_max_dd_pct"] == 2.9641
    assert raw_setup["portfolio_overall_survival"] is True
    assert len(raw_setup["candidate_portfolio"]) == 3
    assert raw_setup["account_state"]["current_balance"] == 5100.0


def test_build_initial_state_seeds_required_channels():
    state = phase1.build_initial_state(phase1.example_raw_setup_from_final_3pair())

    assert state["schema_version"] == "trade_oracle.phase1.v1"
    assert state["completed_agents"] == []
    assert state["fundamental_catalysts"] == []
    assert state["tool_results"] == []
    assert state["specialist_reports"] == []
    assert state["errors"] == []
    assert state["thread_metadata"]["architecture_phase"] == "phase_1"


def test_route_from_intent_router_handles_direct_gatekeeper_and_parallel_batch():
    base_state = phase1.build_initial_state(phase1.example_raw_setup_from_final_3pair())

    direct_state = dict(base_state)
    direct_state["route_plan"] = {
        "go_direct_to_gatekeeper": True,
        "required_batches": [],
    }
    assert phase1.route_from_intent_router(direct_state) == phase1.PYDANTIC_JSON_GATEKEEPER_NODE

    routed_state = dict(base_state)
    routed_state["route_plan"] = {
        "go_direct_to_gatekeeper": False,
        "required_batches": phase1.build_default_route_batches(),
    }
    routed_state["completed_agents"] = [phase1.MACRO_LIQUIDITY_ANALYST_NODE]
    assert phase1.route_from_intent_router(routed_state) == [
        phase1.FUNDAMENTAL_NARRATIVE_SPECIALIST_NODE,
        phase1.TOKENOMICS_AUDITOR_NODE,
        phase1.TECHNICAL_CONFLUENCE_VALIDATOR_NODE,
    ]


def test_phase1_nodes_produce_buy_decision_without_live_dependencies():
    raw_setup = phase1.example_raw_setup_from_final_3pair()
    state = phase1.build_initial_state(raw_setup)
    tool_stubs = phase1.build_mcp_tool_stubs()
    model_registry = phase1.TradeOracleModelRegistry(enable_live_llm=False)

    intent_router = phase1.make_intent_router_node(model_registry, include_reserved_specialist=False)
    macro = phase1.make_macro_liquidity_analyst_node(tool_stubs, model_registry)
    fundamental = phase1.make_fundamental_narrative_specialist_node(tool_stubs, model_registry)
    tokenomics = phase1.make_tokenomics_auditor_node(tool_stubs, model_registry)
    technical = phase1.make_technical_confluence_validator_node(tool_stubs, model_registry)
    devil = phase1.make_devils_advocate_node(model_registry)
    gatekeeper = phase1.make_pydantic_json_gatekeeper_node(tool_stubs, model_registry)

    state = _apply_state_patch(state, intent_router(state))
    assert phase1.route_from_intent_router(state) == phase1.MACRO_LIQUIDITY_ANALYST_NODE

    state = _apply_state_patch(state, macro(state))
    assert phase1.route_from_intent_router(state) == [
        phase1.FUNDAMENTAL_NARRATIVE_SPECIALIST_NODE,
        phase1.TOKENOMICS_AUDITOR_NODE,
        phase1.TECHNICAL_CONFLUENCE_VALIDATOR_NODE,
    ]

    state = _apply_state_patch(state, fundamental(state))
    state = _apply_state_patch(state, tokenomics(state))
    state = _apply_state_patch(state, technical(state))
    assert phase1.route_from_intent_router(state) == phase1.DEVILS_ADVOCATE_NODE

    state = _apply_state_patch(state, devil(state))
    state["human_decision"] = {"action": "APPROVE", "reviewer": "pytest", "notes": "phase1 smoke approval"}
    state = _apply_state_patch(state, gatekeeper(state))

    assert state["final_decision"]["decision"] == "BUY"
    assert state["final_decision"]["execution_status"] == "approved"
    assert state["execution_ready"] is True
    assert state["final_decision"]["risk_guardrails"]["can_open_new_trade"] is True
    assert state["final_decision"]["position_sizing"]["tokens"] > 0
    assert len(state["specialist_reports"]) >= 5


def test_phase1_macro_node_records_tool_errors_and_keeps_fallback_alive():
    class BrokenClient:
        def macro_snapshot(self, request):
            raise RuntimeError("macro endpoint unavailable")

        def fundamental_snapshot(self, request):
            raise RuntimeError("unused")

        def tokenomics_snapshot(self, request):
            raise RuntimeError("unused")

        def technical_snapshot(self, request):
            raise RuntimeError("unused")

        def risk_guardrails(self, request):
            raise RuntimeError("unused")

    raw_setup = phase1.example_raw_setup_from_final_3pair()
    state = phase1.build_initial_state(raw_setup)
    tool_stubs = phase1.build_mcp_tool_stubs(mcp_http_client=BrokenClient())
    model_registry = phase1.TradeOracleModelRegistry(enable_live_llm=False)
    macro = phase1.make_macro_liquidity_analyst_node(tool_stubs, model_registry)

    state = _apply_state_patch(state, macro(state))

    assert state["macro_score"] > 0.0
    assert state["tool_results"][0]["status"] == "error"
    assert state["errors"][0]["agent"] == phase1.MACRO_LIQUIDITY_ANALYST_NODE
    assert state["errors"][0]["tool_name"] == "macro_snapshot"


def test_phase1_specialists_use_tool_driven_summaries_when_tools_succeed():
    raw_setup = phase1.example_raw_setup_from_final_3pair()
    state = phase1.build_initial_state(raw_setup)
    tool_stubs = phase1.build_mcp_tool_stubs()
    model_registry = phase1.TradeOracleModelRegistry(enable_live_llm=False)

    macro = phase1.make_macro_liquidity_analyst_node(tool_stubs, model_registry)
    fundamental = phase1.make_fundamental_narrative_specialist_node(tool_stubs, model_registry)
    tokenomics = phase1.make_tokenomics_auditor_node(tool_stubs, model_registry)
    technical = phase1.make_technical_confluence_validator_node(tool_stubs, model_registry)

    state = _apply_state_patch(state, macro(state))
    state = _apply_state_patch(state, fundamental(state))
    state = _apply_state_patch(state, tokenomics(state))
    state = _apply_state_patch(state, technical(state))

    assert state["macro_summary"].startswith("Macro regime ")
    assert state["fundamental_summary"].startswith("Fundamental review ")
    assert state["tokenomics_summary"].startswith("Tokenomics review ")
    assert state["technical_summary"].startswith("Technical validation ")


def test_gatekeeper_downgrades_to_pass_when_risk_guardrails_block_trade():
    raw_setup = phase1.example_raw_setup_from_final_3pair()
    raw_setup["account_state"]["active_trades_count"] = 4

    state = phase1.build_initial_state(raw_setup)
    tool_stubs = phase1.build_mcp_tool_stubs()
    model_registry = phase1.TradeOracleModelRegistry(enable_live_llm=False)

    intent_router = phase1.make_intent_router_node(model_registry, include_reserved_specialist=False)
    macro = phase1.make_macro_liquidity_analyst_node(tool_stubs, model_registry)
    fundamental = phase1.make_fundamental_narrative_specialist_node(tool_stubs, model_registry)
    tokenomics = phase1.make_tokenomics_auditor_node(tool_stubs, model_registry)
    technical = phase1.make_technical_confluence_validator_node(tool_stubs, model_registry)
    devil = phase1.make_devils_advocate_node(model_registry)
    gatekeeper = phase1.make_pydantic_json_gatekeeper_node(tool_stubs, model_registry)

    state = _apply_state_patch(state, intent_router(state))
    state = _apply_state_patch(state, macro(state))
    state = _apply_state_patch(state, fundamental(state))
    state = _apply_state_patch(state, tokenomics(state))
    state = _apply_state_patch(state, technical(state))
    state = _apply_state_patch(state, devil(state))
    state = _apply_state_patch(state, gatekeeper(state))

    assert state["final_decision"]["decision"] == "BUY"
    assert state["final_decision"]["execution_status"] == "pass"
    assert state["execution_ready"] is False
    assert state["review_required"] is False
    assert state["risk_guardrails_result"]["result"]["can_open_new_trade"] is False


def test_hydrate_raw_setup_account_state_merges_match_trader_and_supabase_context():
    class FakePlatformClient:
        async def authenticate(self):
            return True

        async def get_platform_details(self):
            return {"equity": 5230.5, "active_trades": 2}

    class FakeStateManager:
        def update_high_watermark(self, current_equity):
            assert current_equity == 5230.5
            return 5300.0

    hydrated = asyncio.run(
        phase1.hydrate_raw_setup_account_state(
            phase1.example_raw_setup_from_final_3pair(),
            platform_state_client=FakePlatformClient(),
            state_manager=FakeStateManager(),
        )
    )

    assert hydrated["account_state"]["current_balance"] == 5230.5
    assert hydrated["account_state"]["highest_equity"] == 5300.0
    assert hydrated["account_state"]["active_trades_count"] == 2
    assert hydrated["account_state"]["source"] == "match_trader+supabase"
    assert hydrated["scanner_metadata"]["account_hydration_source"] == "match_trader+supabase"


def test_phase2_scanner_setup_to_raw_setup_maps_regime_and_records_inferred_fields():
    raw_setup = phase1.phase2_scanner_setup_to_raw_setup(
        {
            "symbol": "ETH/USDT",
            "regime": "BEARISH",
            "current_price": 2010.0,
            "atr": 125.5,
        }
    )

    assert raw_setup["asset_ticker"] == "ETH/USDT"
    assert raw_setup["setup_direction"] == "SELL"
    assert raw_setup["benchmark_regime_status"] == "RISK_OFF"
    assert raw_setup["localized_atr"] == 125.5
    assert raw_setup["scanner_metadata"]["source"] == "phase2_market_scanner"
    assert "fibonacci_convergence_proximity" in raw_setup["scanner_metadata"]["inferred_fields"]


def test_phase2_scanner_setup_to_raw_setup_preserves_richer_scanner_fields():
    raw_setup = phase1.phase2_scanner_setup_to_raw_setup(
        {
            "symbol": "SOL/USDT",
            "regime": "BULLISH",
            "current_price": 145.0,
            "atr": 9.25,
            "timeframe": "1d",
            "fibonacci_convergence_proximity": 0.011,
            "ema_cluster_distance": 0.007,
            "setup_quality": 0.88,
            "rationale": "Scanner supplied a high-quality bullish structural setup.",
            "narrative_tags": ["ema20_confirmed", "fib_confluence_strong"],
            "scanner_metadata": {"source": "phase2_market_scanner", "structural_bias": "relative_strength"},
        }
    )

    assert raw_setup["asset_ticker"] == "SOL/USDT"
    assert raw_setup["setup_direction"] == "BUY"
    assert raw_setup["fibonacci_convergence_proximity"] == 0.011
    assert raw_setup["ema_cluster_distance"] == 0.007
    assert raw_setup["setup_quality"] == 0.88
    assert raw_setup["rationale"] == "Scanner supplied a high-quality bullish structural setup."
    assert raw_setup["scanner_metadata"]["inferred_fields"] == []


def test_run_phase1_demo_from_scanner_supports_fake_scanner_and_hydration():
    class FakeScanner:
        async def run_scan(self):
            return [
                {
                    "symbol": "ETH/USDT",
                    "regime": "BEARISH",
                    "current_price": 2010.0,
                    "atr": 125.5,
                },
                {
                    "symbol": "SOL/USDT",
                    "regime": "BULLISH",
                    "current_price": 145.0,
                    "atr": 9.25,
                },
            ]

    class FakePlatformClient:
        async def authenticate(self):
            return True

        async def get_platform_details(self):
            return {"equity": 5200.0, "active_trades": 1}

    class FakeStateManager:
        def update_high_watermark(self, current_equity):
            assert current_equity == 5200.0
            return 5300.0

    selected_setup, first_pass, final_pass = phase1.run_phase1_demo_from_scanner(
        scanner=FakeScanner(),
        scanner_setup_index=1,
        hydrate_account_state=True,
        platform_state_client=FakePlatformClient(),
        state_manager=FakeStateManager(),
    )

    assert selected_setup["asset_ticker"] == "SOL/USDT"
    assert selected_setup["setup_direction"] == "BUY"
    assert selected_setup["account_state"]["current_balance"] == 5200.0
    assert "__interrupt__" in first_pass
    assert final_pass is not None
    assert final_pass["raw_setup"]["asset_ticker"] == "SOL/USDT"


def test_run_phase1_demo_supports_hydrated_account_state_with_injected_sources():
    class FakePlatformClient:
        async def authenticate(self):
            return True

        async def get_platform_details(self):
            return {"equity": 5225.0, "active_trades": 2}

    class FakeStateManager:
        def update_high_watermark(self, current_equity):
            assert current_equity == 5225.0
            return 5300.0

    first_pass, final_pass = phase1.run_phase1_demo(
        hydrate_account_state=True,
        platform_state_client=FakePlatformClient(),
        state_manager=FakeStateManager(),
    )

    assert "__interrupt__" in first_pass
    assert final_pass is not None
    assert final_pass["raw_setup"]["account_state"]["current_balance"] == 5225.0
    assert final_pass["raw_setup"]["account_state"]["highest_equity"] == 5300.0
    assert final_pass["raw_setup"]["account_state"]["active_trades_count"] == 2
    assert final_pass["raw_setup"]["scanner_metadata"]["account_hydration_source"] == "match_trader+supabase"


def test_build_review_payload_includes_audit_snapshot_context():
    state = phase1.build_initial_state(phase1.example_raw_setup_from_final_3pair())
    state["audit_trail"] = ["Intent Router completed.", "Macro-Liquidity Analyst completed."]
    state["completed_agents"] = [phase1.INTENT_ROUTER_NODE, phase1.MACRO_LIQUIDITY_ANALYST_NODE]
    state["errors"] = [{"agent": phase1.MACRO_LIQUIDITY_ANALYST_NODE, "tool_name": "macro_snapshot"}]
    state["tool_results"] = [{"tool_name": "macro_snapshot", "status": "ok"}]
    state["specialist_reports"] = [{"agent": phase1.MACRO_LIQUIDITY_ANALYST_NODE, "summary": "Macro regime risk_on"}]
    state["thread_metadata"] = {"source": "scanner", "architecture_phase": "phase_1"}

    payload = phase1._build_review_payload(
        state,
        phase1.FinalTradeDecision(
            decision="BUY",
            asset_ticker="AVAX/USDT",
            timeframe="4h",
            entry_context="Test review payload.",
            confidence=0.81,
            macro_score=0.8,
            fundamental_clearance=True,
            tokenomics_clearance=True,
            technical_validation={"is_valid": True},
            fundamental_catalysts=["trend_support"],
            adversarial_review="Watch volatility expansion.",
            risk_budget_usd=10.0,
            leverage_cap=2.0,
            consistency_rule_limit=0.20,
            risk_guardrails={"can_open_new_trade": True},
            position_sizing={"tokens": 1.23},
            execution_ready=True,
            execution_status="pending_human_review",
            operator_notes="",
        ),
    )

    assert payload["audit_snapshot"]["audit_trail"][0] == "Intent Router completed."
    assert payload["audit_snapshot"]["completed_agents"][0] == phase1.INTENT_ROUTER_NODE
    assert payload["audit_snapshot"]["errors"][0]["tool_name"] == "macro_snapshot"
