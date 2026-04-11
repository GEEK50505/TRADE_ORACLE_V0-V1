import ccxt.async_support as ccxt  
import pandas as pd  
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

    def enrich_indicator_frame(self, df):
        """
        Compute the baseline structural indicators used by both the legacy scan logic
        and the richer LangGraph adapter bridge.
        """
        enriched = df.copy()
        if 'EMA_20' not in enriched.columns:
            enriched['EMA_20'] = enriched['close'].ewm(span=20, adjust=False).mean()
        if 'SMA_50' not in enriched.columns:
            enriched['SMA_50'] = enriched['close'].rolling(window=50, min_periods=1).mean()
        if 'ATRr_14' not in enriched.columns:
            previous_close = enriched['close'].shift(1)
            true_range = pd.concat(
                [
                    enriched['high'] - enriched['low'],
                    (enriched['high'] - previous_close).abs(),
                    (enriched['low'] - previous_close).abs(),
                ],
                axis=1,
            ).max(axis=1)
            enriched['ATRr_14'] = true_range.rolling(window=14, min_periods=1).mean()
        return enriched

    @staticmethod
    def _safe_float(value, default=0.0):
        try:
            if pd.isna(value):
                return float(default)
            return float(value)
        except Exception:
            return float(default)

    def calculate_fibonacci_convergence_proximity(self, df, lookback=50):
        """
        Estimate how close price is to the nearest major retracement level over the
        recent structural swing range. Lower is better.
        """
        recent = df.tail(lookback)
        if recent.empty:
            return 1.0

        recent_high = self._safe_float(recent['high'].max(), default=0.0)
        recent_low = self._safe_float(recent['low'].min(), default=0.0)
        latest_close = self._safe_float(recent.iloc[-1]['close'], default=0.0)
        swing_range = recent_high - recent_low

        if latest_close <= 0.0 or swing_range <= 0.0:
            return 1.0

        fib_levels = [
            recent_high - swing_range * 0.382,
            recent_high - swing_range * 0.500,
            recent_high - swing_range * 0.618,
        ]
        return min(abs(latest_close - level) / latest_close for level in fib_levels)

    def calculate_setup_quality(self, *, regime, close_price, ema_20, sma_50, dynamic_atr, fib_proximity):
        """
        Convert the structural snapshot into a simple 0-1 quality score.
        """
        close_price = self._safe_float(close_price, default=0.0)
        ema_20 = self._safe_float(ema_20, default=0.0)
        sma_50 = self._safe_float(sma_50, default=0.0)
        dynamic_atr = self._safe_float(dynamic_atr, default=0.0)
        fib_proximity = self._safe_float(fib_proximity, default=1.0)

        if close_price <= 0.0:
            return 0.0

        if regime == "BULLISH":
            regime_alignment = 1.0 if close_price > sma_50 and close_price >= ema_20 else 0.0
        elif regime == "BEARISH":
            regime_alignment = 1.0 if close_price < sma_50 and close_price <= ema_20 else 0.0
        else:
            regime_alignment = 0.0

        ema_cluster_distance = abs(close_price - ema_20) / close_price if ema_20 > 0.0 else 1.0
        ema_score = max(0.0, 1.0 - min(ema_cluster_distance / 0.05, 1.0))
        fib_score = max(0.0, 1.0 - min(fib_proximity / 0.05, 1.0))

        atr_ratio = dynamic_atr / close_price
        if 0.0 < atr_ratio <= 0.08:
            atr_score = 1.0
        elif atr_ratio <= 0.12:
            atr_score = max(0.0, 1.0 - ((atr_ratio - 0.08) / 0.04))
        else:
            atr_score = 0.0

        setup_quality = (
            0.45 * regime_alignment
            + 0.25 * fib_score
            + 0.20 * ema_score
            + 0.10 * atr_score
        )
        return round(max(0.0, min(setup_quality, 1.0)), 4)

    def build_setup_payload(self, symbol, regime, df, timeframe="1d"):
        """
        Build the richer scanner payload while preserving the legacy keys consumed by
        the current execution pipeline.
        """
        enriched = self.enrich_indicator_frame(df)
        latest = enriched.iloc[-1]

        close_price = self._safe_float(latest['close'])
        ema_20 = self._safe_float(latest.get('EMA_20'))
        sma_50 = self._safe_float(latest.get('SMA_50'))
        dynamic_atr = self._safe_float(latest.get('ATRr_14'))
        fib_proximity = self.calculate_fibonacci_convergence_proximity(enriched)
        ema_cluster_distance = abs(close_price - ema_20) / close_price if close_price > 0.0 and ema_20 > 0.0 else 1.0
        setup_quality = self.calculate_setup_quality(
            regime=regime,
            close_price=close_price,
            ema_20=ema_20,
            sma_50=sma_50,
            dynamic_atr=dynamic_atr,
            fib_proximity=fib_proximity,
        )

        if regime == "BULLISH":
            structural_bias = "relative_strength"
            ema_confirmed = close_price >= ema_20
            sma_confirmed = close_price > sma_50
        else:
            structural_bias = "relative_weakness"
            ema_confirmed = close_price <= ema_20
            sma_confirmed = close_price < sma_50

        narrative_tags = [
            "scanner_structural_confluence",
            f"scanner_regime_{regime.lower()}",
            structural_bias,
        ]
        if fib_proximity <= 0.02:
            narrative_tags.append("fib_confluence_strong")
        if ema_confirmed:
            narrative_tags.append("ema20_confirmed")
        if sma_confirmed:
            narrative_tags.append("sma50_confirmed")

        rationale = (
            f"Phase 2 {timeframe.upper()} {structural_bias} setup detected for {symbol}. "
            f"Close={close_price:.4f}, EMA20={ema_20:.4f}, SMA50={sma_50:.4f}, ATR={dynamic_atr:.4f}, "
            f"fib_proximity={fib_proximity:.4f}, quality={setup_quality:.4f}."
        )

        return {
            "symbol": symbol,
            "regime": regime,
            "current_price": close_price,
            "atr": dynamic_atr,
            "timeframe": timeframe,
            "fibonacci_convergence_proximity": round(fib_proximity, 6),
            "ema_cluster_distance": round(ema_cluster_distance, 6),
            "setup_quality": setup_quality,
            "rationale": rationale,
            "narrative_tags": narrative_tags,
            "tokenomics_watch": {},
            "scanner_metadata": {
                "source": "phase2_market_scanner",
                "structural_bias": structural_bias,
                "ema_20": round(ema_20, 6),
                "sma_50": round(sma_50, 6),
                "ema_confirmed": ema_confirmed,
                "sma_confirmed": sma_confirmed,
                "fib_lookback": 50,
            },
        }
  
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
        enriched = self.enrich_indicator_frame(df)
   
        latest = enriched.iloc[-1]  
   
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
            btc_df['SMA_50'] = btc_df['close'].rolling(window=50, min_periods=1).mean()
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
                    setup_payload = self.build_setup_payload(symbol, market_regime, asset_df, timeframe='1d')
                    setup_payload["atr"] = dynamic_atr
                    valid_setups.append(setup_payload)  
       
            return valid_setups
        finally:
            # Properly close exchange connection and async resources
            if self.exchange is not None:
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
            print(f"  Fib Proximity: {setup['fibonacci_convergence_proximity']:.4f}")
            print(f"  EMA Distance: {setup['ema_cluster_distance']:.4f}")
            print(f"  Setup Quality: {setup['setup_quality']:.4f}")
    else:
        print("\nℹ No confluence setups detected in current market regime.")
    
    print("\n" + "=" * 80)
    print("Diagnostic Complete. Scanner ready for integration with risk_manager.py")
    print("=" * 80)
