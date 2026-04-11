"""Tests for the Phase 3 FastAPI MCP scaffold and HTTP tool adapter."""

from fastapi.testclient import TestClient

from ai import trade_oracle_langgraph_phase1 as phase1
from api.trade_oracle_mcp_service import (
    MCPAnalysisRequest,
    TradeOracleBinancePublicProvider,
    TradeOracleCoinGeckoProvider,
    TradeOracleExternalSpecialistClient,
    TradeOracleSpecialistProviderRegistry,
    RiskGuardrailsRequest,
    TradeOracleMCPServiceError,
    build_trade_oracle_mcp_app,
    build_trade_oracle_mcp_http_tools,
)


def test_trade_oracle_mcp_service_health_and_macro_endpoint():
    app = build_trade_oracle_mcp_app(require_auth=False)
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    payload = MCPAnalysisRequest(
        asset_ticker="AVAX/USDT",
        timeframe="4h",
        benchmark_regime_status="RISK_ON",
        localized_atr=1.35,
        fibonacci_convergence_proximity=0.012,
        current_price=41.25,
        setup_direction="BUY",
    ).model_dump()
    response = client.post("/mcp/macro-snapshot", json=payload)
    body = response.json()

    assert response.status_code == 200
    assert body["tool_name"] == "macro_snapshot"
    assert body["status"] == "ok"
    assert body["result"]["macro_regime"] == "risk_on"
    assert body["result"]["macro_score"] >= 0.8
    assert "supporting_factors" in body["result"]
    assert body["result"]["provider_info"]["selected_provider"] == "internal_context_adapter"
    assert body["meta"]["request_id"]
    assert body["meta"]["path"] == "/mcp/macro-snapshot"


def test_trade_oracle_mcp_service_provider_status_endpoint_reports_modes():
    registry = TradeOracleSpecialistProviderRegistry(
        macro_mode="hybrid",
        macro_url="https://macro.example.test",
        fundamental_mode="internal",
        tokenomics_mode="internal",
        technical_mode="external",
        technical_url="https://technical.example.test",
    )
    app = build_trade_oracle_mcp_app(require_auth=False, provider_registry=registry)
    client = TestClient(app)

    response = client.get("/mcp/providers/status")
    body = response.json()

    assert response.status_code == 200
    assert body["service"] == "trade_oracle_mcp"
    assert body["providers"]["macro_snapshot"]["mode"] == "hybrid"
    assert body["providers"]["macro_snapshot"]["external_url_configured"] is True
    assert body["providers"]["macro_snapshot"]["provider_name"] == "external_http_provider"
    assert body["providers"]["technical_snapshot"]["mode"] == "external"
    assert body["providers"]["technical_snapshot"]["provider_name"] == "external_http_provider"


def test_trade_oracle_mcp_service_risk_guardrails_endpoint():
    app = build_trade_oracle_mcp_app(require_auth=False)
    client = TestClient(app)

    payload = RiskGuardrailsRequest(
        current_balance=5100.0,
        highest_equity=5150.0,
        active_trades_count=1,
        entry_price=41.25,
        atr=1.35,
        direction="LONG",
    ).model_dump()
    response = client.post("/mcp/risk-guardrails", json=payload)
    body = response.json()

    assert response.status_code == 200
    assert body["tool_name"] == "risk_guardrails"
    assert body["status"] == "ok"
    assert body["result"]["can_open_new_trade"] is True
    assert body["result"]["position_size"] is not None


def test_trade_oracle_mcp_service_technical_endpoint_uses_richer_scanner_context():
    app = build_trade_oracle_mcp_app(require_auth=False)
    client = TestClient(app)

    payload = MCPAnalysisRequest(
        asset_ticker="SOL/USDT",
        timeframe="1d",
        benchmark_regime_status="RISK_ON",
        localized_atr=9.25,
        fibonacci_convergence_proximity=0.011,
        current_price=145.0,
        setup_direction="BUY",
        narrative_tags=["scanner_structural_confluence", "fib_confluence_strong"],
        extra_context={
            "setup_quality": 0.88,
            "ema_cluster_distance": 0.007,
            "scanner_metadata": {
                "ema_confirmed": True,
                "sma_confirmed": True,
                "structural_bias": "relative_strength",
            },
        },
    ).model_dump()

    response = client.post("/mcp/technical-snapshot", json=payload)
    body = response.json()

    assert response.status_code == 200
    assert body["tool_name"] == "technical_snapshot"
    assert body["result"]["is_valid"] is True
    assert body["result"]["ema_ok"] is True
    assert body["result"]["setup_quality"] == 0.88


def test_trade_oracle_mcp_service_fundamental_endpoint_flags_bias_conflict():
    app = build_trade_oracle_mcp_app(require_auth=False)
    client = TestClient(app)

    payload = MCPAnalysisRequest(
        asset_ticker="ETH/USDT",
        timeframe="1d",
        benchmark_regime_status="RISK_ON",
        localized_atr=12.0,
        fibonacci_convergence_proximity=0.015,
        current_price=2010.0,
        setup_direction="BUY",
        narrative_tags=["scanner_structural_confluence"],
        extra_context={
            "setup_quality": 0.52,
            "portfolio_overall_survival": True,
            "scanner_metadata": {
                "structural_bias": "relative_weakness",
            },
        },
    ).model_dump()

    response = client.post("/mcp/fundamental-snapshot", json=payload)
    body = response.json()

    assert response.status_code == 200
    assert body["tool_name"] == "fundamental_snapshot"
    assert body["result"]["fundamental_clearance"] is False
    assert any("long bias" in flag.lower() for flag in body["result"]["risk_flags"])


def test_trade_oracle_mcp_service_hybrid_provider_falls_back_to_internal_snapshot():
    class BrokenExternalClient(TradeOracleExternalSpecialistClient):
        def request_snapshot(self, *, url, payload, tool_name):
            raise RuntimeError("provider unavailable")

    registry = TradeOracleSpecialistProviderRegistry(
        macro_mode="hybrid",
        macro_url="https://macro.example.test",
        external_client=BrokenExternalClient(),
    )
    app = build_trade_oracle_mcp_app(require_auth=False, provider_registry=registry)
    client = TestClient(app)

    payload = MCPAnalysisRequest(
        asset_ticker="AVAX/USDT",
        timeframe="4h",
        benchmark_regime_status="RISK_ON",
        localized_atr=1.35,
        fibonacci_convergence_proximity=0.012,
        current_price=41.25,
        setup_direction="BUY",
    ).model_dump()
    response = client.post("/mcp/macro-snapshot", json=payload)
    body = response.json()

    assert response.status_code == 200
    assert body["result"]["macro_regime"] == "risk_on"
    assert body["result"]["provider_info"]["fallback_used"] is True
    assert body["result"]["provider_info"]["selected_provider"] == "internal_context_adapter"


def test_trade_oracle_mcp_service_external_provider_can_supply_snapshot():
    class FakeExternalClient(TradeOracleExternalSpecialistClient):
        def request_snapshot(self, *, url, payload, tool_name):
            return {
                "status": "ok",
                "detail": "External provider returned macro snapshot.",
                "result": {
                    "macro_regime": "risk_on",
                    "macro_score": 0.91,
                    "veto_trade": False,
                    "supporting_factors": ["external_macro_feed"],
                    "risk_flags": [],
                },
            }

    registry = TradeOracleSpecialistProviderRegistry(
        macro_mode="external",
        macro_url="https://macro.example.test",
        external_client=FakeExternalClient(),
    )
    app = build_trade_oracle_mcp_app(require_auth=False, provider_registry=registry)
    client = TestClient(app)

    payload = MCPAnalysisRequest(
        asset_ticker="AVAX/USDT",
        timeframe="4h",
        benchmark_regime_status="RISK_ON",
        localized_atr=1.35,
        fibonacci_convergence_proximity=0.012,
        current_price=41.25,
        setup_direction="BUY",
    ).model_dump()
    response = client.post("/mcp/macro-snapshot", json=payload)
    body = response.json()

    assert response.status_code == 200
    assert body["result"]["macro_score"] == 0.91
    assert body["result"]["provider_info"]["selected_provider"] == "external_http_provider"
    assert body["result"]["provider_info"]["fallback_used"] is False


def test_trade_oracle_mcp_service_coingecko_provider_can_supply_snapshot_without_custom_url():
    class FakeResponse:
        def __init__(self, body, status_code=200):
            self._body = body
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        def json(self):
            return self._body

    class FakeCoinGeckoClient:
        def get(self, url, params=None, headers=None):
            if url.endswith("/coins/markets"):
                return FakeResponse(
                    [
                        {
                            "market_cap_rank": 4,
                            "price_change_percentage_24h": 3.2,
                            "total_volume": 25000000000,
                            "market_cap": 300000000000,
                        }
                    ]
                )
            if url.endswith("/global"):
                return FakeResponse(
                    {
                        "data": {
                            "market_cap_change_percentage_24h_usd": 1.8,
                            "market_cap_percentage": {"btc": 54.2},
                        }
                    }
                )
            raise AssertionError(f"Unexpected URL {url}")

    registry = TradeOracleSpecialistProviderRegistry(
        macro_mode="external",
        macro_provider="coingecko",
        coingecko_provider=TradeOracleCoinGeckoProvider(
            base_url="https://api.coingecko.test/api/v3",
            client=FakeCoinGeckoClient(),
        ),
    )
    app = build_trade_oracle_mcp_app(require_auth=False, provider_registry=registry)
    client = TestClient(app)

    payload = MCPAnalysisRequest(
        asset_ticker="ETH/USDT",
        timeframe="4h",
        benchmark_regime_status="RISK_ON",
        localized_atr=55.0,
        fibonacci_convergence_proximity=0.01,
        current_price=3200.0,
        setup_direction="BUY",
    ).model_dump()
    response = client.post("/mcp/macro-snapshot", json=payload)
    body = response.json()

    assert response.status_code == 200
    assert body["result"]["macro_regime"] == "risk_on"
    assert body["result"]["provider_info"]["selected_provider"] == "coingecko"
    assert body["result"]["provider_info"]["fallback_used"] is False


def test_trade_oracle_mcp_service_binance_public_provider_can_supply_snapshot_without_custom_url():
    class FakeResponse:
        def __init__(self, body, status_code=200):
            self._body = body
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        def json(self):
            return self._body

    class FakeBinanceClient:
        def get(self, url, params=None, headers=None):
            if not url.endswith("/api/v3/klines"):
                raise AssertionError(f"Unexpected URL {url}")
            klines = []
            for index in range(120):
                close = 100.0 + (index * 0.25)
                high = close + 1.0
                low = close - 1.0
                open_price = close - 0.4
                klines.append([index, str(open_price), str(high), str(low), str(close), "1000"])
            return FakeResponse(klines)

    registry = TradeOracleSpecialistProviderRegistry(
        technical_mode="external",
        technical_provider="binance_public",
        binance_provider=TradeOracleBinancePublicProvider(
            base_url="https://api.binance.test",
            client=FakeBinanceClient(),
        ),
    )
    app = build_trade_oracle_mcp_app(require_auth=False, provider_registry=registry)
    client = TestClient(app)

    payload = MCPAnalysisRequest(
        asset_ticker="AVAX/USDT",
        timeframe="4h",
        benchmark_regime_status="RISK_ON",
        localized_atr=1.25,
        fibonacci_convergence_proximity=0.01,
        current_price=129.5,
        setup_direction="BUY",
        extra_context={"setup_quality": 0.8},
    ).model_dump()
    response = client.post("/mcp/technical-snapshot", json=payload)
    body = response.json()

    assert response.status_code == 200
    assert body["result"]["provider_info"]["selected_provider"] == "binance_public"
    assert body["result"]["provider_info"]["fallback_used"] is False
    assert body["result"]["ema_ok"] is True


def test_trade_oracle_mcp_service_rejects_missing_api_key_when_auth_enabled():
    app = build_trade_oracle_mcp_app(require_auth=True, api_key="phase3-secret")
    client = TestClient(app)

    payload = MCPAnalysisRequest(
        asset_ticker="AVAX/USDT",
        timeframe="4h",
        benchmark_regime_status="RISK_ON",
        localized_atr=1.35,
        fibonacci_convergence_proximity=0.012,
        current_price=41.25,
        setup_direction="BUY",
    ).model_dump()
    response = client.post("/mcp/macro-snapshot", json=payload)
    body = response.json()

    assert response.status_code == 401
    assert body["status"] == "error"
    assert body["error"]["status_code"] == 401


def test_http_tool_builder_uses_injected_client_without_network():
    class FakeClient:
        def macro_snapshot(self, request):
            return {"tool_name": "macro_snapshot", "status": "ok", "payload": request.model_dump(), "result": {"source": "fake"}}

        def fundamental_snapshot(self, request):
            return {"tool_name": "fundamental_snapshot", "status": "ok", "payload": request.model_dump(), "result": {"source": "fake"}}

        def tokenomics_snapshot(self, request):
            return {"tool_name": "tokenomics_snapshot", "status": "ok", "payload": request.model_dump(), "result": {"source": "fake"}}

        def technical_snapshot(self, request):
            return {"tool_name": "technical_snapshot", "status": "ok", "payload": request.model_dump(), "result": {"source": "fake"}}

        def risk_guardrails(self, request):
            return {"tool_name": "risk_guardrails", "status": "ok", "payload": request.model_dump(), "result": {"source": "fake"}}

    tools = build_trade_oracle_mcp_http_tools(
        client=FakeClient(),
        structured_tool_cls=phase1.StructuredTool,
    )
    payload = {
        "asset_ticker": "AVAX/USDT",
        "timeframe": "4h",
        "benchmark_regime_status": "RISK_ON",
        "localized_atr": 1.35,
        "fibonacci_convergence_proximity": 0.012,
        "current_price": 41.25,
        "setup_direction": "BUY",
    }

    result = tools["macro_snapshot"].invoke(payload)
    assert result["tool_name"] == "macro_snapshot"
    assert result["result"]["source"] == "fake"


def test_trade_oracle_mcp_service_error_class_carries_structured_body():
    error = TradeOracleMCPServiceError(
        "boom",
        status_code=503,
        response_body={"tool_name": "macro_snapshot", "status": "error"},
    )

    assert error.status_code == 503
    assert error.response_body["tool_name"] == "macro_snapshot"


def test_phase1_graph_can_be_built_with_http_tool_client_injected():
    class FakeClient:
        def macro_snapshot(self, request):
            return {"tool_name": "macro_snapshot", "status": "ok", "payload": request.model_dump(), "result": {"macro_regime": "risk_on", "macro_score": 0.82}}

        def fundamental_snapshot(self, request):
            return {"tool_name": "fundamental_snapshot", "status": "ok", "payload": request.model_dump(), "result": {"fundamental_clearance": True}}

        def tokenomics_snapshot(self, request):
            return {"tool_name": "tokenomics_snapshot", "status": "ok", "payload": request.model_dump(), "result": {"tokenomics_clearance": True}}

        def technical_snapshot(self, request):
            return {"tool_name": "technical_snapshot", "status": "ok", "payload": request.model_dump(), "result": {"is_valid": True}}

        def risk_guardrails(self, request):
            return {"tool_name": "risk_guardrails", "status": "ok", "payload": request.model_dump(), "result": {"can_open_new_trade": True}}

    graph = phase1.build_trade_oracle_graph(
        mcp_http_client=FakeClient(),
        checkpointer_path="results/test_trade_oracle_mcp_graph.sqlite",
    )

    assert graph is not None
