"""
Wide Daily VectorBT optimization engine (Sub-Phase 2, Pass 1)
- Runs a wider Daily grid across all symbols in `data/market_data_1D.parquet` by default.
- Chunked, per-parameter sequential evaluation using a Numba confluence function if available,
  falling back to the Python helper in `scripts/vectorbt_helpers.py`.
- Writes per-chunk parquet checkpoints and appends to `results/daily_sweep_results.csv`.
- Produces `results/top_daily_parameters.csv` and `results/optimization_summary.md`.

Usage (full run):
    python scripts/vectorbt_optimization_engine.py --all-symbols --chunk-size 200

"""

import os
import sys
import argparse
import itertools
import math
import time
import gc

import numpy as np
import pandas as pd

# allow importing local helpers
SCRIPT_DIR = os.path.dirname(__file__)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from vectorbt_helpers import simple_backtest, confluence as py_confluence

# try optional acceleration
try:
    from numba import njit
    NUMBA_AVAILABLE = True
except Exception:
    NUMBA_AVAILABLE = False

try:
    import vectorbt as vbt
    VBT_AVAILABLE = True
except Exception:
    VBT_AVAILABLE = False


def build_wider_grid():
    # per user's requested relaxations (balanced to ~15k combos)
    sma_windows = [35, 40, 45, 50, 55, 60, 65]
    rw_thresholds = [0.005 * i for i in range(1, 9)]  # 0.005 .. 0.04
    fib_points = [0.382, 0.5, 0.618, 0.7, 0.786]     # produce pairs with fib_min < fib_max
    fib_pairs = [(a, b) for i, a in enumerate(fib_points) for b in fib_points[i+1:]]
    ema_buffers = [0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04]
    rw_lookbacks = [10, 12, 14, 18]
    # fix EMA window to 20 for this pass (keeps complexity down)
    ema_window = 20

    grid = []
    for sma in sma_windows:
        for rw in rw_thresholds:
            for (fmin, fmax) in fib_pairs:
                for eb in ema_buffers:
                    for lb in rw_lookbacks:
                        grid.append((sma, ema_window, fmin, fmax, rw, eb, lb))
    return grid


def build_much_wider_grid():
    # user-requested much more relaxed ranges
    sma_windows = list(range(30, 81, 5))  # 30,35,...,80
    rw_thresholds = [0.003, 0.005, 0.01, 0.02, 0.03, 0.04, 0.05]
    fib_points = [0.236, 0.382, 0.5, 0.618, 0.7, 0.786]
    fib_pairs = [(a, b) for i, a in enumerate(fib_points) for b in fib_points[i + 1 :]]
    ema_buffers = [0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06]
    rw_lookbacks = [8, 10, 12, 14, 18, 21]
    ema_window = 20

    grid = []
    for sma in sma_windows:
        for rw in rw_thresholds:
            for (fmin, fmax) in fib_pairs:
                for eb in ema_buffers:
                    for lb in rw_lookbacks:
                        grid.append((sma, ema_window, fmin, fmax, rw, eb, lb))
    return grid


if NUMBA_AVAILABLE:
    @njit
    def confluence_nb(close, high, low, sma_window, ema_window, fib_min, fib_max, rw_threshold, ema_buffer, rw_lookback):
        n = close.shape[0]
        entries = np.zeros(n, dtype=np.bool_)
        exits = np.zeros(n, dtype=np.bool_)

        # compute SMA via rolling sum
        sma = np.full(n, np.nan, dtype=np.float64)
        s = 0.0
        w = int(sma_window)
        for i in range(n):
            s += close[i]
            if i - w >= 0:
                s -= close[i - w]
            if i >= w - 1:
                sma[i] = s / w

        # compute EMA
        ema = np.full(n, np.nan, dtype=np.float64)
        a = 2.0 / (ema_window + 1.0)
        if n > 0:
            ema[0] = close[0]
        for i in range(1, n):
            ema[i] = a * close[i] + (1 - a) * ema[i - 1]

        lookback = int(max(sma_window, ema_window, 30, rw_lookback))
        for i in range(lookback, n):
            # local high/low over 30 bars
            local_high = -1e12
            local_low = 1e12
            start = i - 30
            if start < 0:
                start = 0
            for k in range(start, i):
                if high[k] > local_high:
                    local_high = high[k]
                if low[k] < local_low:
                    local_low = low[k]

            if local_high == local_low:
                continue
            retracement = (local_high - close[i]) / (local_high - local_low)

            if i - rw_lookback < 0:
                continue
            prev = close[i - rw_lookback]
            if prev == 0:
                continue
            rw = (prev - close[i]) / prev

            regime_long = not (sma[i] != sma[i]) and (close[i] > sma[i])  # nan check
            fib_zone = (retracement >= fib_min) and (retracement <= fib_max)
            ema_distance = abs(close[i] - ema[i]) / close[i] if close[i] != 0 else 0.0
            ema_convergence = ema_distance <= ema_buffer
            weakness_check = rw >= rw_threshold

            if regime_long and fib_zone and ema_convergence and weakness_check:
                entries[i] = True
            if close[i] < ema[i]:
                exits[i] = True

        return entries, exits
else:
    confluence_nb = None


def run_wide_daily(market_path='data/market_data_1D.parquet', out_prefix='results/daily', relaxed=False):
    if not os.path.exists(market_path):
        print('Market data not found:', market_path)
        return

    df_market = pd.read_parquet(market_path)
    symbols = sorted(df_market['symbol'].unique()) if 'symbol' in df_market.columns else [None]

    if relaxed:
        grid = build_much_wider_grid()
        print('Using RELAXED grid: wider ranges and temporary relaxed gates')
    else:
        grid = build_wider_grid()
    total_params = len(grid)
    print(f'Grid size: {total_params} parameter combinations')

    results_csv = f'{out_prefix}_sweep_results.csv'
    # remove existing outputs for a clean run
    try:
        if os.path.exists(results_csv):
            os.remove(results_csv)
    except Exception:
        pass

    chunk_counter = 0
    processed = 0
    start_time = time.time()

    for symbol in symbols:
        symbol_safe = symbol.replace('/', '_') if symbol else 'single'
        df_sym = df_market[df_market['symbol'] == symbol].set_index('timestamp').sort_index()
        close = df_sym['close'].to_numpy(dtype=np.float64)
        high = df_sym['high'].to_numpy(dtype=np.float64)
        low = df_sym['low'].to_numpy(dtype=np.float64)
        n = close.size

        # process in chunks
        chunk_size = ARG_CHUNK_SIZE
        for i in range(0, total_params, chunk_size):
            chunk = grid[i:i + chunk_size]
            rows = []
            for p in chunk:
                sma_w, ema_w, fmin, fmax, rw_th, eb, lb = p
                # compute signals using numba if available, else python helper
                try:
                    if confluence_nb is not None:
                        ent, ex = confluence_nb(close, high, low, sma_w, ema_w, fmin, fmax, rw_th, eb, lb)
                    else:
                        ent, ex = py_confluence(close, high, low, sma_w, ema_w, fmin, fmax, rw_th, eb, lb)

                    # compute metrics via simple_backtest (deterministic and fast)
                    metrics = simple_backtest(close, ent, ex)
                except Exception as e:
                    metrics = {"total_trades": 0, "win_rate": 0.0, "expectancy": 0.0, "total_return": 0.0}

                row = {
                    'symbol': symbol,
                    'sma': int(sma_w), 'ema': int(ema_w),
                    'fib_min': float(fmin), 'fib_max': float(fmax),
                    'rw': float(rw_th), 'eb': float(eb), 'rw_lookback': int(lb),
                    'total_return': float(metrics.get('total_return', 0.0)),
                    'total_trades': int(metrics.get('total_trades', 0)),
                    'win_rate': float(metrics.get('win_rate', 0.0)),
                    'expectancy': float(metrics.get('expectancy', 0.0))
                }
                rows.append(row)

            # checkpoint chunk
            chunk_file = f'{out_prefix}_chunk_{symbol_safe}_{i//chunk_size}.parquet'
            pd.DataFrame(rows).to_parquet(chunk_file, index=False)
            pd.DataFrame(rows).to_csv(results_csv, mode='a', header=not os.path.exists(results_csv), index=False)
            processed += len(rows)
            chunk_counter += 1
            rows = []
            gc.collect()

            elapsed = time.time() - start_time
            print(f'[{symbol}] Finished chunk {i//chunk_size} ({processed}/{total_params*len(symbols) if symbols else total_params} processed), elapsed {elapsed:.1f}s')

    # aggregation done
    df_all = pd.read_csv(results_csv)
    # apply success gates: relaxed run uses temporary relaxed gates requested by user
    if relaxed:
        mask = (df_all['total_trades'] >= 15) & (df_all['win_rate'] >= 0.38) & (df_all['expectancy'] >= 1.2)
    else:
        mask = (df_all['total_trades'] >= 25) & (df_all['win_rate'] >= 0.40) & (df_all['expectancy'] >= 1.8)
    df_pass = df_all[mask].copy()
    df_pass_sorted = df_pass.sort_values(by=['expectancy'], ascending=False)
    top_n = df_pass_sorted.head(50)
    top_csv = f'{out_prefix}_top_daily_parameters.csv'
    top_n.to_csv(top_csv, index=False)

    # write a short summary
    summary = {
        'total_param_combinations': len(df_all),
        'candidates_after_gates': len(df_pass),
        'top_saved': len(top_n),
        'best_expectancy': float(df_all['expectancy'].max()) if not df_all['expectancy'].isna().all() else 0.0,
        'best_win_rate': float(df_all['win_rate'].max()) if not df_all['win_rate'].isna().all() else 0.0,
    }
    with open(f'{out_prefix}_optimization_summary.md', 'w') as fh:
        fh.write('# Daily sweep optimization summary\n\n')
        for k, v in summary.items():
            fh.write(f'- **{k}**: {v}\n')

    print('Sweep complete. Results:')
    print(' - all results:', results_csv)
    print(' - top daily parameters:', top_csv)
    print(' - summary:', f'{out_prefix}_optimization_summary.md')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--market', default='data/market_data_1D.parquet')
    p.add_argument('--chunk-size', type=int, default=200)
    p.add_argument('--relaxed', action='store_true', help='Use the much wider relaxed parameter ranges and relaxed gates')
    p.add_argument('--all-symbols', action='store_true')
    p.add_argument('--symbol', default='BTC/USDT')
    p.add_argument('--test-only', action='store_true')
    args = p.parse_args()

    ARG_CHUNK_SIZE = args.chunk_size

    # if single-symbol mode, adjust symbols selection inside run
    if args.all_symbols:
        out_prefix = 'results/daily_relaxed' if args.relaxed else 'results/daily'
        run_wide_daily(market_path=args.market, out_prefix=out_prefix, relaxed=args.relaxed)
    else:
        # limit to one symbol for test/debug
        df = pd.read_parquet(args.market)
        if 'symbol' in df.columns and args.symbol not in df['symbol'].unique():
            print('Symbol not found in market file:', args.symbol)
            sys.exit(1)
        # create a small wrapper to run only for this symbol
        # reuse run_wide_daily but filter to the symbol
        # hack: temporarily filter the file on disk
        df_sym = df[df['symbol'] == args.symbol]
        tmp_path = 'data/_tmp_single_symbol.parquet'
        df_sym.to_parquet(tmp_path)
        run_wide_daily(market_path=tmp_path, out_prefix=f'results/daily_{args.symbol.replace("/","_")}', relaxed=args.relaxed )
        os.remove(tmp_path)
