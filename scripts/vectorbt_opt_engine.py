"""
Lightweight, memory-conscious VectorBT engine skeleton with a robust fallback path.
- Default timeframe: Daily (1D) — optimized for 8GB laptop and per-symbol sweeps.
- Uses `scripts/vectorbt_helpers.py` for entry/exit generation and a simple backtest fallback.

Usage (smoke):
    python scripts/vectorbt_opt_engine.py --symbol BTC/USDT --chunk-size 50 --test-only
"""

import os
import sys
import argparse
import itertools
import gc
import math

import numpy as np
import pandas as pd

# Make sure helpers in same folder importable when running as `python scripts/vectorbt_opt_engine.py`
SCRIPT_DIR = os.path.dirname(__file__)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    import vectorbt as vbt
    VBT_AVAILABLE = True
except Exception:
    VBT_AVAILABLE = False

from vectorbt_helpers import confluence, simple_backtest


def ensure_results_dir():
    os.makedirs('results', exist_ok=True)


def build_grid(preset='conservative', tf='1D'):
    """
    Return a parameter grid depending on preset and timeframe.
    - 'conservative' is small and fast (used for smoke tests / low RAM)
    - 'full' expands ranges to the original optimization grid
    """
    if preset == 'conservative':
        # small grid for quick iteration
        sma_windows = [40, 50, 60]
        ema_windows = [15, 20, 25]
        fib_mins = [0.50, 0.618]
        fib_maxs = [0.618, 0.786]
        rw_thresholds = [0.01, 0.03, 0.05]
        ema_buffers = [0.005, 0.01]
    else:
        # 'full' grid tuned to timeframe: Daily uses larger windows
        if tf == '1D':
            sma_windows = [40, 45, 50, 55, 60]
            ema_windows = [15, 18, 20, 22, 25]
            fib_mins = [0.50, 0.55, 0.618]
            fib_maxs = [0.618, 0.70, 0.786]
            rw_thresholds = [0.01, 0.02, 0.03, 0.04, 0.05]
            ema_buffers = [0.005, 0.01, 0.015, 0.02]
        elif tf == '4H':
            sma_windows = [30, 40, 50]
            ema_windows = [12, 15, 20]
            fib_mins = [0.50, 0.55, 0.618]
            fib_maxs = [0.618, 0.70, 0.786]
            rw_thresholds = [0.01, 0.02, 0.03]
            ema_buffers = [0.005, 0.01, 0.015]
        else:  # 1H
            sma_windows = [20, 30, 40, 50, 60]
            ema_windows = [10, 15, 20, 30]
            fib_mins = [0.50, 0.55, 0.618]
            fib_maxs = [0.618, 0.70, 0.786]
            rw_thresholds = [0.01, 0.02, 0.03, 0.04]
            ema_buffers = [0.005, 0.01, 0.015]

    grid = list(itertools.product(sma_windows, ema_windows, fib_mins, fib_maxs, rw_thresholds, ema_buffers))
    return grid


def run_smoke(symbol, df_sym, grid, chunk_size=50, test_only=False, tf='1D'):
    close = df_sym['close'].to_numpy(dtype=np.float32)
    high = df_sym['high'].to_numpy(dtype=np.float32)
    low = df_sym['low'].to_numpy(dtype=np.float32)

    ensure_results_dir()
    out_csv = f'results/oracle_parameter_surface_{tf}.csv'

    # map timeframe to vectorbt freq string
    freq_map = {'1D': 'D', '4H': '4h', '1H': '1h'}
    freq_str = freq_map.get(tf, 'D')

    for i in range(0, len(grid), chunk_size):
        chunk = grid[i:i + chunk_size]
        rows = []
        for p in chunk:
            sma_w, ema_w, fmin, fmax, rw_th, eb = p
            entries, exits = confluence(close, high, low, sma_w, ema_w, fmin, fmax, rw_th, eb)

            # Prefer vectorbt metrics when available, but always compute simple_backtest metrics
            metrics = simple_backtest(close, entries, exits)
            total_return = metrics['total_return']
            total_trades = metrics['total_trades']
            win_rate = metrics['win_rate']
            expectancy = metrics['expectancy']
            sharpe = float('nan')

            if VBT_AVAILABLE:
                try:
                    # vectorbt expects Series with datetime index for nicer outputs
                    close_ser = pd.Series(close, index=df_sym.index)
                    ent_ser = pd.Series(entries, index=df_sym.index)
                    ex_ser = pd.Series(exits, index=df_sym.index)
                    pf = vbt.Portfolio.from_signals(close_ser, ent_ser, ex_ser, freq=freq_str, init_cash=10000, fees=0.0005)
                    # Some methods return scalars or arrays; coerce safely
                    try:
                        total_return = float(pf.total_return())
                    except Exception:
                        total_return = float('nan')
                    try:
                        sharpe = float(pf.sharpe())
                    except Exception:
                        sharpe = float('nan')
                except Exception:
                    # if vectorbt fails for this param, keep fallback metrics
                    pass

            row = {
                'symbol': symbol,
                'sma': int(sma_w), 'ema': int(ema_w),
                'fib_min': float(fmin), 'fib_max': float(fmax),
                'rw': float(rw_th), 'eb': float(eb),
                'total_return': float(total_return), 'sharpe': float(sharpe),
                'total_trades': int(total_trades), 'win_rate': float(win_rate),
                'expectancy': float(expectancy)
            }
            rows.append(row)

        # write chunk outputs (include timeframe in filename to avoid collisions)
        # include sanitized symbol in chunk filename so per-symbol runs don't overwrite
        symbol_safe = symbol.replace('/', '_').replace(':', '_')
        chunk_file = f'results/chunk_{tf}_{symbol_safe}_{i//chunk_size}.parquet'
        pd.DataFrame(rows).to_parquet(chunk_file, index=False)
        pd.DataFrame(rows).to_csv(out_csv, mode='a', header=not os.path.exists(out_csv), index=False)

        print(f"Wrote chunk {i//chunk_size} ({len(rows)} rows) -> {chunk_file}")
        rows = []
        gc.collect()

        if test_only:
            print("Test-only flag set; stopping after first chunk.")
            break


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--symbol', default='BTC/USDT')
    p.add_argument('--chunk-size', type=int, default=50)
    p.add_argument('--test-only', action='store_true')
    p.add_argument('--timeframe', choices=['1D', '4H', '1H'], default='1D')
    p.add_argument('--grid', choices=['conservative', 'full'], default='conservative', help='Grid preset to use')
    p.add_argument('--all-symbols', action='store_true', help='Run sweep for all symbols present in the data file')
    p.add_argument('--timeframes', default=None, help='Comma-separated timeframes to run (e.g. "1D,4H,1H")')
    args = p.parse_args()

    tf = args.timeframe
    grid_preset = args.grid
    all_symbols = args.all_symbols
    timeframes = [t.strip() for t in args.timeframes.split(',')] if args.timeframes else [tf]
    # iterate requested timeframes and symbols
    for run_tf in timeframes:
        if run_tf == '1D':
            data_path = os.path.join('data', 'market_data_1D.parquet')
        elif run_tf == '4H':
            data_path = os.path.join('data', 'market_data_4H.parquet')
        else:
            data_path = os.path.join('data', 'market_data_1H.parquet')

        if not os.path.exists(data_path):
            print(f"Data file not found: {data_path}. Please run scripts/fetch_data.py first.")
            continue

        df = pd.read_parquet(data_path)
        symbols = [args.symbol]
        if all_symbols:
            if 'symbol' in df.columns:
                symbols = sorted(df['symbol'].unique())
            else:
                symbols = [args.symbol]

        grid = build_grid(preset=grid_preset, tf=run_tf)
        print(f"Running timeframe {run_tf}: parameter grid size {len(grid)}; chunk_size={args.chunk_size}; symbols={symbols}")

        # remove previous outputs for this timeframe to avoid duplicates
        for f in os.listdir('results'):
            if f.startswith(f'oracle_parameter_surface_{run_tf}') or f.startswith(f'chunk_{run_tf}_'):
                try:
                    os.remove(os.path.join('results', f))
                except Exception:
                    pass

        for symbol in symbols:
            if 'symbol' in df.columns:
                df_sym = df[df['symbol'] == symbol].set_index('timestamp').sort_index()
            else:
                df_sym = df.set_index('timestamp').sort_index()

            print(f"Starting sweep for {symbol} on {run_tf} (rows={len(df_sym)})")
            run_smoke(symbol, df_sym, grid, chunk_size=args.chunk_size, test_only=args.test_only, tf=run_tf)


if __name__ == '__main__':
    main()
