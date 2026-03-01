import ccxt.async_support as ccxt  
import pandas as pd  
import pandas_ta as ta  
import asyncio
import socket

# CRITICAL FIX: Disable aiodns on Windows by monkeypatching aiohttp's resolver
# This prevents "Could not contact DNS servers" errors with aiodns DNS resolution
try:
    import aiohttp.resolver
    
    # Create a custom resolver that uses system socket DNS
    class CustomResolver(aiohttp.resolver.AbstractResolver):
        """Custom resolver using system socket DNS instead of aiodns"""
        
        async def resolve(self, host, port=0, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM):
            """Resolve hostname using system socket module in executor"""
            loop = asyncio.get_event_loop()
            # Use executor to run blocking socket.getaddrinfo in thread pool
            try:
                infos = await loop.run_in_executor(None, socket.getaddrinfo, host, port, family, type)
                return [aiohttp.resolver.ResolveResult(
                    family=info[0],
                    type=info[1],
                    proto=info[2],
                    canonname=info[3],
                    sockaddr=info[4]
                ) for info in infos]
            except Exception as e:
                raise aiohttp.resolver.OSError(f"Cannot resolve host {host}") from e
        
        async def close(self):
            """No cleanup needed for socket resolver"""
            pass
    
    # Force aiohttp to use CustomResolver instead of AsyncResolver (aiodns)
    aiohttp.resolver.DefaultResolver = CustomResolver
    
except Exception as e:
    print(f"Warning: Failed to patch DNS resolver: {e}")
    print("Falling back to default aiohttp resolver")
  
class MarketScanner:  
    def __init__(self, watchlist):  
        """
        Initializes the scanner with a watchlist.
        Exchange connection is created lazily when async operation begins.
        """
        self.exchange = None
        self.watchlist = watchlist
        
    async def _init_exchange(self):
        """
        Lazily initializes exchange after event loop is running.
        """
        if self.exchange is None:
            self.exchange = ccxt.binance({
                'enableRateLimit': True
            })  
  
    async def fetch_ohlcv(self, symbol, timeframe, limit=200):  
        """
        Fetches historical OHLCV data asynchronously and structures it into a pandas DataFrame.
        """
        await self._init_exchange()
        ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)  
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])  
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')  
        return df  
  
    def evaluate_confluence(self, df, regime):  
        """
        Calculates dynamic technical indicators (EMA, SMA, ATR) and evaluates regime-based 
        confluences for both Relative Strength and Relative Weakness setups.
        
        For BULLISH regime: price must be above both SMA_50 and EMA_20 (Relative Strength)
        For BEARISH regime: price must be below both SMA_50 and EMA_20 (Relative Weakness)
        
        Returns: (is_valid, dynamic_atr) where dynamic_atr is used for position sizing
        """
        # Calculate dynamic technical indicators via vectorized pandas_ta methods
        df.ta.ema(length=20, append=True)  
        df.ta.sma(length=50, append=True)  
        df.ta.atr(length=14, append=True)  
   
        latest = df.iloc[-1]  
   
        if regime == "BULLISH":  
            # Bullish setup: price above both structural averages
            if latest['close'] > latest['SMA_50'] and latest['close'] >= latest['EMA_20']:  
                return True, latest['ATRr_14']  
   
        elif regime == "BEARISH":  
            # Bearish setup: price below both structural averages (relative weakness signal)
            if latest['close'] < latest['SMA_50'] and latest['close'] <= latest['EMA_20']:  
                return True, latest['ATRr_14']  
   
        return False, 0.0  
  
    async def run_scan(self):  
        """
        Orchestrates the full omnidirectional scan across the watchlist based on 
        the primary BTC macro liquidity regime.
        
        The system uses BTC/USDT 50-day SMA as the macro regime filter:
        - If BTC > SMA_50: BULLISH (authorize long positions)
        - If BTC < SMA_50: BEARISH (authorize short positions)
        """
        try:
            # Determine market regime using BTC 50-day SMA as macro filter
            btc_df = await self.fetch_ohlcv('BTC/USDT', '1d')  
            btc_df.ta.sma(length=50, append=True)  
            btc_latest = btc_df.iloc[-1]  
       
            market_regime = "BULLISH" if btc_latest['close'] > btc_latest['SMA_50'] else "BEARISH"  
            print(f"Current Market Regime Detected: {market_regime}")

            # Initialize valid setups list
            valid_setups = []  
            
            # Scan watchlist for confluence signals
            for symbol in self.watchlist:  
                if symbol == 'BTC/USDT':  
                    continue  
       
                asset_df = await self.fetch_ohlcv(symbol, '1d')  
                is_valid, dynamic_atr = self.evaluate_confluence(asset_df, market_regime)  
       
                if is_valid:  
                    valid_setups.append({  
                        "symbol": symbol,  
                        "regime": market_regime,  
                        "current_price": asset_df.iloc[-1]['close'],  
                        "atr": dynamic_atr  
                    })  
       
            return valid_setups
        finally:
            # Properly close exchange connection and async resources
            await self.exchange.close()


if __name__ == "__main__":
    """
    Isolated Phase 2 validation: Run the scanner in isolation prior to integration with main.py
    """
    import sys
    import os
    
    # Add workspace root to path to import config module
    workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, workspace_root)
    
    from config.settings import WATCHLIST
    
    print("=" * 80)
    print("TRADE_ORACLE Phase 2: Market Scanner Isolated Validation")
    print("=" * 80)
    print(f"Scanning watchlist: {WATCHLIST}\n")
    
    scanner = MarketScanner(WATCHLIST)
    results = asyncio.run(scanner.run_scan())
    
    print("\n" + "=" * 80)
    print("SCAN RESULTS:")
    print("=" * 80)
    
    if results:
        for setup in results:
            print(f"\n✓ Valid Setup Detected:")
            print(f"  Symbol: {setup['symbol']}")
            print(f"  Regime: {setup['regime']}")
            print(f"  Current Price: ${setup['current_price']:.2f}")
            print(f"  Dynamic ATR: {setup['atr']:.4f}")
    else:
        print("\nℹ No confluence setups detected in current market regime.")
    
    print("\n" + "=" * 80)
    print("Diagnostic Complete. Scanner ready for integration with risk_manager.py")
    print("=" * 80)