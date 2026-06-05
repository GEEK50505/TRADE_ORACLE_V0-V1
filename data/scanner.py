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

def rolling_mean(series: pd.Series, window: int) -> pd.Series:
    """Simple rolling mean with full-window readiness."""
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    """EMA with the same recursive shape used elsewhere in the repo."""
    return series.ewm(span=window, adjust=False).mean()


def rolling_max(series: pd.Series, window: int) -> pd.Series:
    """Rolling max with full-window readiness."""
    return series.rolling(window=window, min_periods=window).max()


def rolling_min(series: pd.Series, window: int) -> pd.Series:
    """Rolling min with full-window readiness."""
    return series.rolling(window=window, min_periods=window).min()


def true_range(frame: pd.DataFrame) -> pd.Series:
    """Build the True Range series used by the ATR calculation."""
    prev_close = frame["close"].shift(1)
    high_low = frame["high"] - frame["low"]
    high_prev = (frame["high"] - prev_close).abs()
    low_prev = (frame["low"] - prev_close).abs()
    return pd.concat([high_low, high_prev, low_prev], axis=1).max(axis=1)


def atr_wilder(frame: pd.DataFrame, period: int) -> pd.Series:
    """Wilder-smoothed ATR, matching Backtrader's ATR family closely."""
    tr = true_range(frame)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


STRATEGY_CONFIG = {
    "AVAX/USDT": {
        "direction": "BUY",
        "sma": 35,
        "ema": 20,
        "fib_floor": 0.236,
        "fib_band": 0.436,
        "rw": 0.002,
        "eb": 0.068,
        "rw_lookback": 21,
        "confirm_ema_period": 15,
        "confirm_min_distance": 0.008,
    },
    "DOGE/USDT": {
        "direction": "SELL",
        "sma": 70,
        "ema": 20,
        "fib_floor": 0.236,
        "fib_band": 0.686,
        "rw": 0.05,
        "eb": 0.028,
        "rw_lookback": 10,
        "confirm_ema_period": 20,
        "confirm_min_distance": 0.004,
    }
}
  
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
  
    def build_setup_payload_4h(
        self,
        symbol,
        direction,
        close_1d,
        ema_1d,
        sma_1d,
        atr_1d,
        fib_proximity,
        ema_distance_1d,
        setup_quality,
        current_price_4h,
        rationale,
        narrative_tags,
    ):
        """
        Build the richer scanner payload while preserving the legacy keys consumed by
        the current execution pipeline, updated for the Phase 2 4H confirmation strategy.
        """
        regime = "BULLISH" if direction == "BUY" else "BEARISH"
        structural_bias = "relative_strength" if direction == "BUY" else "relative_weakness"
        ema_confirmed = close_1d >= ema_1d if direction == "BUY" else close_1d <= ema_1d
        sma_confirmed = close_1d > sma_1d if direction == "BUY" else close_1d < sma_1d

        candidate_portfolio = [
            {
                "param_id": "combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004",
                "long_symbol": "AVAX/USDT",
                "short_symbol": "DOGE/USDT",
                "timeframe": "4h",
                "expectancy": 1.0542,
                "max_dd_pct": 1.7764,
                "overall_survival": True,
            },
            {
                "param_id": "combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004",
                "long_symbol": "AVAX/USDT",
                "short_symbol": "DOGE/USDT",
                "timeframe": "4h",
                "expectancy": 1.0542,
                "max_dd_pct": 2.0279,
                "overall_survival": True,
            },
            {
                "param_id": "combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004",
                "long_symbol": "AVAX/USDT",
                "short_symbol": "DOGE/USDT",
                "timeframe": "4h",
                "expectancy": 1.0542,
                "max_dd_pct": 2.1053,
                "overall_survival": True,
            },
        ]

        return {
            "symbol": symbol,
            "regime": regime,
            "current_price": current_price_4h,
            "atr": atr_1d,
            "timeframe": "4h",
            "fibonacci_convergence_proximity": round(fib_proximity, 6),
            "ema_cluster_distance": round(ema_distance_1d, 6),
            "setup_quality": setup_quality,
            "rationale": rationale,
            "narrative_tags": narrative_tags,
            "candidate_portfolio": candidate_portfolio,
            "portfolio_expectancy": 1.0542,
            "portfolio_max_dd_pct": 2.9641,
            "portfolio_consistency_score": 3.8893,
            "portfolio_overall_survival": True,
            "tokenomics_watch": {},
            "scanner_metadata": {
                "source": "phase2_market_scanner",
                "structural_bias": structural_bias,
                "ema_20": round(ema_1d, 6),
                "sma_50": round(sma_1d, 6),
                "ema_confirmed": ema_confirmed,
                "sma_confirmed": sma_confirmed,
                "fib_lookback": 30,
            },
        }

    async def run_scan(self):  
        """
        Orchestrates the full scan across the watchlist using the optimized
        Daily + 4H confirmation strategy for AVAX/USDT and DOGE/USDT.
        """
        try:
            print("Starting Backtested 4H Confirmation Strategy scan...")
            valid_setups = []  
            
            for symbol in self.watchlist:  
                if symbol not in STRATEGY_CONFIG:
                    continue  

                cfg = STRATEGY_CONFIG[symbol]
                direction = cfg["direction"]

                print(f"Evaluating {symbol} for {direction} setup...")

                # Fetch Daily and 4H OHLCV data
                df_1d = await self.fetch_ohlcv(symbol, '1d', limit=200)
                df_4h = await self.fetch_ohlcv(symbol, '4h', limit=200)

                min_required_1d = max(cfg["sma"], cfg["ema"], 30, cfg["rw_lookback"], 14) + 1
                if len(df_1d) < min_required_1d:
                    print(f"Skipping {symbol}: insufficient 1d bars ({len(df_1d)} < {min_required_1d})")
                    continue

                min_required_4h = max(1, int(cfg["confirm_ema_period"])) + 1
                if len(df_4h) < min_required_4h:
                    print(f"Skipping {symbol}: insufficient 4h bars ({len(df_4h)} < {min_required_4h})")
                    continue

                # 1D calculations
                working_1d = df_1d.copy()
                working_1d["sma_calc"] = rolling_mean(working_1d["close"], cfg["sma"])
                working_1d["ema_calc"] = ema(working_1d["close"], cfg["ema"])
                working_1d["atr_calc"] = atr_wilder(working_1d, 14)
                working_1d["high30_calc"] = rolling_max(working_1d["high"], 30)
                working_1d["low30_calc"] = rolling_min(working_1d["low"], 30)
                working_1d["prev_close_calc"] = working_1d["close"].shift(cfg["rw_lookback"])

                latest_1d = working_1d.iloc[-1]
                close_1d = float(latest_1d["close"])
                sma_1d = float(latest_1d["sma_calc"])
                ema_1d = float(latest_1d["ema_calc"])
                atr_1d = float(latest_1d["atr_calc"])
                high30_1d = float(latest_1d["high30_calc"])
                low30_1d = float(latest_1d["low30_calc"])
                prev_close_1d = float(latest_1d["prev_close_calc"])

                if any(pd.isna(val) for val in [close_1d, sma_1d, ema_1d, atr_1d, high30_1d, low30_1d, prev_close_1d]):
                    print(f"Skipping {symbol}: NaN values found in daily indicators")
                    continue
                if close_1d <= 0.0 or atr_1d <= 0.0 or high30_1d <= low30_1d or prev_close_1d <= 0.0:
                    print(f"Skipping {symbol}: invalid numeric values in daily indicators")
                    continue

                ema_distance_1d = abs(close_1d - ema_1d) / close_1d

                # 4H calculations
                working_4h = df_4h.copy()
                working_4h["confirm_ema_calc"] = ema(working_4h["close"], cfg["confirm_ema_period"])
                latest_4h = working_4h.iloc[-1]
                close_4h = float(latest_4h["close"])
                confirm_ema_4h = float(latest_4h["confirm_ema_calc"])

                if any(pd.isna(val) for val in [close_4h, confirm_ema_4h]):
                    print(f"Skipping {symbol}: NaN values found in 4h indicators")
                    continue
                if close_4h <= 0.0 or confirm_ema_4h <= 0.0:
                    print(f"Skipping {symbol}: invalid numeric values in 4h indicators")
                    continue

                # Evaluate confluence
                daily_confluence = False
                confirm_valid = False
                summary = ""
                metrics_summary = ""

                if direction == "BUY":
                    retracement = (high30_1d - close_1d) / (high30_1d - low30_1d)
                    rw_value = (prev_close_1d - close_1d) / prev_close_1d
                    daily_confluence = (
                        close_1d > sma_1d
                        and cfg["fib_floor"] <= retracement <= cfg["fib_band"]
                        and ema_distance_1d <= cfg["eb"]
                        and rw_value >= cfg["rw"]
                    )
                    confirm_distance = (close_4h - confirm_ema_4h) / confirm_ema_4h
                    confirm_valid = bool(close_4h > confirm_ema_4h and confirm_distance >= cfg["confirm_min_distance"])
                    summary = (
                        f"Daily: close {close_1d:.4f} > SMA {sma_1d:.4f}; "
                        f"retracement {retracement:.4f} in [{cfg['fib_floor']:.3f}, {cfg['fib_band']:.3f}]; "
                        f"EMA distance {ema_distance_1d:.4f} <= {cfg['eb']:.4f}; "
                        f"RW {rw_value:.4f} >= {cfg['rw']:.4f}"
                    )
                    metrics_summary = f"4H confirm close {close_4h:.4f} > EMA {confirm_ema_4h:.4f}; distance {confirm_distance:.4f} >= {cfg['confirm_min_distance']:.4f}"

                else: # SELL
                    bounce_retracement = (close_1d - low30_1d) / (high30_1d - low30_1d)
                    downside_momentum = (prev_close_1d - close_1d) / prev_close_1d
                    daily_confluence = (
                        close_1d < sma_1d
                        and cfg["fib_floor"] <= bounce_retracement <= cfg["fib_band"]
                        and ema_distance_1d <= cfg["eb"]
                        and downside_momentum >= cfg["rw"]
                    )
                    confirm_distance = (confirm_ema_4h - close_4h) / confirm_ema_4h
                    confirm_valid = bool(close_4h < confirm_ema_4h and confirm_distance >= cfg["confirm_min_distance"])
                    summary = (
                        f"Daily: close {close_1d:.4f} < SMA {sma_1d:.4f}; "
                        f"bounce retracement {bounce_retracement:.4f} in [{cfg['fib_floor']:.3f}, {cfg['fib_band']:.3f}]; "
                        f"EMA distance {ema_distance_1d:.4f} <= {cfg['eb']:.4f}; "
                        f"downside momentum {downside_momentum:.4f} >= {cfg['rw']:.4f}"
                    )
                    metrics_summary = f"4H confirm close {close_4h:.4f} < EMA {confirm_ema_4h:.4f}; distance {confirm_distance:.4f} >= {cfg['confirm_min_distance']:.4f}"

                print(f"  -> Confluence Daily={daily_confluence}, 4H={confirm_valid}")

                if daily_confluence and confirm_valid:
                    fib_proximity = self.calculate_fibonacci_convergence_proximity(working_1d, lookback=30)
                    setup_quality = self.calculate_setup_quality(
                        regime="BULLISH" if direction == "BUY" else "BEARISH",
                        close_price=close_1d,
                        ema_20=ema_1d,
                        sma_50=sma_1d,
                        dynamic_atr=atr_1d,
                        fib_proximity=fib_proximity,
                    )
                    
                    narrative_tags = [
                        "scanner_structural_confluence",
                        f"scanner_regime_{'bullish' if direction == 'BUY' else 'bearish'}",
                        "relative_strength" if direction == "BUY" else "relative_weakness",
                        "maven_rule_survivor",
                    ]
                    if fib_proximity <= 0.02:
                        narrative_tags.append("fib_confluence_strong")
                    if close_1d >= ema_1d if direction == "BUY" else close_1d <= ema_1d:
                        narrative_tags.append("ema20_confirmed")
                    if close_1d > sma_1d if direction == "BUY" else close_1d < sma_1d:
                        narrative_tags.append("sma_confirmed")

                    rationale = f"Phase 2 4H {'BUY' if direction == 'BUY' else 'SELL'} setup detected for {symbol}. {summary}; {metrics_summary}."
                    
                    setup_payload = self.build_setup_payload_4h(
                        symbol=symbol,
                        direction=direction,
                        close_1d=close_1d,
                        ema_1d=ema_1d,
                        sma_1d=sma_1d,
                        atr_1d=atr_1d,
                        fib_proximity=fib_proximity,
                        ema_distance_1d=ema_distance_1d,
                        setup_quality=setup_quality,
                        current_price_4h=close_4h,
                        rationale=rationale,
                        narrative_tags=narrative_tags,
                    )
                    valid_setups.append(setup_payload)
            
            return valid_setups
        finally:
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
            print(f"\n[+] Valid Setup Detected:")
            print(f"  Symbol: {setup['symbol']}")
            print(f"  Regime: {setup['regime']}")
            print(f"  Current Price: ${setup['current_price']:.2f}")
            print(f"  Dynamic ATR: {setup['atr']:.4f}")
            print(f"  Fib Proximity: {setup['fibonacci_convergence_proximity']:.4f}")
            print(f"  EMA Distance: {setup['ema_cluster_distance']:.4f}")
            print(f"  Setup Quality: {setup['setup_quality']:.4f}")
    else:
        print("\n[i] No confluence setups detected in current market regime.")
    
    print("\n" + "=" * 80)
    print("Diagnostic Complete. Scanner ready for integration with risk_manager.py")
    print("=" * 80)
