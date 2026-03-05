# risk/manager.py
import logging
from typing import Dict, Optional
from config import settings

class RiskManager:
    """
    The RiskManager is the quantitative gatekeeper for the TRADE_ORACLE architecture.
    It strictly enforces trailing drawdown limits, manages concurrent portfolio exposure,
    executes dynamic volatility-based position sizing, and mandates hard margin ceilings.
    """
    
    def __init__(self, current_balance: float, highest_equity: float, active_trades_count: int = 0):
        self.balance = current_balance
        self.high_watermark = highest_equity
        self.active_trades = active_trades_count
        self.risk_usd = settings.RISK_AMOUNT_USD
        self.max_leverage = settings.MAX_CRYPTO_LEVERAGE
        
        # Configure localized hierarchical logging for operational transparency
        self.logger = logging.getLogger("TRADE_ORACLE.RiskManager")
        if not self.logger.handlers:
            logging.basicConfig(level=logging.INFO)

    def can_open_new_trade(self) -> bool:
        """
        Validates concurrency limits and critical drawdown proximity.
        Each trade risks exactly $10. Total allowable risk is $50 (1% floating limit).
        Maximum concurrent operational trades are capped at 4 to reserve a $10 slippage buffer.
        """
        if self.active_trades >= settings.MAX_CONCURRENT_TRADES:
            self.logger.warning(f"Concurrency Limit Reached: {self.active_trades} active trades detected. Rejecting new entries.")
            return False
            
        max_allowed_drop = self.high_watermark * settings.MAX_TRAILING_DRAWDOWN_PCT
        current_drawdown = self.high_watermark - self.balance
        distance_to_failure = max_allowed_drop - current_drawdown
        
        self.logger.info(f"Historical High Watermark: ${self.high_watermark:.2f}")
        self.logger.info(f"Absolute Distance to 3% Failure Level: ${distance_to_failure:.2f}")
        
        if current_drawdown >= max_allowed_drop:
            self.logger.critical(f"CRITICAL HALT: Trailing Drawdown limit breached. Current DD: ${current_drawdown:.2f}")
            return False
            
        # Structural safety buffer: Halt execution if within $15 of absolute failure
        if distance_to_failure <= 15.0:
            self.logger.warning("WARNING: Approaching critical drawdown threshold. Suspending execution protocols.")
            return False
            
        return True

    def calculate_position_size(self, entry_price: float, atr: float, direction: str) -> Optional:
        """
        Calculates geometric position sizes mathematically adjusted for localized 
        volatility (ATR), enforcing the ten-dollar risk pivot and leverage truncation.
        """
        # Immediately abort if the portfolio is saturated or in critical drawdown
        if not self.can_open_new_trade():
            return None

        # Calculate the absolute distance to the stop loss based on the configured multiplier
        sl_distance = atr * settings.STOP_LOSS_ATR_MULTIPLIER
        
        if direction.upper() == "LONG":
            stop_loss = entry_price - sl_distance
        elif direction.upper() == "SHORT":
            stop_loss = entry_price + sl_distance
        else:
            self.logger.error(f"Invalid directional parameter received: {direction}")
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
            self.logger.warning(f"Leverage ceiling breached. Truncating theoretical exposure from ${theoretical_usd_value:.2f} to ${max_usd_exposure:.2f}")
            actual_usd = max_usd_exposure
            actual_tokens = actual_usd / entry_price
            
            # Recalculate true risk based on the truncated token volume
            true_risk = actual_tokens * absolute_distance
            self.logger.info(f"Position size forcibly reduced. True algorithmic risk adjusted to ${true_risk:.2f}")
        else:
            actual_tokens = theoretical_tokens
            
        # Calculate Fractional Take-Profit Targets for Consistency Rule mitigation
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
            "tp2": round(tp2, 4)
        }