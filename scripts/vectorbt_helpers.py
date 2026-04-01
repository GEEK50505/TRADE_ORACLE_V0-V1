"""
Lightweight helper utilities for Sub-Phase 2 sweeps.
Provides a deterministic, dependency-minimal fallback (numpy/pandas) so smoke runs work
even when `vectorbt` or `numba` are not installed.
"""

import numpy as np


def _sma(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.size
    out = np.full(n, np.nan, dtype=np.float32)
    if window <= 0:
        return out
    if window <= n:
        kernel = np.ones(window, dtype=np.float32) / float(window)
        valid = np.convolve(arr.astype(np.float32), kernel, mode="valid")
        out[window - 1 :] = valid
    return out


def _ema(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.size
    out = np.full(n, np.nan, dtype=np.float32)
    if window <= 0:
        return out
    alpha = 2.0 / (window + 1.0)
    out[0] = arr[0]
    for i in range(1, n):
        out[i] = alpha * arr[i] + (1.0 - alpha) * out[i - 1]
    return out


def confluence(close, high, low, sma_window=50, ema_window=20, fib_min=0.5, fib_max=0.618, rw_threshold=0.02, ema_buffer=0.01, rw_lookback=14):
    """
    Compute entry/exit boolean arrays for a single parameter tuple.
    This is a straightforward, easy-to-read implementation (not numba-optimized).

    Inputs: numpy arrays (close, high, low) as float32/float64.
    Returns: entries, exits boolean numpy arrays of same length.
    """
    close = np.asarray(close, dtype=np.float32)
    high = np.asarray(high, dtype=np.float32)
    low = np.asarray(low, dtype=np.float32)

    n = close.size
    entries = np.zeros(n, dtype=np.bool_)
    exits = np.zeros(n, dtype=np.bool_)

    sma = _sma(close, int(sma_window))
    ema = _ema(close, int(ema_window))

    lookback = int(max(sma_window, ema_window, 30, rw_lookback))

    for i in range(lookback, n):
        window_high = high[i - 30 : i].max() if i - 30 >= 0 else high[:i].max()
        window_low = low[i - 30 : i].min() if i - 30 >= 0 else low[:i].min()
        if window_high == window_low:
            continue
        retracement = (window_high - close[i]) / (window_high - window_low)

        if i - rw_lookback >= 0 and close[i - rw_lookback] != 0:
            rw = (close[i - rw_lookback] - close[i]) / close[i - rw_lookback]
        else:
            rw = 0.0

        regime_long = not np.isnan(sma[i]) and (close[i] > sma[i])
        fib_zone = (retracement >= fib_min) and (retracement <= fib_max)
        ema_distance = abs(close[i] - ema[i]) / (close[i] if close[i] != 0 else 1.0)
        ema_convergence = ema_distance <= ema_buffer
        weakness_check = rw >= rw_threshold

        if regime_long and fib_zone and ema_convergence and weakness_check:
            entries[i] = True
        if not np.isnan(ema[i]) and close[i] < ema[i]:
            exits[i] = True

    return entries, exits


def simple_backtest(close, entries, exits, init_cash=10000.0, fee=0.0005):
    """
    Simple sequential backtest to compute a few scalar metrics without external deps.
    - Assumes single long trades only (entry->exit), fixed notional = `init_cash` per trade
      (so P&L is expressed in dollars relative to `init_cash`).

    Returns dict: total_trades, win_rate, expectancy (avg $ per trade), total_return (fraction of init_cash).
    """
    close = np.asarray(close, dtype=np.float32)
    entries = np.asarray(entries, dtype=bool)
    exits = np.asarray(exits, dtype=bool)

    trades = []
    in_pos = False
    entry_price = 0.0

    for i in range(close.size):
        if entries[i] and not in_pos:
            entry_price = close[i]
            in_pos = True
        if exits[i] and in_pos:
            exit_price = close[i]
            pnl_pct = (exit_price - entry_price) / entry_price - 2.0 * fee
            pnl = init_cash * pnl_pct
            trades.append(pnl)
            in_pos = False

    # close any open position at the last price
    if in_pos:
        exit_price = float(close[-1])
        pnl_pct = (exit_price - entry_price) / entry_price - 2.0 * fee
        trades.append(init_cash * pnl_pct)

    total_trades = len(trades)
    if total_trades == 0:
        return {"total_trades": 0, "win_rate": 0.0, "expectancy": 0.0, "total_return": 0.0}

    wins = sum(1 for p in trades if p > 0)
    win_rate = float(wins) / float(total_trades)
    expectancy = float(sum(trades)) / float(total_trades)
    total_return = float(sum(trades)) / float(init_cash)

    return {"total_trades": total_trades, "win_rate": win_rate, "expectancy": expectancy, "total_return": total_return}
