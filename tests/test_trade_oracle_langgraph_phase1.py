"""Focused tests for the TRADE_ORACLE LangGraph Phase 1 scaffold."""

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
    gatekeeper = phase1.make_pydantic_json_gatekeeper_node(model_registry)

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
    assert len(state["specialist_reports"]) >= 5
