# scanner/scanner.py
import ccxt
import pandas as pd
import pandas_ta as ta
import time
from datetime import datetime
from config import WATCHLIST, TIMEFRAMES

exchange = ccxt.binance({'enableRateLimit': True})

def fetch_ohlcv(symbol, timeframe, limit=150):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    except:
        return None

def calculate_indicators(df):
    if len(df) < 50:
        return None
    df['ema20'] = ta.ema(df['close'], length=20)
    df['ema50'] = ta.ema(df['close'], length=50)
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    return df

def run_scanner():
    print(f"\n=== Scanner Started - {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n")
    
    btc_df = fetch_ohlcv('BTC/USDT', '1d')
    if btc_df is None:
        print("Failed to fetch BTC data")
        return ""
    
    btc_df = calculate_indicators(btc_df)
    if btc_df is None or btc_df['close'].iloc[-1] <= btc_df['ema50'].iloc[-1]:
        print("BTC not in bullish regime. Staying in cash.")
        return ""

    results = []
    for symbol in WATCHLIST:
        if symbol == 'BTC/USDT':
            continue
        df = fetch_ohlcv(symbol, '1d')
        if df is None:
            continue
        df = calculate_indicators(df)
        if df is None:
            continue
        
        price = df['close'].iloc[-1]
        ema20 = df['ema20'].iloc[-1]
        ema50 = df['ema50'].iloc[-1]
        proximity = abs(price - ema20) / ema20 if ema20 != 0 else 1
        
        if (price > ema50 and ema20 > ema50 and proximity <= 0.06):
            results.append({
                'symbol': symbol,
                'price': round(price, 4),
                'atr': round(df['atr'].iloc[-1], 4)
            })
        time.sleep(1.1)
    
    if results:
        df = pd.DataFrame(results)
        print(df.to_string(index=False))
        return df.to_string(index=False)
    else:
        print("No valid setups found today.")
        return ""

if __name__ == "__main__":
    run_scanner()