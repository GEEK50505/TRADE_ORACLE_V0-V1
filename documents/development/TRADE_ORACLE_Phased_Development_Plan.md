# TRADE_ORACLE — Phased Development Plan (derived & expanded)

Source: TRADE_ORACLE Optimization Crucible_ A Sub-Phased Blueprint for Proprietary Trading Compliance.txt

---

## Executive Summary

This document is a direct, digested, and operationalized plan derived from the source blueprint. It preserves all original objectives, KPIs, deliverables, and timelines while adding concrete implementation tasks, file paths, script names, and dependency recommendations to make the project actionable for a single-developer laptop workflow.

Main changes from the original blueprint:
- Relaxed confluence parameters into parameter grids for search.
- Strong memory- and time-management guidance (data downsampling to 1H/4H, chunked VectorBT sweeps, partial persistence of results).
- Concrete script names, file locations, and acceptance criteria for automated verification.

---

## Weekly Checkpoint Guide (May–June 2026)

- **Week 1 — May 1–7**: Data ingestion & setup. Deliverable: `data/market_data_1H.parquet` (1H/4H data with indicators).
- **Week 2 — May 8–14**: Chunked VectorBT parameter sweep. Deliverable: `results/oracle_parameter_surface.csv` (top 100 parameter sets).
- **Week 3 — May 15–24**: Backtrader chronological testing of top sets. Deliverable: `results/final_candidate_sets.csv` (3–5 final parameter sets).
- **Week 4 — May 25–31**: Walk-forward optimization. Deliverable: `results/wfo_final_set.json`.
- **Week 5 — June 1–7**: MT5 execution bridge tests and VPS deployment (dry-run on micro-lots).
- **Week 6+ — June 8–July 8**: 30-day forward test and live demo tracking.

Each weekly deliverable must include a short `README.md` in `results/` describing the evaluation metrics and how the artifact was produced.

---

## Sub-Phase 1 — Lightweight Data Ingestion (Implementation)

Objectives
- Replace 1-minute tick reliance with 1H/4H/1D candles for long-range optimization.
- Produce a single, compact, column-complete parquet file containing indicators for all assets.

Tasks
- Create `data/data_pipeline.py` that:
  - Fetches OHLCV for configured tickers (default: BTC, ETH, SOL, LINK) via `ccxt` or `yfinance`.
  - Builds a multi-asset `pandas` DataFrame with time-index and columns: `open, high, low, close, volume, sma50, ema20, rel_weak_14, high30, low30`.
  - Serializes to `data/market_data_1H.parquet` using `snappy` compression.
- Include a small CLI wrapper `scripts/fetch_data.py` to download ranges and resume on failure.

Deliverables
- `data/market_data_1H.parquet` (< 500 MB target).
- `data/market_data_4H.parquet` (optional, same format).
- `scripts/fetch_data.py`, `data/data_pipeline.py`.

Acceptance Criteria
- No NaNs in indicator columns for the chosen date range.
- File size < 500 MB and loadable into memory on a 16–32 GB laptop.

Minimal example (in `data/data_pipeline.py`):

```python
import ccxt
import pandas as pd
import pyarrow

def fetch_ohlcv(exchange_name, symbol, timeframe, since=None, limit=1000):
    ex = getattr(ccxt, exchange_name)()
    bars = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
    df = pd.DataFrame(bars, columns=["ts","open","high","low","close","volume"])
    df['timestamp'] = pd.to_datetime(df['ts'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df

# indicator calc example
# df['sma50'] = df['close'].rolling(50).mean()
# df.to_parquet('data/market_data_1H.parquet', compression='snappy')
```

Notes
- Use `parquet` to minimize I/O and memory overhead. Persist intermediate partial downloads to `data/cache/` to allow safe resumption.

---


## Sub-Phase 2 — Vectorized Parameter Relaxation & Multi‑Dimensional Sweeps (Daily-primary, 8GB‑optimized)

Executive summary

This phase turns brittle single‑value rules into a memory‑safe, chunked VectorBT sweep driven by your validated 36‑month Daily dataset. Because your laptop is an Intel i5 (11th gen) with 8 GB RAM and integrated Iris Xe, the plan uses Daily as the main timeframe, runs per‑symbol sweeps, and keeps chunk sizes and data types conservative so you can iterate without exhausting memory.

Objectives
- Use Daily as the primary sweep (stable signals, compact memory footprint).
- Run a coarse vectorized sweep on the Daily dataset, chunked and per‑parameter sequential to minimize peak RAM.
- Persist partial results per chunk, aggregate into `results/oracle_parameter_surface.csv`, and extract `results/top_100_parameters.csv`.
- Validate metrics: total return, win rate, Sharpe, total trades, and per‑trade expectancy.

Design choices for an 8GB laptop
- Primary timeframe: Daily (~1,100 rows per symbol for 36 months). This keeps arrays small and allows larger parameter grids than hourly.
- Secondary confirmation: 4H (or 1H) only for finalists.
- Per‑symbol sweeps: recommended to avoid cross‑symbol matrix allocations.
- Default chunk_size: 200 parameter combinations per chunk (conservative); use 50–100 for initial smoke runs.
- Data types: convert price arrays to `float32` and use boolean arrays for signals to halve memory vs float64.
- Execution: run `vbt.Portfolio.from_signals` per parameter (sequential) instead of allocating a k×N boolean matrix for a chunk when memory is constrained.
- Monitor memory with `psutil` and reduce `chunk_size` if process memory > 65% of available RAM.

Recommended starting grid (coarse, Daily)
- `sma_window`: [40, 50, 60] (3)
- `ema_window`: [15, 20, 25] (3)
- `fib_min`: [0.50, 0.618] (2)
- `fib_max`: [0.618, 0.786] (2)
- `rw_threshold`: [0.01, 0.03, 0.05] (3)
- `ema_buffer`: [0.005, 0.01] (2)

Total combinations (coarse grid): 3×3×2×2×3×2 = 216. This is a conservative, fast starting grid for exploration on 8 GB; expand/refine around winners.

High‑level algorithm (Daily, memory‑calibrated)
1. Build the parameter product and split into chunks (default `chunk_size=200`, start smoke `--chunk-size=50`).
2. For each chunk and for each parameter in the chunk (sequential):
   - Create `close, high, low` arrays as `np.float32`.
   - Run the Numba confluence function to produce boolean `entries` and `exits` arrays.
   - Immediately call `vbt.Portfolio.from_signals(close, entries, exits, freq='D', ...)` for that single param.
   - Extract metrics and append a row to the chunk results.
   - Delete `entries`, `exits`, and `pf` and call `gc.collect()` to free memory.
   - Optionally check `psutil.Process().memory_info().rss` and pause/adjust if >65% RAM.
3. Write the chunk results to `results/chunk_{i}.parquet` and append to `results/oracle_parameter_surface.csv`.
4. After all chunks: concatenate, apply filters, and write `results/top_100_parameters.csv`.

Memory‑conscious code sketch (per‑param sequential, place in `scripts/vectorbt_opt_engine.py`)

```python
import itertools, os, gc
import numpy as np
import pandas as pd
import vectorbt as vbt
import psutil
from scripts.vectorbt_helpers import confluence_nb

df = pd.read_parquet('data/market_data_1D.parquet')
sym = 'BTC/USDT'
sym_df = df[df['symbol']==sym].set_index('timestamp').sort_index()
close = sym_df['close'].to_numpy(dtype=np.float32)
high = sym_df['high'].to_numpy(dtype=np.float32)
low  = sym_df['low'].to_numpy(dtype=np.float32)

grid = list(itertools.product(sma_windows, ema_windows, fib_mins, fib_maxs, rw_thresholds, ema_buffers))
chunk_size = 200
results_rows = []
proc = psutil.Process()

for i in range(0, len(grid), chunk_size):
    chunk = grid[i:i+chunk_size]
    for p in chunk:
        ent, ex = confluence_nb(close, high, low, *p)
        pf = vbt.Portfolio.from_signals(close, ent, ex, freq='D', init_cash=10000, fees=0.0005)
        # compute metrics (total_return, sharpe, trades, win_rate, expectancy)
        results_rows.append({...})
        del ent, ex, pf
        gc.collect()
        if proc.memory_info().rss / (1024**2) > 0.65 * 8192/1.0:  # rough check against 8GB
            # reduce chunk size or pause
            pass

    pd.DataFrame(results_rows).to_parquet(f'results/chunk_{i//chunk_size}.parquet', index=False)
    pd.DataFrame(results_rows).to_csv('results/oracle_parameter_surface.csv', mode='a', header=not os.path.exists('results/oracle_parameter_surface.csv'), index=False)
    results_rows = []

```

Notes & best practices for 8GB
- Always run per‑symbol; aggregate finalists across symbols after the sweep.
- Use `np.float32` for price arrays; convert back to float64 only when needed for high‑precision reporting.
- Keep `chunk_size` adjustable; begin with `--chunk-size 50` for a smoke run, then `200` for full coarse sweep.
- If runs are CPU‑bound, prefer running overnight; keep interactive runs small.
- Keep frequent checkpoints: write after each chunk and track processed-chunk manifest so you can resume.

Success criteria & gating to Sub‑Phase 3
- Identify ≥100 parameter sets that produce 30–90 trades in the last 6 months (Daily window, ~183 rows) with win_rate ≥ 45% and expectancy ≥ $3.
- Run 4H/Daily confirmation on finalists; <30% contradiction rate.

Deliverables
- `scripts/vectorbt_opt_engine.py` (runnable, memory‑calibrated)
- `scripts/vectorbt_helpers.py` (Numba confluence, float32)
- `results/oracle_parameter_surface.csv`, `results/top_100_parameters.csv`, and `results/chunk_*.parquet`

First 3 actions I recommend now
1. Install minimal packages:
```powershell
pip install vectorbt numba numpy pandas pyarrow psutil
```
2. Create `scripts/vectorbt_helpers.py` (Numba confluence using `float32`) and `scripts/vectorbt_opt_engine.py` (per‑param sequential engine).
3. Run a smoke chunk:
```powershell
python scripts/vectorbt_opt_engine.py --symbol BTC/USDT --chunk-size 50 --test-only
```

I can create the two scripts and run a smoke chunk for you now (will respect `--chunk-size=50` and run per‑symbol). Say “create and run” to proceed.

---

## Sub-Phase 3 — Backtrader Chronological Test & Maven Rule Enforcement

Objectives
- Move path-dependent top candidate sets to a chronology-aware engine (Backtrader) to enforce floating-equity trailing drawdown and the Maven 20% consistency rule.

Tasks
- Create `scripts/backtrader_evaluate.py` which:
  - Loads `results/top_100_parameters.csv` and `data/market_data_1H.parquet`.
  - For each parameter set, runs a full chronological backtest using `backtrader`.
  - Uses a custom analyzer `MavenComplianceAnalyzer` to track high-watermark, drawdown breach, and consistency score.
  - Filters parameter sets that pass all compliance checks into `results/final_candidate_sets.csv`.

Sample analyzer (to place in `scripts/backtrader_utils.py`):

```python
import backtrader as bt

class MavenComplianceAnalyzer(bt.Analyzer):
    def start(self):
        self.high_watermark = self.strategy.broker.get_cash()
        self.account_breached = False
        self.trade_profits = []
        self.total_profit = 0.0

    def next(self):
        current_equity = self.strategy.broker.getvalue()
        if current_equity > self.high_watermark:
            self.high_watermark = current_equity
        liquidation_level = self.high_watermark * 0.97
        if current_equity <= liquidation_level:
            self.account_breached = True

    def notify_trade(self, trade):
        if trade.isclosed and trade.pnlcomm > 0:
            self.trade_profits.append(trade.pnlcomm)
            self.total_profit += trade.pnlcomm

    def get_analysis(self):
        consistency = 0.0
        if self.total_profit > 0 and self.trade_profits:
            consistency = (max(self.trade_profits) / self.total_profit) * 100
        return {'Breached': self.account_breached, 'Consistency_Score': consistency}
```

Deliverable
- `results/final_candidate_sets.csv` with top 3–5 parameter sets and full compliance analysis.

Acceptance Criteria
- Survive 3% trailing drawdown (i.e., `Breached` == False)
- Consistency score < 18%
- Win rate >= 42%
- Expectancy >= 2.50

Notes
- Enforce 4 simultaneous trades and $10 fixed risk in the Backtrader strategy implementation.

---

## Sub-Phase 4 — Walk-Forward Optimization (WFO) & Forward Testing

Objectives
- Validate chosen parameters in forward, unseen market data and deploy to MT5 demo for a 30-day forward test.

Tasks
- Implement WFO harness `scripts/wfo_runner.py` that:
  - Splits historical data into rolling train/test windows (e.g., 12-mo train / 1-mo test rolling forward).
  - For each train window, finds best parameters (via step 2) and tests on the holdout window.
  - Produces `results/wfo_report.csv` summarizing stability across windows.
- Integrate the final parameter set with the MT5 execution bridge (`execution/match_trader.py`), ensuring precise lot sizing from $10 fixed risk.
- Prepare VPS deployment script and instructions in `deploy/README.md`.

Deliverable
- `results/wfo_final_set.json` and deployment artifacts.

Acceptance Criteria
- Final parameter set passes WFO stability checks and live-demo requirements.

---

## Supabase, Secrets & Environment

Required environment variables (create `.env.template`):

```
SUPABASE_URL=
SUPABASE_KEY=
OPENAI_API_KEY=
DWAVE_API_TOKEN=
MT5_WEBHOOK_URL=
WATCHLIST=BTC,ETH,SOL,LINK
```

Files to check / update
- `journal/supabase_client.py` — ensure it handles list/dict responses robustly and logs insert/update operations.
- Add `.env` to `.gitignore`.

---

## Recommended Dependencies (optimization suite)

These are recommended additions to support parameter optimization and evaluation. Create `requirements.optimization.txt` containing:

```
vectorbt>=0.26.0
numba>=0.57.0
optuna>=3.0.0
backtrader==1.9.76.123
yfinance>=0.2.21
joblib>=1.3.0
psutil>=5.9.5
scikit-learn>=1.2.2
matplotlib>=3.8.1
seaborn>=0.12.2
```

Notes
- Test the vectorbt / pandas compatibility on your local Python version. If vectorbt raises compatibility issues, fall back to a pure-numpy sweep + custom metric calculator.

---

## Scripts & File Map (suggested)

- `data/data_pipeline.py` — fetch + indicators + parquet
- `scripts/fetch_data.py` — small CLI wrapper to populate `data/`
- `scripts/optimize_vectorbt.py` — chunked VectorBT sweeps and partial persistence
- `scripts/backtrader_evaluate.py` — chronological backtests and compliance analyzer
- `scripts/wfo_runner.py` — walk-forward optimization harness
- `results/` — outputs: csv, parquet, partials
- `deploy/README.md` — VPS + MT5 deployment instructions

---

## Validation, Tests & Automation

- Add `tests/test_data_pipeline.py` — basic smoke test: load `market_data_1H.parquet`, assert no NaNs in indicator columns.
- Add `tests/test_optimize_smoke.py` — run a tiny grid (<= 10 parameter combos) to validate the sweep pipeline on a subset of the data.
- Add GitHub Actions workflow `ci/smoke.yml` to run smoke tests on pushes to `main` (optional).

---

## Walk-through Checklist (developer quick-start)

1. Create and activate venv.
2. Install base deps: `pip install -r requirements.txt`.
3. Install optimization extras: `pip install -r requirements.optimization.txt`.
4. Copy `.env.template` → `.env` and populate keys.
5. Run `python scripts/fetch_data.py --timeframe 1h --start 2019-01-01`.
6. Run `python scripts/optimize_vectorbt.py --chunk-size 500`.
7. Run `python scripts/backtrader_evaluate.py --candidates results/top_100_parameters.csv`.

Example commands (copy/paste):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements.optimization.txt
python scripts/fetch_data.py --timeframe 1h --symbols BTC/USDT,ETH/USDT --years 3
python scripts/optimize_vectorbt.py --chunk-size 500
```

---

## Pitfalls & Mitigations (kept from original, expanded)

- Over-Optimization Trap — (mitigation) expand ranges, require minimum traded frequency (5–15 trades/month), and use walk-forward validation.
- Memory exhaustion — (mitigation) 1H/4H data, chunked sweeps, partial persistence, GC and process restarts for large jobs.
- MT5 latency — (mitigation) prefer 1H/4H timeframe and dry-run on micro-lots before live deployment.

---

## Deliverables Summary

- `data/market_data_1H.parquet` — canonical dataset
- `results/oracle_parameter_surface.csv` — top N parameter surface
- `results/top_100_parameters.csv` — short list for BT evaluation
- `results/final_candidate_sets.csv` — 3–5 final parameter sets
- `results/wfo_final_set.json` — final WFO-selected parameter set
- `deploy/README.md` — deployment + MT5 instructions

---

## Next Actions (recommended immediate steps)

1. Create `.env` from `.env.template` with your Supabase and API keys.
2. Add `requirements.optimization.txt` and install the optimization packages.
3. Implement `data/data_pipeline.py` and run a single small fetch to verify environment.

---

## Works Cited

- Maven Trading documentation and blog links (preserved from original). 

---

(End of plan)

