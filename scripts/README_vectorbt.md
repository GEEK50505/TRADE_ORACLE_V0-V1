VectorBT engine (Sub-Phase 2)

This folder contains a lightweight, memory-conscious engine for running parameter sweeps on the project's market data files.

Quick smoke steps (Daily primary):

1. Ensure pip deps (optional but recommended):

```powershell
pip install vectorbt numba numpy pandas pyarrow psutil
```

2. Run a smoke chunk for `BTC/USDT` (chunk-size 50):

```powershell
python scripts/vectorbt_opt_engine.py --symbol BTC/USDT --chunk-size 50 --test-only
```

Notes:
- The engine will create `results/chunk_0.parquet` and append to `results/oracle_parameter_surface.csv`.
- If `vectorbt` is not installed, the engine falls back to a simple backtest implementation so smoke runs still produce meaningful rows.
