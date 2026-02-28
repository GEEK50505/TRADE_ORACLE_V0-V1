class RiskManager:
    def __init__(self, config, current_balance, highest_equity):
        self.balance = current_balance
        self.high_watermark = highest_equity
        self.risk_pct = config.RISK_PER_TRADE
        self.max_leverage = config.MAX_CRYPTO_LEVERAGE
        
    def validate_trailing_drawdown(self):
        # Maven calculates the 3% trailing drop from the highest equity point
        max_allowed_drop = self.high_watermark * 0.03
        current_drawdown = self.high_watermark - self.balance
        
        if current_drawdown >= max_allowed_drop:
            raise Exception(f"CRITICAL HALT: Trailing Drawdown limit breached. DD: ${current_drawdown}")
        return True

    def calculate_position_size(self, entry_price: float, stop_loss: float):
        absolute_risk_usd = self.balance * self.risk_pct
        distance_to_sl = abs(entry_price - stop_loss)
        
        if distance_to_sl == 0:
            return 0.0
            
        theoretical_tokens = absolute_risk_usd / distance_to_sl
        theoretical_usd_value = theoretical_tokens * entry_price
        
        # Enforce Maven's strict 1:2 crypto leverage limit
        max_usd_exposure = self.balance * self.max_leverage
        
        if theoretical_usd_value > max_usd_exposure:
            actual_usd = max_usd_exposure
            actual_tokens = actual_usd / entry_price
        else:
            actual_tokens = theoretical_tokens
            
        return round(actual_tokens, 4)