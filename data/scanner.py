import ccxt.async_support as ccxt
import pandas as pd
import pandas_ta as ta
import asyncio

class MarketScanner:
    def __init__(self, watchlist):
        self.exchange = ccxt.binance({'enableRateLimit': True})
        self.watchlist = watchlist

    async def fetch_ohlcv(self, symbol, timeframe, limit=200):
        ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    def evaluate_confluence(self, df, regime):
        # Calculate dynamic technicals
        df.ta.ema(length=20, append=True)
        df.ta.sma(length=50, append=True)
        df.ta.atr(length=14, append=True)
        
        latest = df.iloc[-1]
        
        if regime == "BULLISH":
            if latest['close'] > latest and latest['close'] >= latest['EMA_20']:
                return True, latest
        
        elif regime == "BEARISH":
            if latest['close'] < latest and latest['close'] <= latest['EMA_20']:
                return True, latest
                
        return False, 0.0

    async def run_scan(self):
        btc_df = await self.fetch_ohlcv('BTC/USDT', '1d')
        btc_df.ta.sma(length=50, append=True)
        btc_latest = btc_df.iloc[-1]
        
        market_regime = "BULLISH" if btc_latest['close'] > btc_latest else "BEARISH"
        
        valid_setups =
        for symbol in self.watchlist:
            if symbol == 'BTC/USDT': continue
            
            asset_df = await self.fetch_ohlcv(symbol, '1d')
            is_valid, dynamic_atr = self.evaluate_confluence(asset_df, market_regime)
            
            if is_valid:
                valid_setups.append({
                    "symbol": symbol,
                    "regime": market_regime,
                    "current_price": asset_df.iloc[-1]['close'],
                    "atr": dynamic_atr
                })
        
        await self.exchange.close()
        return valid_setups