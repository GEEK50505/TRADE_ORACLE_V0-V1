"""
FastAPI MCP-style service scaffold for the TRADE_ORACLE specialist tools.

This module intentionally keeps the service deterministic and local-first. It does
not call legacy Python scripts directly yet; instead it exposes typed endpoints and
HTTP tool adapters that the LangGraph layer can adopt without changing topology.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from config import settings
from risk.manager import RiskManager


class MCPAnalysisRequest(BaseModel):
    """Shared request envelope for analysis-oriented specialist tools."""

    model_config = ConfigDict(extra="allow")

    asset_ticker: str
    timeframe: str = "4h"
    benchmark_regime_status: str = ""
    localized_atr: float = 0.0
    fibonacci_convergence_proximity: float = 0.0
    current_price: float = 0.0
    setup_direction: str = "PASS"
    narrative_tags: list[str] = Field(default_factory=list)
    tokenomics_watch: dict[str, Any] = Field(default_factory=dict)
    extra_context: dict[str, Any] = Field(default_factory=dict)


class RiskGuardrailsRequest(BaseModel):
    """Request contract for the deterministic risk guardrails endpoint."""

    model_config = ConfigDict(extra="allow")

    current_balance: float
    highest_equity: float
    active_trades_count: int = 0
    entry_price: float = 0.0
    atr: float = 0.0
    direction: Literal["LONG", "SHORT", "BUY", "SELL"] = "LONG"


class MCPToolResponse(BaseModel):
    """Uniform response envelope returned by each MCP-style endpoint."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    status: Literal["ok", "error"]
    detail: str
    payload: dict[str, Any]
    result: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class MCPProviderStatusResponse(BaseModel):
    """Provider inventory returned by the MCP service."""

    model_config = ConfigDict(extra="forbid")

    service: str
    providers: dict[str, dict[str, Any]] = Field(default_factory=dict)


class TradeOracleMCPServiceError(RuntimeError):
    """Structured HTTP client error raised by the MCP client."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body or {}


COINGECKO_COIN_IDS: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "TON": "the-open-network",
    "ADA": "cardano",
    "BNB": "binancecoin",
}


def _extract_base_symbol(asset_ticker: str) -> str:
    base = str(asset_ticker).strip().upper()
    if "/" in base:
        base = base.split("/", 1)[0]
    if ":" in base:
        base = base.split(":", 1)[0]
    return "".join(char for char in base if char.isalnum())


def _to_binance_symbol(asset_ticker: str) -> str:
    ticker = str(asset_ticker).strip().upper()
    if "/" in ticker:
        base, quote = ticker.split("/", 1)
        return f"{base}{quote}".replace(":", "")
    return "".join(char for char in ticker if char.isalnum())


def _clamp(value: float, *, lower: float = 0.0, upper: float = 0.99) -> float:
    return max(lower, min(float(value), upper))


def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    if abs(float(denominator)) < 1e-12:
        return float(default)
    return float(numerator) / float(denominator)


def _ema(values: list[float], period: int) -> float:
    cleaned = [float(value) for value in values if value is not None]
    if not cleaned:
        return 0.0
    effective_period = max(1, min(period, len(cleaned)))
    multiplier = 2.0 / (effective_period + 1.0)
    ema_value = sum(cleaned[:effective_period]) / effective_period
    for value in cleaned[effective_period:]:
        ema_value = ((value - ema_value) * multiplier) + ema_value
    return float(ema_value)


def _sma(values: list[float], period: int) -> float:
    cleaned = [float(value) for value in values if value is not None]
    if not cleaned:
        return 0.0
    effective_period = max(1, min(period, len(cleaned)))
    return float(sum(cleaned[-effective_period:]) / effective_period)


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    length = min(len(highs), len(lows), len(closes))
    if length < 2:
        return 0.0
    true_ranges: list[float] = []
    for index in range(1, length):
        current_high = float(highs[index])
        current_low = float(lows[index])
        previous_close = float(closes[index - 1])
        true_ranges.append(
            max(
                current_high - current_low,
                abs(current_high - previous_close),
                abs(current_low - previous_close),
            )
        )
    if not true_ranges:
        return 0.0
    effective_period = max(1, min(period, len(true_ranges)))
    return float(sum(true_ranges[-effective_period:]) / effective_period)


@dataclass(slots=True)
class TradeOracleExternalSpecialistClient:
    """Generic HTTP client for optional external specialist data adapters."""

    timeout: float = settings.TRADE_ORACLE_MCP_PROVIDER_TIMEOUT
    api_key: str | None = settings.TRADE_ORACLE_MCP_PROVIDER_API_KEY
    client: httpx.Client | None = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = httpx.Client(timeout=self.timeout, trust_env=False)

    def request_snapshot(self, *, url: str, payload: dict[str, Any], tool_name: str) -> dict[str, Any]:
        headers = {"X-Request-ID": uuid4().hex}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = self.client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError(f"External provider for {tool_name} returned a non-object payload.")
        return body


@dataclass(slots=True)
class TradeOracleCoinGeckoProvider:
    """Live free-provider adapter for macro, fundamental, and tokenomics snapshots."""

    base_url: str = settings.TRADE_ORACLE_COINGECKO_BASE_URL
    api_key: str | None = settings.TRADE_ORACLE_COINGECKO_API_KEY
    timeout: float = settings.TRADE_ORACLE_MCP_PROVIDER_TIMEOUT
    client: httpx.Client | None = None
    coin_id_overrides: dict[str, str] = field(default_factory=lambda: dict(COINGECKO_COIN_IDS))
    coin_id_cache: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = httpx.Client(timeout=self.timeout, trust_env=False)
        self.base_url = self.base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-cg-demo-api-key"] = self.api_key
        return headers

    def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        response = self.client.get(
            f"{self.base_url}{path}",
            params=params or {},
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()

    def resolve_coin_id(self, asset_ticker: str) -> str:
        symbol = _extract_base_symbol(asset_ticker)
        if symbol in self.coin_id_cache:
            return self.coin_id_cache[symbol]
        if symbol in self.coin_id_overrides:
            coin_id = self.coin_id_overrides[symbol]
            self.coin_id_cache[symbol] = coin_id
            return coin_id

        search_body = self._get_json("/search", params={"query": symbol})
        for candidate in list(search_body.get("coins", [])):
            candidate_symbol = str(candidate.get("symbol", "")).strip().upper()
            if candidate_symbol == symbol and candidate.get("id"):
                coin_id = str(candidate["id"])
                self.coin_id_cache[symbol] = coin_id
                return coin_id
        raise ValueError(f"CoinGecko could not resolve a coin ID for symbol '{symbol}'.")

    def _get_coin_market(self, coin_id: str) -> dict[str, Any]:
        market_rows = self._get_json(
            "/coins/markets",
            params={
                "vs_currency": "usd",
                "ids": coin_id,
                "price_change_percentage": "24h",
            },
        )
        if not isinstance(market_rows, list) or not market_rows:
            raise ValueError(f"CoinGecko returned no /coins/markets rows for '{coin_id}'.")
        return dict(market_rows[0])

    def _get_coin_detail(self, coin_id: str) -> dict[str, Any]:
        detail = self._get_json(
            f"/coins/{coin_id}",
            params={
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "true",
                "developer_data": "false",
                "sparkline": "false",
            },
        )
        if not isinstance(detail, dict):
            raise ValueError(f"CoinGecko returned a non-object /coins/{{id}} payload for '{coin_id}'.")
        return detail

    def macro_snapshot(self, request: MCPAnalysisRequest) -> tuple[str, dict[str, Any]]:
        coin_id = self.resolve_coin_id(request.asset_ticker)
        market_row = self._get_coin_market(coin_id)
        global_body = self._get_json("/global")
        global_data = global_body.get("data", {}) if isinstance(global_body, dict) else {}

        global_change = _safe_float(global_data.get("market_cap_change_percentage_24h_usd"), default=0.0)
        btc_dominance = _safe_float(
            (global_data.get("market_cap_percentage") or {}).get("btc"),
            default=52.0,
        )
        asset_change = _safe_float(
            market_row.get("price_change_percentage_24h_in_currency", market_row.get("price_change_percentage_24h")),
            default=0.0,
        )
        market_cap_rank = int(market_row.get("market_cap_rank") or 999999)
        volume_ratio = _safe_div(
            _safe_float(market_row.get("total_volume"), default=0.0),
            _safe_float(market_row.get("market_cap"), default=0.0),
            default=0.0,
        )

        if global_change >= 1.0 and btc_dominance <= 58.0:
            macro_regime = "risk_on"
        elif global_change <= -1.0:
            macro_regime = "risk_off"
        else:
            macro_regime = "neutral"

        long_bias_score = 0.50
        long_bias_score += max(min(global_change / 18.0, 0.18), -0.18)
        long_bias_score += max(min(asset_change / 25.0, 0.16), -0.16)
        long_bias_score += max(min((volume_ratio - 0.05) * 0.8, 0.10), -0.10)
        if market_cap_rank <= 25:
            long_bias_score += 0.04
        if btc_dominance >= 62.0:
            long_bias_score -= 0.05

        setup_direction = request.setup_direction.upper()
        macro_score = long_bias_score if setup_direction in {"BUY", "LONG"} else (1.0 - long_bias_score)
        macro_score = _clamp(macro_score, lower=0.05, upper=0.97)

        supporting_factors = [
            f"CoinGecko global market cap change 24h: {global_change:.2f}%.",
            f"CoinGecko BTC dominance: {btc_dominance:.2f}%.",
            f"{request.asset_ticker} 24h change: {asset_change:.2f}% with volume/market-cap ratio {volume_ratio:.3f}.",
        ]
        risk_flags: list[str] = []
        veto_trade = False

        if macro_regime == "risk_off" and setup_direction in {"BUY", "LONG"}:
            risk_flags.append("CoinGecko global data shows a risk-off regime against a long setup.")
            veto_trade = global_change <= -2.5
        if macro_regime == "risk_on" and setup_direction in {"SELL", "SHORT"}:
            risk_flags.append("CoinGecko global data shows a risk-on regime against a short setup.")
        if market_cap_rank > 50:
            risk_flags.append("Asset market-cap rank is weaker than the preferred major-cap zone.")

        return (
            "Live macro-liquidity snapshot generated from CoinGecko global and market endpoints.",
            {
                "macro_regime": macro_regime,
                "macro_score": macro_score,
                "veto_trade": veto_trade,
                "supporting_factors": supporting_factors,
                "risk_flags": risk_flags,
                "market_cap_rank": market_cap_rank,
                "btc_dominance": btc_dominance,
                "global_market_cap_change_24h_pct": global_change,
                "asset_change_24h_pct": asset_change,
            },
        )

    def fundamental_snapshot(self, request: MCPAnalysisRequest) -> tuple[str, dict[str, Any]]:
        coin_id = self.resolve_coin_id(request.asset_ticker)
        coin_detail = self._get_coin_detail(coin_id)
        categories = [str(item) for item in list(coin_detail.get("categories", [])) if item]
        rank = int(coin_detail.get("market_cap_rank") or 999999)
        sentiment = _safe_float(coin_detail.get("sentiment_votes_up_percentage"), default=0.0)
        links = coin_detail.get("links", {}) if isinstance(coin_detail.get("links"), dict) else {}
        homepage = next((str(url) for url in list(links.get("homepage", [])) if url), "")
        risk_flags: list[str] = []
        catalysts: list[str] = []

        if rank <= 25:
            catalysts.append("Major-cap asset with strong market-cap rank.")
        elif rank <= 100:
            catalysts.append("Mid-to-large cap asset with acceptable liquidity profile.")
        else:
            risk_flags.append("Market-cap rank is outside the preferred liquidity band.")

        if categories:
            catalysts.append(f"CoinGecko categories: {', '.join(categories[:3])}.")
        if homepage:
            catalysts.append("Project exposes an official website in CoinGecko metadata.")
        if sentiment >= 60.0:
            catalysts.append(f"CoinGecko community sentiment is constructive at {sentiment:.1f}% up-votes.")
        elif 0.0 < sentiment < 45.0:
            risk_flags.append(f"CoinGecko community sentiment is weak at {sentiment:.1f}% up-votes.")

        structural_bias = str(_analysis_context(request)["scanner_metadata"].get("structural_bias", "")).strip().lower()
        setup_direction = request.setup_direction.upper()
        if setup_direction in {"BUY", "LONG"} and structural_bias == "relative_weakness":
            risk_flags.append("Narrative structure conflicts with a long bias.")
        if setup_direction in {"SELL", "SHORT"} and structural_bias == "relative_strength":
            risk_flags.append("Narrative structure conflicts with a short bias.")

        return (
            "Live fundamental narrative snapshot generated from CoinGecko coin metadata.",
            {
                "fundamental_clearance": not bool(risk_flags),
                "fundamental_catalysts": catalysts,
                "risk_flags": risk_flags,
                "structural_bias": structural_bias,
                "market_cap_rank": rank,
                "sentiment_votes_up_percentage": sentiment,
            },
        )

    def tokenomics_snapshot(self, request: MCPAnalysisRequest) -> tuple[str, dict[str, Any]]:
        coin_id = self.resolve_coin_id(request.asset_ticker)
        coin_detail = self._get_coin_detail(coin_id)
        market_data = coin_detail.get("market_data", {}) if isinstance(coin_detail.get("market_data"), dict) else {}
        tokenomics_watch = request.tokenomics_watch if isinstance(request.tokenomics_watch, dict) else {}

        circulating_supply = _safe_float(market_data.get("circulating_supply"), default=0.0)
        total_supply = _safe_float(market_data.get("total_supply"), default=0.0)
        max_supply = _safe_float(market_data.get("max_supply"), default=0.0)
        fdv = _safe_float(market_data.get("fully_diluted_valuation", {}).get("usd"), default=0.0)
        market_cap = _safe_float(market_data.get("market_cap", {}).get("usd"), default=0.0)

        supply_ratio = 1.0
        if max_supply > 0:
            supply_ratio = _safe_div(circulating_supply, max_supply, default=1.0)
        elif total_supply > 0:
            supply_ratio = _safe_div(circulating_supply, total_supply, default=1.0)
        fdv_ratio = _safe_div(fdv, market_cap, default=1.0) if fdv > 0 and market_cap > 0 else 1.0

        inferred_major_unlock = bool(max_supply > 0 and supply_ratio < 0.65 and fdv_ratio >= 1.4)
        major_unlock_flag = bool(tokenomics_watch.get("major_unlock_flag", inferred_major_unlock))
        dilutive_event_within_days = int(tokenomics_watch.get("dilutive_event_within_days", 30 if inferred_major_unlock else 999))

        risk_flags: list[str] = []
        if major_unlock_flag:
            risk_flags.append("Tokenomics profile suggests meaningful dilution risk.")
        if dilutive_event_within_days <= 10:
            risk_flags.append("Tokenomics event falls inside the intended swing window.")
        if fdv_ratio >= 1.8:
            risk_flags.append("FDV-to-market-cap ratio is elevated.")

        coverage_quality = "coingecko_live_plus_watch" if tokenomics_watch else "coingecko_live"
        tokenomics_clearance = dilutive_event_within_days > 10 and not major_unlock_flag

        return (
            "Live tokenomics snapshot generated from CoinGecko supply and FDV data.",
            {
                "tokenomics_clearance": tokenomics_clearance,
                "dilutive_event_within_days": dilutive_event_within_days,
                "major_unlock_flag": major_unlock_flag,
                "risk_flags": risk_flags,
                "coverage_quality": coverage_quality,
                "circulating_supply": circulating_supply,
                "total_supply": total_supply,
                "max_supply": max_supply,
                "circulating_supply_ratio": supply_ratio,
                "fdv_to_market_cap_ratio": fdv_ratio,
            },
        )


@dataclass(slots=True)
class TradeOracleBinancePublicProvider:
    """Live free-provider adapter for technical snapshots using Binance public klines."""

    base_url: str = settings.TRADE_ORACLE_BINANCE_BASE_URL
    timeout: float = settings.TRADE_ORACLE_MCP_PROVIDER_TIMEOUT
    client: httpx.Client | None = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = httpx.Client(timeout=self.timeout, trust_env=False)
        self.base_url = self.base_url.rstrip("/")

    def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        response = self.client.get(
            f"{self.base_url}{path}",
            params=params or {},
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        return response.json()

    def technical_snapshot(self, request: MCPAnalysisRequest) -> tuple[str, dict[str, Any]]:
        binance_symbol = _to_binance_symbol(request.asset_ticker)
        interval = str(request.timeframe or "4h").strip() or "4h"
        kline_rows = self._get_json(
            "/api/v3/klines",
            params={"symbol": binance_symbol, "interval": interval, "limit": 120},
        )
        if not isinstance(kline_rows, list) or len(kline_rows) < 20:
            raise ValueError(f"Binance returned insufficient klines for '{binance_symbol}' at interval '{interval}'.")

        closes = [_safe_float(row[4], default=0.0) for row in kline_rows]
        highs = [_safe_float(row[2], default=0.0) for row in kline_rows]
        lows = [_safe_float(row[3], default=0.0) for row in kline_rows]
        latest_close = closes[-1]
        ema20 = _ema(closes, 20)
        sma20 = _sma(closes, 20)
        provider_atr = _atr(highs, lows, closes, 14)
        ema_distance = _safe_div(abs(latest_close - ema20), latest_close, default=1.0)
        sma_distance = _safe_div(abs(latest_close - sma20), latest_close, default=1.0)
        provider_atr_ratio = _safe_div(provider_atr, latest_close, default=0.0)

        is_long_setup = request.setup_direction.upper() in {"BUY", "LONG"}
        ema_confirmed = latest_close >= ema20 if is_long_setup else latest_close <= ema20
        sma_confirmed = latest_close >= sma20 if is_long_setup else latest_close <= sma20
        ema_ok = ema_distance <= 0.03
        fib_ok = request.fibonacci_convergence_proximity <= 0.02
        atr_ok = 0.0 < provider_atr_ratio <= 0.08

        setup_quality = _analysis_context(request)["setup_quality"]
        if setup_quality <= 0.0:
            setup_quality = _clamp(
                0.35
                + (0.18 if ema_confirmed else 0.0)
                + (0.12 if sma_confirmed else 0.0)
                + max(0.0, 0.18 - (ema_distance * 4.0))
                + max(0.0, 0.10 - (request.fibonacci_convergence_proximity * 3.0)),
                lower=0.0,
                upper=0.99,
            )

        risk_flags: list[str] = []
        if not fib_ok:
            risk_flags.append("Fibonacci confluence is too weak.")
        if not atr_ok:
            risk_flags.append("Binance realized volatility is outside the preferred band.")
        if not ema_ok:
            risk_flags.append("Price is too far from the 20-period EMA cluster.")
        if not ema_confirmed:
            risk_flags.append("Price is on the wrong side of the 20-period EMA for the setup direction.")
        if not sma_confirmed:
            risk_flags.append("Price is on the wrong side of the 20-period SMA for the setup direction.")
        if setup_quality < 0.45:
            risk_flags.append("Composite technical quality is below the preferred threshold.")

        is_valid = bool(fib_ok and atr_ok and ema_ok and ema_confirmed and sma_confirmed and setup_quality >= 0.45)

        return (
            "Live technical snapshot generated from Binance public spot kline data.",
            {
                "is_valid": is_valid,
                "fib_ok": fib_ok,
                "atr_ok": atr_ok,
                "ema_ok": ema_ok,
                "ema_confirmed": ema_confirmed,
                "sma_confirmed": sma_confirmed,
                "ema_cluster_distance": ema_distance,
                "sma_distance": sma_distance,
                "setup_quality": setup_quality,
                "localized_atr": request.localized_atr,
                "provider_atr_14": provider_atr,
                "provider_atr_ratio": provider_atr_ratio,
                "provider_ema20": ema20,
                "provider_sma20": sma20,
                "latest_close": latest_close,
                "fibonacci_convergence_proximity": request.fibonacci_convergence_proximity,
                "risk_flags": risk_flags,
            },
        )


@dataclass(slots=True)
class TradeOracleSpecialistProviderRegistry:
    """Per-specialist provider routing for internal, hybrid, or external operation."""

    macro_mode: str = settings.TRADE_ORACLE_MCP_MACRO_PROVIDER_MODE
    fundamental_mode: str = settings.TRADE_ORACLE_MCP_FUNDAMENTAL_PROVIDER_MODE
    tokenomics_mode: str = settings.TRADE_ORACLE_MCP_TOKENOMICS_PROVIDER_MODE
    technical_mode: str = settings.TRADE_ORACLE_MCP_TECHNICAL_PROVIDER_MODE
    macro_provider: str = settings.TRADE_ORACLE_MCP_MACRO_PROVIDER
    fundamental_provider: str = settings.TRADE_ORACLE_MCP_FUNDAMENTAL_PROVIDER
    tokenomics_provider: str = settings.TRADE_ORACLE_MCP_TOKENOMICS_PROVIDER
    technical_provider: str = settings.TRADE_ORACLE_MCP_TECHNICAL_PROVIDER
    macro_url: str = settings.TRADE_ORACLE_MCP_MACRO_PROVIDER_URL
    fundamental_url: str = settings.TRADE_ORACLE_MCP_FUNDAMENTAL_PROVIDER_URL
    tokenomics_url: str = settings.TRADE_ORACLE_MCP_TOKENOMICS_PROVIDER_URL
    technical_url: str = settings.TRADE_ORACLE_MCP_TECHNICAL_PROVIDER_URL
    external_client: TradeOracleExternalSpecialistClient | None = None
    coingecko_provider: TradeOracleCoinGeckoProvider | None = None
    binance_provider: TradeOracleBinancePublicProvider | None = None

    def describe(self) -> dict[str, dict[str, Any]]:
        return {
            "macro_snapshot": self._domain_status(
                mode=self.macro_mode,
                provider_name=self.macro_provider,
                url=self.macro_url,
            ),
            "fundamental_snapshot": self._domain_status(
                mode=self.fundamental_mode,
                provider_name=self.fundamental_provider,
                url=self.fundamental_url,
            ),
            "tokenomics_snapshot": self._domain_status(
                mode=self.tokenomics_mode,
                provider_name=self.tokenomics_provider,
                url=self.tokenomics_url,
            ),
            "technical_snapshot": self._domain_status(
                mode=self.technical_mode,
                provider_name=self.technical_provider,
                url=self.technical_url,
            ),
            "risk_guardrails": {
                "mode": "internal",
                "provider_name": "risk_manager",
                "external_url_configured": False,
                "fallback_enabled": False,
            },
        }

    @staticmethod
    def _normalized_provider_name(*, mode: str, provider_name: str, url: str) -> str:
        normalized_mode = mode.strip().lower()
        normalized_provider = provider_name.strip().lower()
        if normalized_mode == "internal":
            return "internal_context_adapter"
        if url:
            return "external_http_provider"
        if normalized_provider in {"coingecko", "binance_public"}:
            return normalized_provider
        return "external_http_provider"

    @classmethod
    def _domain_status(cls, *, mode: str, provider_name: str, url: str) -> dict[str, Any]:
        normalized_mode = mode.strip().lower()
        return {
            "mode": normalized_mode,
            "provider_name": cls._normalized_provider_name(mode=mode, provider_name=provider_name, url=url),
            "external_url_configured": bool(url),
            "fallback_enabled": normalized_mode == "hybrid",
        }

    def _coingecko(self) -> TradeOracleCoinGeckoProvider:
        if self.coingecko_provider is None:
            self.coingecko_provider = TradeOracleCoinGeckoProvider()
        return self.coingecko_provider

    def _binance(self) -> TradeOracleBinancePublicProvider:
        if self.binance_provider is None:
            self.binance_provider = TradeOracleBinancePublicProvider()
        return self.binance_provider

    def _resolve_live_snapshot(
        self,
        *,
        tool_name: str,
        request: MCPAnalysisRequest,
        provider_name: str,
        url: str,
        request_payload: dict[str, Any],
    ) -> tuple[str, dict[str, Any], str]:
        if url:
            if self.external_client is None:
                raise ValueError(f"{tool_name} is configured with an external URL but no external client is available.")
            response_body = self.external_client.request_snapshot(
                url=url,
                payload=request_payload,
                tool_name=tool_name,
            )
            detail, result = _normalize_external_snapshot_response(
                tool_name=tool_name,
                response_body=response_body,
            )
            return detail, result, "external_http_provider"

        normalized_provider = provider_name.strip().lower()
        if normalized_provider == "coingecko":
            provider = self._coingecko()
            if tool_name == "macro_snapshot":
                detail, result = provider.macro_snapshot(request)
            elif tool_name == "fundamental_snapshot":
                detail, result = provider.fundamental_snapshot(request)
            elif tool_name == "tokenomics_snapshot":
                detail, result = provider.tokenomics_snapshot(request)
            else:
                raise ValueError(f"CoinGecko does not support '{tool_name}'.")
            return detail, result, "coingecko"

        if normalized_provider == "binance_public":
            if tool_name != "technical_snapshot":
                raise ValueError(f"Binance public market data does not support '{tool_name}'.")
            detail, result = self._binance().technical_snapshot(request)
            return detail, result, "binance_public"

        if self.external_client is None:
            raise ValueError(f"{tool_name} requires a custom external client for provider '{provider_name}'.")
        response_body = self.external_client.request_snapshot(
            url=url,
            payload=request_payload,
            tool_name=tool_name,
        )
        detail, result = _normalize_external_snapshot_response(
            tool_name=tool_name,
            response_body=response_body,
        )
        return detail, result, "external_http_provider"

    def resolve_snapshot(
        self,
        *,
        tool_name: str,
        request: MCPAnalysisRequest,
        request_payload: dict[str, Any],
        mode: str,
        provider_name: str,
        url: str,
        internal_detail: str,
        internal_result: dict[str, Any],
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        normalized_mode = mode.strip().lower()
        provider_meta = self._domain_status(mode=normalized_mode, provider_name=provider_name, url=url)
        if normalized_mode == "internal":
            return internal_detail, dict(internal_result), {
                **provider_meta,
                "selected_provider": "internal_context_adapter",
                "fallback_used": False,
            }

        try:
            detail, result, selected_provider = self._resolve_live_snapshot(
                tool_name=tool_name,
                request=request,
                provider_name=provider_name,
                url=url,
                request_payload=request_payload,
            )
            return detail, result, {
                **provider_meta,
                "selected_provider": selected_provider,
                "fallback_used": False,
            }
        except Exception as exc:
            if normalized_mode == "external":
                raise
            return internal_detail, dict(internal_result), {
                **provider_meta,
                "selected_provider": "internal_context_adapter",
                "fallback_used": True,
                "fallback_reason": str(exc),
            }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _analysis_context(request: MCPAnalysisRequest) -> dict[str, Any]:
    """Normalize extra_context payloads into one safe adapter context object."""
    extra_context = request.extra_context if isinstance(request.extra_context, dict) else {}
    scanner_metadata = extra_context.get("scanner_metadata", {})
    scanner_metadata = scanner_metadata if isinstance(scanner_metadata, dict) else {}
    account_state = extra_context.get("account_state", {})
    account_state = account_state if isinstance(account_state, dict) else {}
    return {
        "extra_context": extra_context,
        "scanner_metadata": scanner_metadata,
        "account_state": account_state,
        "setup_quality": _safe_float(extra_context.get("setup_quality"), default=0.0),
        "ema_cluster_distance": _safe_float(extra_context.get("ema_cluster_distance"), default=1.0),
        "portfolio_expectancy": _safe_float(extra_context.get("portfolio_expectancy"), default=0.0),
        "portfolio_max_dd_pct": _safe_float(extra_context.get("portfolio_max_dd_pct"), default=0.0),
        "portfolio_consistency_score": _safe_float(extra_context.get("portfolio_consistency_score"), default=0.0),
        "portfolio_overall_survival": bool(extra_context.get("portfolio_overall_survival", False)),
        "candidate_portfolio_size": int(extra_context.get("candidate_portfolio_size", 0) or 0),
    }


def _response_meta(*, request: Request | None = None, tool_name: str) -> dict[str, Any]:
    request_id = None
    path = ""
    if request is not None:
        request_id = request.headers.get("X-Request-ID") or getattr(request.state, "request_id", None)
        path = request.url.path
    return {
        "request_id": request_id or uuid4().hex,
        "tool_name": tool_name,
        "path": path,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _tool_response(
    *,
    tool_name: str,
    detail: str,
    payload: dict[str, Any],
    result: dict[str, Any] | None = None,
    request: Request | None = None,
) -> MCPToolResponse:
    return MCPToolResponse(
        tool_name=tool_name,
        status="ok",
        detail=detail,
        payload=payload,
        result=result or {},
        meta=_response_meta(request=request, tool_name=tool_name),
    )


def _normalize_external_snapshot_response(
    *,
    tool_name: str,
    response_body: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Accept either a raw result dict or an MCP-like envelope from an external provider."""
    if str(response_body.get("status", "")).lower() == "ok" and isinstance(response_body.get("result"), dict):
        detail = str(response_body.get("detail", f"External provider returned {tool_name} successfully."))
        return detail, dict(response_body["result"])
    return f"External provider returned raw structured output for {tool_name}.", dict(response_body)


def _error_response(
    *,
    tool_name: str,
    detail: str,
    payload: dict[str, Any] | None = None,
    code: str,
    request: Request | None = None,
    status_code: int | None = None,
    error: dict[str, Any] | None = None,
) -> MCPToolResponse:
    error_body = {
        "code": code,
        "status_code": status_code,
    }
    if error:
        error_body.update(error)
    return MCPToolResponse(
        tool_name=tool_name,
        status="error",
        detail=detail,
        payload=payload or {},
        error=error_body,
        meta=_response_meta(request=request, tool_name=tool_name),
    )


def _authorization_dependency(
    *,
    require_auth: bool,
    expected_api_key: str | None,
):
    def authorize_request(
        x_trade_oracle_api_key: str | None = Header(default=None, alias="X-Trade-Oracle-API-Key"),
    ) -> None:
        if not require_auth:
            return
        if not expected_api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="MCP authentication is enabled but TRADE_ORACLE_MCP_API_KEY is not configured.",
            )
        if x_trade_oracle_api_key != expected_api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing MCP API key.",
            )

    return authorize_request


def _build_internal_macro_snapshot_result(request: MCPAnalysisRequest) -> tuple[str, dict[str, Any]]:
    context = _analysis_context(request)
    benchmark = request.benchmark_regime_status.upper()
    setup_direction = request.setup_direction.upper()
    macro_regime = "neutral"
    macro_score = 0.55
    veto_trade = False
    supporting_factors: list[str] = []
    risk_flags: list[str] = []

    if "RISK_ON" in benchmark or "BULL" in benchmark:
        macro_regime = "risk_on"
        macro_score = 0.80 if setup_direction in {"BUY", "LONG"} else 0.34
        supporting_factors.append("Benchmark regime supports risk-on positioning.")
    elif "RISK_OFF" in benchmark or "BEAR" in benchmark:
        macro_regime = "risk_off"
        macro_score = 0.28 if setup_direction in {"BUY", "LONG"} else 0.78
        supporting_factors.append("Benchmark regime supports defensive or short-biased positioning.")

    if macro_regime == "risk_off" and setup_direction in {"BUY", "LONG"}:
        veto_trade = True
        risk_flags.append("Risk-off macro regime conflicts with a long-biased setup.")
    elif macro_regime == "risk_on" and setup_direction in {"SELL", "SHORT"}:
        risk_flags.append("Risk-on macro regime conflicts with a short-biased setup.")

    setup_quality = context["setup_quality"]
    if setup_quality > 0.0:
        macro_score += min(setup_quality * 0.12, 0.12)
        supporting_factors.append(f"Scanner setup quality contributes {min(setup_quality * 0.12, 0.12):.2f} score uplift.")

    if context["portfolio_overall_survival"]:
        macro_score += 0.03
        supporting_factors.append("Portfolio source context previously survived realistic rules.")
    if context["portfolio_max_dd_pct"] >= 2.8:
        macro_score -= 0.05
        risk_flags.append("Portfolio drawdown context is already close to Maven tolerance.")

    macro_score = max(0.0, min(macro_score, 0.99))

    return (
        "Internal macro-liquidity adapter generated from scanner and portfolio context.",
        {
            "macro_regime": macro_regime,
            "macro_score": macro_score,
            "veto_trade": veto_trade,
            "supporting_factors": supporting_factors,
            "risk_flags": risk_flags,
        },
    )


def _build_internal_fundamental_snapshot_result(request: MCPAnalysisRequest) -> tuple[str, dict[str, Any]]:
    context = _analysis_context(request)
    scanner_metadata = context["scanner_metadata"]
    structural_bias = str(scanner_metadata.get("structural_bias", "")).strip().lower()
    catalysts = list(request.narrative_tags) or [
        "High-liquidity majors remain preferred under Maven-style execution constraints."
    ]
    risk_flags = [tag for tag in catalysts if "regulatory" in tag.lower()]
    if structural_bias:
        catalysts.append(f"structural_bias:{structural_bias}")
    if context["portfolio_overall_survival"]:
        catalysts.append("realistic_survivor_context")
    if context["setup_quality"] < 0.45 and context["setup_quality"] > 0.0:
        risk_flags.append("Scanner setup quality is weak relative to preferred threshold.")

    setup_direction = request.setup_direction.upper()
    if setup_direction in {"BUY", "LONG"} and structural_bias == "relative_weakness":
        risk_flags.append("Narrative structure conflicts with a long bias.")
    if setup_direction in {"SELL", "SHORT"} and structural_bias == "relative_strength":
        risk_flags.append("Narrative structure conflicts with a short bias.")

    fundamental_clearance = not bool(risk_flags)
    return (
        "Internal narrative adapter generated from scanner tags and structural context.",
        {
            "fundamental_clearance": fundamental_clearance,
            "fundamental_catalysts": list(dict.fromkeys(catalysts)),
            "risk_flags": risk_flags,
            "structural_bias": structural_bias,
        },
    )


def _build_internal_tokenomics_snapshot_result(request: MCPAnalysisRequest) -> tuple[str, dict[str, Any]]:
    context = _analysis_context(request)
    tokenomics_watch = request.tokenomics_watch
    dilutive_days = int(tokenomics_watch.get("dilutive_event_within_days", 999))
    major_unlock_flag = bool(tokenomics_watch.get("major_unlock_flag", False))
    risk_flags: list[str] = []
    if major_unlock_flag:
        risk_flags.append("Major unlock flag detected in the holding window.")
    if dilutive_days <= 10:
        risk_flags.append("Dilutive event falls inside the intended swing window.")
    if context["candidate_portfolio_size"] >= 3 and dilutive_days <= 45:
        risk_flags.append("Portfolio-sized swing window overlaps a potentially meaningful dilution window.")

    coverage_quality = "explicit_watch" if tokenomics_watch else "no_live_coverage"
    tokenomics_clearance = dilutive_days > 10 and not major_unlock_flag

    return (
        "Internal tokenomics adapter generated from tokenomics_watch and holding-window context.",
        {
            "tokenomics_clearance": tokenomics_clearance,
            "dilutive_event_within_days": dilutive_days,
            "major_unlock_flag": major_unlock_flag,
            "risk_flags": risk_flags,
            "coverage_quality": coverage_quality,
        },
    )


def _build_internal_technical_snapshot_result(request: MCPAnalysisRequest) -> tuple[str, dict[str, Any]]:
    context = _analysis_context(request)
    scanner_metadata = context["scanner_metadata"]
    fib_ok = request.fibonacci_convergence_proximity <= 0.02
    atr_ok = 0.0 < request.localized_atr < max(request.current_price * 0.08, 0.5)
    ema_distance = context["ema_cluster_distance"]
    setup_quality = context["setup_quality"]
    ema_ok = ema_distance <= 0.03
    ema_confirmed = bool(scanner_metadata.get("ema_confirmed", ema_ok))
    sma_confirmed = bool(scanner_metadata.get("sma_confirmed", True))
    risk_flags: list[str] = []
    if not fib_ok:
        risk_flags.append("Fibonacci confluence is too weak.")
    if not atr_ok:
        risk_flags.append("ATR regime is outside the safe structural band.")
    if not ema_ok:
        risk_flags.append("Price is too far from the EMA cluster.")
    if not ema_confirmed:
        risk_flags.append("EMA confirmation is missing from scanner structure.")
    if not sma_confirmed:
        risk_flags.append("SMA confirmation is missing from scanner structure.")
    if 0.0 < setup_quality < 0.45:
        risk_flags.append("Scanner setup quality is below the preferred threshold.")

    is_valid = bool(fib_ok and atr_ok and ema_ok and ema_confirmed and sma_confirmed and (setup_quality == 0.0 or setup_quality >= 0.45))

    return (
        "Internal technical adapter generated from scanner structure and volatility context.",
        {
            "is_valid": is_valid,
            "fib_ok": fib_ok,
            "atr_ok": atr_ok,
            "ema_ok": ema_ok,
            "ema_confirmed": ema_confirmed,
            "sma_confirmed": sma_confirmed,
            "ema_cluster_distance": ema_distance,
            "setup_quality": setup_quality,
            "localized_atr": request.localized_atr,
            "fibonacci_convergence_proximity": request.fibonacci_convergence_proximity,
            "risk_flags": risk_flags,
        },
    )


def build_trade_oracle_specialist_provider_registry(
    *,
    external_client: TradeOracleExternalSpecialistClient | None = None,
    coingecko_provider: TradeOracleCoinGeckoProvider | None = None,
    binance_provider: TradeOracleBinancePublicProvider | None = None,
) -> TradeOracleSpecialistProviderRegistry:
    """Build the MCP specialist provider registry from settings or injected clients."""
    return TradeOracleSpecialistProviderRegistry(
        external_client=external_client,
        coingecko_provider=coingecko_provider,
        binance_provider=binance_provider,
    )


def build_macro_snapshot_response(
    request: MCPAnalysisRequest,
    *,
    http_request: Request | None = None,
    provider_registry: TradeOracleSpecialistProviderRegistry | None = None,
) -> MCPToolResponse:
    registry = provider_registry or build_trade_oracle_specialist_provider_registry()
    internal_detail, internal_result = _build_internal_macro_snapshot_result(request)
    detail, result, provider_meta = registry.resolve_snapshot(
        tool_name="macro_snapshot",
        request=request,
        request_payload=request.model_dump(),
        mode=registry.macro_mode,
        provider_name=registry.macro_provider,
        url=registry.macro_url,
        internal_detail=internal_detail,
        internal_result=internal_result,
    )
    return _tool_response(
        tool_name="macro_snapshot",
        detail=detail,
        payload=request.model_dump(),
        result={**result, "provider_info": provider_meta},
        request=http_request,
    )


def build_fundamental_snapshot_response(
    request: MCPAnalysisRequest,
    *,
    http_request: Request | None = None,
    provider_registry: TradeOracleSpecialistProviderRegistry | None = None,
) -> MCPToolResponse:
    registry = provider_registry or build_trade_oracle_specialist_provider_registry()
    internal_detail, internal_result = _build_internal_fundamental_snapshot_result(request)
    detail, result, provider_meta = registry.resolve_snapshot(
        tool_name="fundamental_snapshot",
        request=request,
        request_payload=request.model_dump(),
        mode=registry.fundamental_mode,
        provider_name=registry.fundamental_provider,
        url=registry.fundamental_url,
        internal_detail=internal_detail,
        internal_result=internal_result,
    )
    return _tool_response(
        tool_name="fundamental_snapshot",
        detail=detail,
        payload=request.model_dump(),
        result={**result, "provider_info": provider_meta},
        request=http_request,
    )


def build_tokenomics_snapshot_response(
    request: MCPAnalysisRequest,
    *,
    http_request: Request | None = None,
    provider_registry: TradeOracleSpecialistProviderRegistry | None = None,
) -> MCPToolResponse:
    registry = provider_registry or build_trade_oracle_specialist_provider_registry()
    internal_detail, internal_result = _build_internal_tokenomics_snapshot_result(request)
    detail, result, provider_meta = registry.resolve_snapshot(
        tool_name="tokenomics_snapshot",
        request=request,
        request_payload=request.model_dump(),
        mode=registry.tokenomics_mode,
        provider_name=registry.tokenomics_provider,
        url=registry.tokenomics_url,
        internal_detail=internal_detail,
        internal_result=internal_result,
    )
    return _tool_response(
        tool_name="tokenomics_snapshot",
        detail=detail,
        payload=request.model_dump(),
        result={**result, "provider_info": provider_meta},
        request=http_request,
    )


def build_technical_snapshot_response(
    request: MCPAnalysisRequest,
    *,
    http_request: Request | None = None,
    provider_registry: TradeOracleSpecialistProviderRegistry | None = None,
) -> MCPToolResponse:
    registry = provider_registry or build_trade_oracle_specialist_provider_registry()
    internal_detail, internal_result = _build_internal_technical_snapshot_result(request)
    detail, result, provider_meta = registry.resolve_snapshot(
        tool_name="technical_snapshot",
        request=request,
        request_payload=request.model_dump(),
        mode=registry.technical_mode,
        provider_name=registry.technical_provider,
        url=registry.technical_url,
        internal_detail=internal_detail,
        internal_result=internal_result,
    )
    return _tool_response(
        tool_name="technical_snapshot",
        detail=detail,
        payload=request.model_dump(),
        result={**result, "provider_info": provider_meta},
        request=http_request,
    )


def build_risk_guardrails_response(
    request: RiskGuardrailsRequest,
    *,
    http_request: Request | None = None,
) -> MCPToolResponse:
    risk_manager = RiskManager(
        current_balance=request.current_balance,
        highest_equity=request.highest_equity,
        active_trades_count=request.active_trades_count,
    )
    can_open_new_trade = risk_manager.can_open_new_trade()

    position_size: dict[str, Any] | None = None
    if can_open_new_trade and request.entry_price > 0 and request.atr > 0:
        direction = "LONG" if request.direction.upper() in {"BUY", "LONG"} else "SHORT"
        position_size = risk_manager.calculate_position_size(
            entry_price=request.entry_price,
            atr=request.atr,
            direction=direction,
        )

    return _tool_response(
        tool_name="risk_guardrails",
        detail="Deterministic risk guardrails response generated by the Phase 3 MCP scaffold.",
        payload=request.model_dump(),
        result={
            "can_open_new_trade": can_open_new_trade,
            "risk_amount_usd": settings.RISK_AMOUNT_USD,
            "max_concurrent_trades": settings.MAX_CONCURRENT_TRADES,
            "position_size": position_size,
        },
        request=http_request,
    )


def build_trade_oracle_mcp_app(
    *,
    require_auth: bool | None = None,
    api_key: str | None = None,
    provider_registry: TradeOracleSpecialistProviderRegistry | None = None,
) -> FastAPI:
    """Create the FastAPI microservice described in the architecture blueprint."""
    resolved_api_key = api_key if api_key is not None else settings.TRADE_ORACLE_MCP_API_KEY
    resolved_require_auth = (
        require_auth
        if require_auth is not None
        else (settings.TRADE_ORACLE_MCP_REQUIRE_AUTH or bool(resolved_api_key))
    )
    authorize_request = _authorization_dependency(
        require_auth=resolved_require_auth,
        expected_api_key=resolved_api_key,
    )
    resolved_provider_registry = provider_registry or build_trade_oracle_specialist_provider_registry()
    app = FastAPI(
        title="TRADE_ORACLE MCP Service",
        version="0.1.0",
        description="Phase 3 FastAPI scaffold exposing internal, hybrid, or external MCP-style specialist tools.",
    )

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        body = _error_response(
            tool_name="request_validation",
            detail="Incoming MCP payload failed validation.",
            payload={},
            code="validation_error",
            request=request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error={"issues": exc.errors()},
        )
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=body.model_dump())

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        body = _error_response(
            tool_name="request_authorization",
            detail=str(exc.detail),
            payload={},
            code="http_error",
            request=request,
            status_code=exc.status_code,
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        body = _error_response(
            tool_name="internal_service_error",
            detail="Unhandled MCP service exception.",
            payload={},
            code="internal_error",
            request=request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error={"type": type(exc).__name__, "message": str(exc)},
        )
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=body.model_dump())

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/mcp/providers/status", response_model=MCPProviderStatusResponse)
    def provider_status(_: None = Depends(authorize_request)) -> MCPProviderStatusResponse:
        return MCPProviderStatusResponse(
            service="trade_oracle_mcp",
            providers=resolved_provider_registry.describe(),
        )

    @app.post("/mcp/macro-snapshot", response_model=MCPToolResponse)
    def macro_snapshot(
        request: MCPAnalysisRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> MCPToolResponse:
        return build_macro_snapshot_response(
            request,
            http_request=http_request,
            provider_registry=resolved_provider_registry,
        )

    @app.post("/mcp/fundamental-snapshot", response_model=MCPToolResponse)
    def fundamental_snapshot(
        request: MCPAnalysisRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> MCPToolResponse:
        return build_fundamental_snapshot_response(
            request,
            http_request=http_request,
            provider_registry=resolved_provider_registry,
        )

    @app.post("/mcp/tokenomics-snapshot", response_model=MCPToolResponse)
    def tokenomics_snapshot(
        request: MCPAnalysisRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> MCPToolResponse:
        return build_tokenomics_snapshot_response(
            request,
            http_request=http_request,
            provider_registry=resolved_provider_registry,
        )

    @app.post("/mcp/technical-snapshot", response_model=MCPToolResponse)
    def technical_snapshot(
        request: MCPAnalysisRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> MCPToolResponse:
        return build_technical_snapshot_response(
            request,
            http_request=http_request,
            provider_registry=resolved_provider_registry,
        )

    @app.post("/mcp/risk-guardrails", response_model=MCPToolResponse)
    def risk_guardrails(
        request: RiskGuardrailsRequest,
        http_request: Request,
        _: None = Depends(authorize_request),
    ) -> MCPToolResponse:
        return build_risk_guardrails_response(request, http_request=http_request)

    return app


class TradeOracleMCPHttpClient:
    """Small HTTP client for the Phase 3 MCP-style service."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key if api_key is not None else settings.TRADE_ORACLE_MCP_API_KEY
        self._owns_client = client is None
        self.client = client or httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"X-Request-ID": uuid4().hex}
        if self.api_key:
            headers["X-Trade-Oracle-API-Key"] = self.api_key
        try:
            response = self.client.post(path, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise TradeOracleMCPServiceError(
                f"MCP request failed before a response was received: {exc}",
                response_body=_error_response(
                    tool_name="http_transport_error",
                    detail="MCP service transport failure.",
                    payload=payload,
                    code="transport_error",
                    error={"type": type(exc).__name__, "message": str(exc)},
                ).model_dump(),
            ) from exc

        try:
            response_body = response.json()
        except ValueError:
            response_body = {
                "tool_name": "invalid_json_response",
                "status": "error",
                "detail": "MCP service returned a non-JSON response.",
                "payload": payload,
                "result": {},
                "error": {
                    "code": "invalid_json_response",
                    "status_code": response.status_code,
                    "raw_text": response.text,
                },
                "meta": {
                    "request_id": response.headers.get("X-Request-ID", headers["X-Request-ID"]),
                    "path": path,
                },
            }

        if response.is_error:
            raise TradeOracleMCPServiceError(
                f"MCP request failed with HTTP {response.status_code}.",
                status_code=response.status_code,
                response_body=response_body,
            )
        return response_body

    def health(self) -> dict[str, Any]:
        response = self.client.get("/health")
        response.raise_for_status()
        return response.json()

    def provider_status(self) -> dict[str, Any]:
        response = self.client.get("/mcp/providers/status")
        response.raise_for_status()
        return response.json()

    def macro_snapshot(self, request: MCPAnalysisRequest) -> dict[str, Any]:
        return self._post("/mcp/macro-snapshot", request.model_dump())

    def fundamental_snapshot(self, request: MCPAnalysisRequest) -> dict[str, Any]:
        return self._post("/mcp/fundamental-snapshot", request.model_dump())

    def tokenomics_snapshot(self, request: MCPAnalysisRequest) -> dict[str, Any]:
        return self._post("/mcp/tokenomics-snapshot", request.model_dump())

    def technical_snapshot(self, request: MCPAnalysisRequest) -> dict[str, Any]:
        return self._post("/mcp/technical-snapshot", request.model_dump())

    def risk_guardrails(self, request: RiskGuardrailsRequest) -> dict[str, Any]:
        return self._post("/mcp/risk-guardrails", request.model_dump())


def build_trade_oracle_mcp_http_tools(
    *,
    client: TradeOracleMCPHttpClient,
    structured_tool_cls: type[Any] | None = None,
) -> dict[str, Any]:
    """Build LangChain-compatible tool callables backed by the HTTP client."""

    def macro_snapshot(**kwargs: Any) -> dict[str, Any]:
        return client.macro_snapshot(MCPAnalysisRequest.model_validate(kwargs))

    def fundamental_snapshot(**kwargs: Any) -> dict[str, Any]:
        return client.fundamental_snapshot(MCPAnalysisRequest.model_validate(kwargs))

    def tokenomics_snapshot(**kwargs: Any) -> dict[str, Any]:
        return client.tokenomics_snapshot(MCPAnalysisRequest.model_validate(kwargs))

    def technical_snapshot(**kwargs: Any) -> dict[str, Any]:
        return client.technical_snapshot(MCPAnalysisRequest.model_validate(kwargs))

    def risk_guardrails(**kwargs: Any) -> dict[str, Any]:
        return client.risk_guardrails(RiskGuardrailsRequest.model_validate(kwargs))

    functions = {
        "macro_snapshot": (macro_snapshot, MCPAnalysisRequest, "HTTP-backed macro snapshot via FastAPI MCP service."),
        "fundamental_snapshot": (
            fundamental_snapshot,
            MCPAnalysisRequest,
            "HTTP-backed fundamental snapshot via FastAPI MCP service.",
        ),
        "tokenomics_snapshot": (
            tokenomics_snapshot,
            MCPAnalysisRequest,
            "HTTP-backed tokenomics snapshot via FastAPI MCP service.",
        ),
        "technical_snapshot": (
            technical_snapshot,
            MCPAnalysisRequest,
            "HTTP-backed technical snapshot via FastAPI MCP service.",
        ),
        "risk_guardrails": (
            risk_guardrails,
            RiskGuardrailsRequest,
            "HTTP-backed risk guardrails via FastAPI MCP service.",
        ),
    }

    if structured_tool_cls is None:
        return {name: func for name, (func, _, _) in functions.items()}

    return {
        name: structured_tool_cls.from_function(
            func=func,
            name=name,
            description=description,
            args_schema=args_schema,
        )
        for name, (func, args_schema, description) in functions.items()
    }


app = build_trade_oracle_mcp_app()


__all__ = [
    "MCPAnalysisRequest",
    "RiskGuardrailsRequest",
    "MCPToolResponse",
    "MCPProviderStatusResponse",
    "TradeOracleMCPServiceError",
    "TradeOracleExternalSpecialistClient",
    "TradeOracleCoinGeckoProvider",
    "TradeOracleBinancePublicProvider",
    "TradeOracleSpecialistProviderRegistry",
    "TradeOracleMCPHttpClient",
    "build_trade_oracle_mcp_app",
    "build_trade_oracle_mcp_http_tools",
    "build_trade_oracle_specialist_provider_registry",
    "build_macro_snapshot_response",
    "build_fundamental_snapshot_response",
    "build_tokenomics_snapshot_response",
    "build_technical_snapshot_response",
    "build_risk_guardrails_response",
    "app",
]
