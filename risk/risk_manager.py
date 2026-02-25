# risk/risk_manager.py
import pandas as pd

def calculate_position_size(entry_price: float, stop_loss: float, risk_amount: float = 25.0) -> float:
    """
    Calculate exact position size so that if stop is hit, you lose exactly $25 (0.5%)
    """
    if stop_loss >= entry_price:
        return 0.0  # Invalid stop
    
    risk_per_unit = entry_price - stop_loss
    position_size = risk_amount / risk_per_unit
    return round(position_size, 6)  # crypto precision

def calculate_atr_stops(entry_price: float, atr_4h: float, multiplier_sl: float = 1.5, 
                       multiplier_tp1: float = 2.0, multiplier_tp2: float = 3.5):
    """
    Calculate dynamic ATR-based stops and targets
    """
    stop_loss = entry_price - (multiplier_sl * atr_4h)
    tp1 = entry_price + (multiplier_tp1 * atr_4h)
    tp2 = entry_price + (multiplier_tp2 * atr_4h)
    
    return {
        'stop_loss': round(stop_loss, 4),
        'tp1': round(tp1, 4),
        'tp2': round(tp2, 4)
    }

def validate_trade_risk(account_balance: float, risk_per_trade: float = 0.005):
    """Validate risk is within safe limits"""
    max_risk = account_balance * risk_per_trade
    return max_risk

# Test function
if __name__ == "__main__":
    # Example usage
    entry = 62500
    atr = 850
    risk_amount = 25.0
    
    stops = calculate_atr_stops(entry, atr)
    size = calculate_position_size(entry, stops['stop_loss'], risk_amount)
    
    print(f"Entry: ${entry}")
    print(f"Stop Loss: ${stops['stop_loss']}")
    print(f"TP1: ${stops['tp1']}")
    print(f"TP2: ${stops['tp2']}")
    print(f"Position Size: {size} BTC")