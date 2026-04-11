"""Lazy API exports for TRADE_ORACLE services.

The API package is imported by the LangGraph core, so exports stay lazy to avoid
pulling the higher-level brain services into module initialization and creating
circular imports.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "BrainAccountState": ("api.trade_oracle_brain_service", "BrainAccountState"),
    "BrainEvaluateSetupRequest": ("api.trade_oracle_brain_service", "BrainEvaluateSetupRequest"),
    "BrainEvaluateBatchRequest": ("api.trade_oracle_brain_service", "BrainEvaluateBatchRequest"),
    "BrainResumeReviewRequest": ("api.trade_oracle_brain_service", "BrainResumeReviewRequest"),
    "BrainServiceResponse": ("api.trade_oracle_brain_service", "BrainServiceResponse"),
    "build_trade_oracle_brain_app": ("api.trade_oracle_brain_service", "build_trade_oracle_brain_app"),
    "SuperBrainAccountState": ("api.trade_oracle_super_brain_service", "SuperBrainAccountState"),
    "SuperBrainRunRequest": ("api.trade_oracle_super_brain_service", "SuperBrainRunRequest"),
    "SuperBrainResumeRequest": ("api.trade_oracle_super_brain_service", "SuperBrainResumeRequest"),
    "SuperBrainResponse": ("api.trade_oracle_super_brain_service", "SuperBrainResponse"),
    "build_trade_oracle_super_brain_app": ("api.trade_oracle_super_brain_service", "build_trade_oracle_super_brain_app"),
    "PlatformHealthResponse": ("api.trade_oracle_platform_service", "PlatformHealthResponse"),
    "PlatformCapabilitiesResponse": ("api.trade_oracle_platform_service", "PlatformCapabilitiesResponse"),
    "PlatformAuditResponse": ("api.trade_oracle_platform_service", "PlatformAuditResponse"),
    "build_trade_oracle_platform_app": ("api.trade_oracle_platform_service", "build_trade_oracle_platform_app"),
    "platform_app": ("api.trade_oracle_platform_service", "app"),
    "Phase2ScannerRequest": ("api.trade_oracle_ops_service", "Phase2ScannerRequest"),
    "LiveScannerRequest": ("api.trade_oracle_ops_service", "LiveScannerRequest"),
    "RiskEvaluateRequest": ("api.trade_oracle_ops_service", "RiskEvaluateRequest"),
    "ExecutionPlatformDetailsRequest": ("api.trade_oracle_ops_service", "ExecutionPlatformDetailsRequest"),
    "ExecutionTransmitOrderRequest": ("api.trade_oracle_ops_service", "ExecutionTransmitOrderRequest"),
    "OpsServiceResponse": ("api.trade_oracle_ops_service", "OpsServiceResponse"),
    "build_trade_oracle_ops_app": ("api.trade_oracle_ops_service", "build_trade_oracle_ops_app"),
    "MCPAnalysisRequest": ("api.trade_oracle_mcp_service", "MCPAnalysisRequest"),
    "RiskGuardrailsRequest": ("api.trade_oracle_mcp_service", "RiskGuardrailsRequest"),
    "MCPToolResponse": ("api.trade_oracle_mcp_service", "MCPToolResponse"),
    "MCPProviderStatusResponse": ("api.trade_oracle_mcp_service", "MCPProviderStatusResponse"),
    "TradeOracleMCPServiceError": ("api.trade_oracle_mcp_service", "TradeOracleMCPServiceError"),
    "TradeOracleExternalSpecialistClient": ("api.trade_oracle_mcp_service", "TradeOracleExternalSpecialistClient"),
    "TradeOracleCoinGeckoProvider": ("api.trade_oracle_mcp_service", "TradeOracleCoinGeckoProvider"),
    "TradeOracleBinancePublicProvider": ("api.trade_oracle_mcp_service", "TradeOracleBinancePublicProvider"),
    "TradeOracleSpecialistProviderRegistry": ("api.trade_oracle_mcp_service", "TradeOracleSpecialistProviderRegistry"),
    "TradeOracleMCPHttpClient": ("api.trade_oracle_mcp_service", "TradeOracleMCPHttpClient"),
    "build_trade_oracle_mcp_app": ("api.trade_oracle_mcp_service", "build_trade_oracle_mcp_app"),
    "build_trade_oracle_mcp_http_tools": ("api.trade_oracle_mcp_service", "build_trade_oracle_mcp_http_tools"),
    "build_trade_oracle_specialist_provider_registry": ("api.trade_oracle_mcp_service", "build_trade_oracle_specialist_provider_registry"),
    "app": ("api.trade_oracle_mcp_service", "app"),
}

__all__ = list(_EXPORTS.keys())


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + __all__)
