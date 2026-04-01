"""
Aggregate Daily oracle results, compute last-6-month trade counts per parameter,
and produce `results/top_100_parameters.csv` using gating filters.
"""
import os
import gc
import argparse
import pandas as pd
import numpy as np

# Ensure scripts dir is importable
import sys
SCRIPT_DIR = os.path.dirname(__file__)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from vectorbt_helpers import confluence, simple_backtest


def process_symbol(df_market, df_oracle_sym, last_days=183):
    sym_rows = []
    close_all = df_market['close'].to_numpy(dtype=np.float32)
    high_all = df_market['high'].to_numpy(dtype=np.float32)
    low_all = df_market['low'].to_numpy(dtype=np.float32)
    n = close_all.size
    last_n = min(last_days, n)
    close = close_all[-last_n:]
    high = high_all[-last_n:]
    low = low_all[-last_n:]

    for _, row in df_oracle_sym.iterrows():
        sma = int(row['sma'])
        ema = int(row['ema'])
        fmin = float(row['fib_min'])
        fmax = float(row['fib_max'])
        rw = float(row['rw'])
        eb = float(row['eb']) if 'eb' in row.index else float(row.get('expectancy', 0.01))

        try:
            entries, exits = confluence(close, high, low, sma, ema, fmin, fmax, rw, eb)
            metrics = simple_backtest(close, entries, exits)
        except Exception as e:
            metrics = {"total_trades": 0, "win_rate": 0.0, "expectancy": 0.0, "total_return": 0.0}

        out = row.to_dict()
        out['trades_recent'] = int(metrics.get('total_trades', 0))
        out['win_rate_recent'] = float(metrics.get('win_rate', 0.0))
        out['expectancy_recent'] = float(metrics.get('expectancy', 0.0))
        sym_rows.append(out)

    return sym_rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--oracle', default='results/oracle_parameter_surface_1D.csv')
    p.add_argument('--market', default='data/market_data_1D.parquet')
    p.add_argument('--last-days', type=int, default=183)
    p.add_argument('--top-n', type=int, default=100)
    args = p.parse_args()

    if not os.path.exists(args.oracle):
        print('Oracle CSV not found:', args.oracle)
        return
    if not os.path.exists(args.market):
        print('Market parquet not found:', args.market)
        return

    print('Loading oracle CSV...')
    df_oracle = pd.read_csv(args.oracle)
    print('Loading market data (parquet)...')
    df_market = pd.read_parquet(args.market)

    results = []
    symbols = sorted(df_oracle['symbol'].unique())
    for sym in symbols:
        print(f'Processing symbol {sym}...')
        df_oracle_sym = df_oracle[df_oracle['symbol'] == sym].reset_index(drop=True)
        # prepare market subset
        df_m_sym = df_market[df_market['symbol'] == sym].set_index('timestamp').sort_index()
        sym_rows = process_symbol(df_m_sym, df_oracle_sym, last_days=args.last_days)
        results.extend(sym_rows)
        gc.collect()

    df_results = pd.DataFrame(results)
    out_full = f'results/oracle_parameter_surface_1D_with_recent.csv'
    df_results.to_parquet(out_full.replace('.csv', '.parquet'), index=False)
    df_results.to_csv(out_full, index=False)

    # filtering gates
    mask = (
        (df_results['trades_recent'] >= 30) & (df_results['trades_recent'] <= 90) &
        (df_results['win_rate_recent'] >= 0.45) & (df_results['expectancy_recent'] >= 3.0)
    )
    df_candidates = df_results[mask].copy()
    df_candidates_sorted = df_candidates.sort_values(by=['expectancy_recent'], ascending=False)
    top_n = df_candidates_sorted.head(args.top_n)

    out_top = 'results/top_100_parameters.csv'
    top_n.to_csv(out_top, index=False)

    print(f'Done. Total rows processed: {len(df_results)}; candidates: {len(df_candidates)}; top N: {len(top_n)}')


if __name__ == '__main__':
    main()
