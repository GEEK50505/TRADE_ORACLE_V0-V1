# main.py - Final integrated controller

from scanner.scanner import run_scanner
from risk.risk_manager import calculate_atr_stops, calculate_position_size
from ai.prompts import get_ranking_prompt
from config import RISK_PER_TRADE

def parse_ai_response(ai_text: str):
    """Parses AI ranking output"""
    lines = [line.strip() for line in ai_text.strip().split('\n') if line.strip()]
    setups = []
    current = {}

    for line in lines:
        if line.startswith('1.') or line.startswith('2.'):
            if current:
                setups.append(current)
            current = {}

        if 'Ticker' in line:
            try:
                current['ticker'] = line.split(':')[1].strip().split()[0]
            except:
                pass
        if 'Conviction' in line or 'Confidence' in line:
            try:
                current['confidence'] = float(line.split(':')[1].strip().split('/')[0])
            except:
                current['confidence'] = 8.0
        if 'Entry' in line:
            try:
                current['entry'] = float(line.split(':')[1].strip().replace('$', '').replace(',', ''))
            except:
                current['entry'] = 0.0
        if 'Stop Loss' in line or 'Stop' in line:
            try:
                current['stop'] = float(line.split(':')[1].strip().replace('$', '').replace(',', ''))
            except:
                current['stop'] = 0.0
        if 'TP1' in line or 'Take Profit 1' in line:
            try:
                current['tp1'] = float(line.split(':')[1].strip().replace('$', '').replace(',', ''))
            except:
                current['tp1'] = 0.0
        if 'TP2' in line or 'Take Profit 2' in line:
            try:
                current['tp2'] = float(line.split(':')[1].strip().replace('$', '').replace(',', ''))
            except:
                current['tp2'] = 0.0

    if current:
        setups.append(current)
    return setups

def main():
    print("🚀 Crypto Swing Trading System Started\n")
    
    print("Scanning for high-probability setups...")
    scanner_output = run_scanner()
    
    if not scanner_output or scanner_output.strip() == "":
        print("No valid setups found today. Staying in cash.\n")
        return
    
    market_regime = "BTC above 50-day EMA, bullish regime, moderate volatility"
    prompt = get_ranking_prompt(scanner_output, market_regime)
    
    print("\n" + "="*80)
    print("COPY & PASTE THIS PROMPT INTO CLAUDE OR GROK")
    print("="*80)
    print(prompt)
    print("="*80)
    
    print("\nPaste the full AI ranking response below and press Enter twice when done:")
    ai_response = []
    while True:
        line = input()
        if line.strip() == "" and len(ai_response) > 0:
            break
        ai_response.append(line)
    
    ai_text = "\n".join(ai_response)
    
    print("\n✅ AI Response Received. Parsing and calculating...\n")
    
    setups = parse_ai_response(ai_text)
    
    if not setups:
        print("Could not parse AI response. Please try again.")
        return
    
    top = setups[0]
    print(f"Top Setup: {top.get('ticker', 'N/A')} | Confidence: {top.get('confidence', 8.0)}/10")
    
    entry = top.get('entry', 62500.0)
    atr = 850.0
    stops = calculate_atr_stops(entry, atr)
    size = calculate_position_size(entry, stops['stop_loss'], RISK_PER_TRADE * 5000)
    
    print("\n" + "-"*70)
    print("FINAL TRADE CALCULATION")
    print("-"*70)
    print(f"Ticker           : {top.get('ticker', 'N/A')}")
    print(f"Entry Price      : ${entry}")
    print(f"Stop Loss        : ${stops['stop_loss']}")
    print(f"Take Profit 1    : ${stops['tp1']}")
    print(f"Take Profit 2    : ${stops['tp2']}")
    print(f"Position Size    : {size} BTC (${size * entry:.2f})")
    print(f"Risk Amount      : ${RISK_PER_TRADE * 5000:.2f}")
    
    print("\n✅ Trade ready to execute in Maven Trading.")

if __name__ == "__main__":
    main()