import logging
from typing import Dict, Optional

from config import settings

logger = logging.getLogger("TRADE_ORACLE.RiskManager")

# Hardcoded — MUST NOT be overridden by env/config.
_CIRCUIT_BREAKER_DRAWDOWN_PCT: float = 0.025  # 2.5%
_CIRCUIT_BREAKER_BUFFER_USD: float = 15.0    # additional alert buffer (audit/telegram context)


class CircuitBreakerTriggered(Exception):
    """
    Raised when the 2.5% hard drawdown circuit breaker fires.

    This is intentionally distinct from normal risk rejection so the daemon
    can halt the entire evaluation cycle and require manual restart.
    """

    def __init__(self, current_drawdown_pct: float, current_drawdown_usd: float, high_watermark: float):
        self.current_drawdown_pct = current_drawdown_pct
        self.current_drawdown_usd = current_drawdown_usd
        self.high_watermark = high_watermark
        super().__init__(
            f"CIRCUIT BREAKER TRIGGERED: "
            f"Drawdown {current_drawdown_pct * 100:.3f}% "
            f"(${current_drawdown_usd:.2f}) has exceeded the "
            f"{_CIRCUIT_BREAKER_DRAWDOWN_PCT * 100:.1f}% hard limit. "
            f"High watermark was ${high_watermark:.2f}. "
            f"All new trade evaluation is halted. "
            f"Manual operator reset required."
        )


class RiskManager:
    """
    Quantitative gatekeeper for TRADE_ORACLE.

    Enforces:
    - 2.5% hard circuit breaker (hardcoded, non-overridable)
    - 3.0% trailing drawdown limit + $15 operational buffer (per-trade gate)
    - 4-trade maximum concurrency
    - $10 fixed risk per trade
    - 1:2 leverage ceiling
    - ATR-based position sizing
    """

    def __init__(self, current_balance: float, highest_equity: float, active_trades_count: int = 0):
        self.balance = float(current_balance)
        self.high_watermark = float(highest_equity)
        self.active_trades = int(active_trades_count)

        self.risk_usd = float(settings.RISK_AMOUNT_USD)
        self.max_leverage = float(settings.MAX_CRYPTO_LEVERAGE)

        # Configure localized hierarchical logging for operational transparency
        self.logger = logger
        if not self.logger.handlers:
            logging.basicConfig(level=logging.INFO)

    # ------------------------------------------------------------------
    # Circuit Breaker — System-Level Halt
    # ------------------------------------------------------------------

    def check_circuit_breaker(self) -> None:
        """
        Hard 2.5% drawdown circuit breaker.

        Call this BEFORE can_open_new_trade() at the start of every daemon
        evaluation cycle, and again in the Telegram "approve" path right
        before executing the approved trade.

        Raises:
            CircuitBreakerTriggered: if drawdown >= 2.5% from high watermark.
        """
        if self.high_watermark <= 0:
            # Defensive: should never happen, but treat it as a breaker condition.
            self.logger.error(
                "RiskManager.check_circuit_breaker: high_watermark is %.2f — cannot compute drawdown.",
                self.high_watermark,
            )
            raise CircuitBreakerTriggered(
                current_drawdown_pct=1.0,
                current_drawdown_usd=0.0,
                high_watermark=self.high_watermark,
            )

        current_drawdown_usd = max(0.0, self.high_watermark - self.balance)
        current_drawdown_pct = current_drawdown_usd / self.high_watermark

        if current_drawdown_pct >= _CIRCUIT_BREAKER_DRAWDOWN_PCT:
            self.logger.critical(
                "CIRCUIT BREAKER TRIGGERED | "
                "Drawdown: %.3f%% ($%.2f) | "
                "Watermark: $%.2f | "
                "Balance: $%.2f | "
                "Limit: %.1f%% | "
                "ALL EVALUATION HALTED — MANUAL RESET REQUIRED",
                current_drawdown_pct * 100,
                current_drawdown_usd,
                self.high_watermark,
                self.balance,
                _CIRCUIT_BREAKER_DRAWDOWN_PCT * 100,
            )
            raise CircuitBreakerTriggered(
                current_drawdown_pct=current_drawdown_pct,
                current_drawdown_usd=current_drawdown_usd,
                high_watermark=self.high_watermark,
            )

        self._log_drawdown_proximity(current_drawdown_pct, current_drawdown_usd)

    def _log_drawdown_proximity(self, current_drawdown_pct: float, current_drawdown_usd: float) -> None:
        """
        Logs progressively urgent warnings as drawdown approaches the hard circuit breaker.

        Thresholds (pct of high watermark):
        - > 2.0% : WARNING
        - > 2.2% : ERROR
        - > 2.35%: CRITICAL (imminent)
        """
        usd_to_circuit_breaker = (self.high_watermark * _CIRCUIT_BREAKER_DRAWDOWN_PCT) - current_drawdown_usd
        if current_drawdown_pct > 0.0235:
            self.logger.critical(
                "CIRCUIT BREAKER IMMINENT | "
                "Current DD: %.3f%% ($%.2f) | "
                "Only $%.2f from hard halt | "
                "Watermark: $%.2f",
                current_drawdown_pct * 100,
                current_drawdown_usd,
                usd_to_circuit_breaker,
                self.high_watermark,
            )
        elif current_drawdown_pct > 0.022:
            self.logger.error(
                "DRAWDOWN ELEVATED — CONSIDER MANUAL PAUSE | "
                "Current DD: %.3f%% ($%.2f) | "
                "$%.2f from circuit breaker",
                current_drawdown_pct * 100,
                current_drawdown_usd,
                usd_to_circuit_breaker,
            )
        elif current_drawdown_pct > 0.020:
            self.logger.warning(
                "Drawdown elevated | "
                "Current DD: %.3f%% ($%.2f) | "
                "$%.2f from circuit breaker",
                current_drawdown_pct * 100,
                current_drawdown_usd,
                usd_to_circuit_breaker,
            )

    # ------------------------------------------------------------------
    # Trade Entry Gating — Individual Trade Level
    # ------------------------------------------------------------------

    def can_open_new_trade(self) -> bool:
        """
        Validates concurrency limits and critical drawdown proximity.

        Note:
        - This method is a per-trade gate.
        - The system-level 2.5% hard circuit breaker is enforced separately
          via check_circuit_breaker().

        Returns:
            True if trade entry is allowed, else False.
        """
        if self.active_trades >= settings.MAX_CONCURRENT_TRADES:
            self.logger.warning(
                "Concurrency Limit Reached: %d active trades detected. Rejecting new entries.",
                self.active_trades,
            )
            return False

        max_allowed_drop = self.high_watermark * settings.MAX_TRAILING_DRAWDOWN_PCT
        current_drawdown = self.high_watermark - self.balance
        distance_to_failure = max_allowed_drop - current_drawdown

        self.logger.info("Historical High Watermark: $%.2f", self.high_watermark)
        self.logger.info("Absolute Distance to 3%% Failure Level: $%.2f", distance_to_failure)

        if current_drawdown >= max_allowed_drop:
            self.logger.critical(
                "CRITICAL HALT: Trailing Drawdown limit breached. Current DD: $%.2f",
                current_drawdown,
            )
            return False

        # Structural safety buffer: Halt execution if within $15 of absolute failure
        if distance_to_failure <= _CIRCUIT_BREAKER_BUFFER_USD:
            self.logger.warning(
                "WARNING: Approaching critical drawdown threshold. Suspending execution protocols."
            )
            return False

        return True

    # ------------------------------------------------------------------
    # Position Sizing — ATR-based, MT5/CFD bridge aware
    # ------------------------------------------------------------------

    def calculate_position_size(self, entry_price: float, atr: float, direction: str) -> Optional[Dict]:
        """
        Calculates geometric position sizes mathematically adjusted for localized
        volatility (ATR), enforcing the $10 risk pivot and leverage truncation.

        Returns:
            Dict with sizing parameters, or None if trade is rejected.
        """
        # Immediately abort if the portfolio is saturated or in critical drawdown
        if not self.can_open_new_trade():
            return None

        sl_distance = atr * settings.STOP_LOSS_ATR_MULTIPLIER

        if direction.upper() == "LONG":
            stop_loss = entry_price - sl_distance
        elif direction.upper() == "SHORT":
            stop_loss = entry_price + sl_distance
        else:
            self.logger.error("Invalid directional parameter received: %s", direction)
            return None

        absolute_distance = abs(entry_price - stop_loss)

        if absolute_distance <= 0:
            self.logger.error("Mathematical Error: Calculated stop loss distance is zero.")
            return None

        # Core quantitative position sizing formula targeting exactly $10 risk
        theoretical_tokens = self.risk_usd / absolute_distance
        theoretical_usd_value = theoretical_tokens * entry_price

        # Enforce strict 1:2 cryptocurrency leverage limit mapping to $10,000 maximum exposure
        max_usd_exposure = self.balance * self.max_leverage

        if theoretical_usd_value > max_usd_exposure:
            self.logger.warning(
                "Leverage ceiling breached. Truncating theoretical exposure from $%.2f to $%.2f",
                theoretical_usd_value,
                max_usd_exposure,
            )
            actual_usd = max_usd_exposure
            actual_tokens = actual_usd / entry_price

            # Recalculate true risk based on the truncated token volume
            true_risk = actual_tokens * absolute_distance
            self.logger.info("Position size forcibly reduced. True algorithmic risk: $%.2f", true_risk)
        else:
            actual_tokens = theoretical_tokens

        # Calculate Fractional Take-Profit Targets
        if direction.upper() == "LONG":
            tp1 = entry_price + (atr * settings.TP1_ATR_MULTIPLIER)
            tp2 = entry_price + (atr * settings.TP2_ATR_MULTIPLIER)
        else:
            tp1 = entry_price - (atr * settings.TP1_ATR_MULTIPLIER)
            tp2 = entry_price - (atr * settings.TP2_ATR_MULTIPLIER)

        return {
            "tokens": round(actual_tokens, 5),
            "usd_value": round(actual_tokens * entry_price, 2),
            "entry_price": round(entry_price, 4),
            "stop_loss": round(stop_loss, 4),
            "tp1": round(tp1, 4),
            "tp2": round(tp2, 4),
        }
