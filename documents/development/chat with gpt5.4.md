

You are an expert quantitative trading architect helping me optimize the TRADE_ORACLE system for Maven Trading $5k Instant Funding account. Current situation: - I have expanded to 10 assets (BTC, ETH, SOL, XRP, DOGE, AVAX, LINK, TON, ADA, BNB). - I just ran a wide VectorBT sweep on daily timeframe only. - Results: 156,800 combinations tested, but 0 candidates passed the gates (total_trades ≥ 25, win_rate ≥ 0.40, expectancy ≥ 1.8). - The strategy is still suffering from severe volume starvation even after previous relaxations. Task: Revise and create the next iteration of Sub-Phase 2 (Vectorized Parameter Relaxation) for me. Requirements for the new sweep: - Use daily timeframe only on all 10 assets. - Make the parameter ranges EVEN WIDER than the last sweep to dramatically increase trade frequency. - Temporarily lower the filtering gates so we can capture 50–200+ candidates for analysis. - Output a complete, ready-to-run Python script (vectorbt_wider_sweep_v2.py) that I can execute immediately. - Include clear comments and instructions. Specific wider parameter ranges to use: - SMA Window: 30 – 90 (step 5) - Relative Weakness Threshold: 0.002 (0.2%) – 0.055 (5.5%) (step 0.003) - Fibonacci Band: 0.236 – 0.786 (step 0.05) - EMA Buffer: 0.003 – 0.07 (0.3% – 7%) (step 0.005) - Relative Weakness Lookback: 8, 10, 12, 14, 18, 21, 25 days Temporary relaxed gates for this run only: - total_trades (full 36-month history) ≥ 12 - win_rate ≥ 35% - expectancy ≥ $1.00 After the script, add a short section explaining: 1. Why we are widening further and lowering gates temporarily. 2. What success looks like after this run (how many candidates we hope to get). 3. Next steps once we have the candidates (moving to Backtrader validation). Make the code
No tasks in progress


continue



9 previous messages
The short-side pipeline is now wired up.

Added:

vectorbt_short_sweep.py
backtrader_evaluate_short.py
build_short_final_shortlist.py
short_optimization_runbook.md
What the short validator now does:

Inverts the Daily signal logic for shorts: close < SMA, short-side fib bounce zone, EMA proximity, downside momentum.
Uses true short trade mechanics: short entry, stop above entry, TP1/TP2 below entry, 50% scale-out, same $10 risk and Maven rules.
Keeps the same mixed-feed architecture as the long validator: 4H execution where available, Daily fallback otherwise.
Is ready for future short-side 4H confirmation fields too, but does not require them yet.
Checks completed:

python -m py_compile scripts\vectorbt_short_sweep.py
python -m py_compile scripts\backtrader_evaluate_short.py
python -m py_compile scripts\build_short_final_shortlist.py
Smoke test passed:
python scripts\backtrader_evaluate_short.py --candidates results\short_wider_sweep_results.csv --output-prefix results\backtrader_short_smoke --limit 2
Exact run order:

python scripts\vectorbt_short_sweep.py
python scripts\backtrader_evaluate_short.py --candidates results\short_candidates.csv --output-prefix results\backtrader_short
python scripts\analyze_backtrader_survivors.py --validation-results results\backtrader_short_results.csv --shortlist results\short_candidates.csv --ranking-csv results\backtrader_short_survivor_ranking.csv --asset-stats-csv results\backtrader_short_survivor_asset_stats.csv --report-md results\backtrader_short_survivor_report.md
python scripts\build_short_final_shortlist.py
That will produce:

results/short_candidates.csv
results/backtrader_short_results.csv
results/backtrader_short_summary.md
results/backtrader_short_survivor_report.md
results/backtrader_short_final_shortlist.csv
results/backtrader_short_final_shortlist.md
The next concrete move is to launch the full short discovery sweep:

python scripts\vectorbt_short_sweep.py

contine


I’m kicking off the full short-side discovery run now so we can see whether the short architecture produces a real candidate pool before we spend time on short Backtrader validation. I’ll write it to dedicated short logs and keep checking progress so you’re not flying blind.

The short sweep process launched as PID 10004. I’m checking the live log and the partial output files now to see whether it’s already writing chunks or if it stalled during startup.

The short discovery sweep finished cleanly, and it was much more fertile than the long side. I’m looking at the candidate distribution now, because 258,004 relaxed short candidates is far too many to send directly into Backtrader, so the next sensible move is to compress that pool into a representative validation shortlist first.

The short discovery result is very strong, but also extremely redundant. I’m compressing the 258,004 relaxed hits into a representative Backtrader shortlist now so we validate distinct short behaviors instead of wasting hours on threshold clones.

The shortlist is ready at 150 rows, which is a reasonable size for chronological validation. I’m checking the symbol spread and top rows now, then I’ll start the short Backtrader batch with dedicated logs so we can monitor it the same way we did the long phases.

The shortlist looks healthy and well-distributed across all 10 assets. I’m starting the full short Backtrader validation now with separate logs, because this is the step that will tell us whether the huge short discovery pool survives actual Maven-style chronology or collapses the way most overfit grids do.


check the progress



1 previous message
The short Backtrader run is active and progressing, but the early results are rough.

Current status:

Process is running: PID 9600
Progress log shows 27/150 candidates reached, about 18% complete
Current pace is about 17.7s per candidate
Rough ETA from the log is about 36 more minutes
What the partial results say:

backtrader_short_results.csv currently has 20 flushed rows
0 survivors so far
20 breaches so far
Important note:

The CSV lags the live run because the validator flushes every 10 candidates, so the log is the best real-time indicator
The latest live tail in backtrader_short_run.err.log shows it has already reached rank 27, and those recent candidates are still failing with breached=1, survive=0
So the honest read right now is:

The run is not hung
It is still working normally
Early short candidates are getting crushed under Maven-style chronology
If you want, I can keep monitoring it and tell you when it finishes, or I can start diagnosing why the short discovery layer is overproducing candidates that immediately breach in Backtrader.


just tell me when it is finished



17 previous messages
It’s finished.

Final short Backtrader run:

150/150 candidates evaluated
53 survivors
90 breaches
Files:

Results: backtrader_short_results.csv
Summary: backtrader_short_summary.md
Live log: backtrader_short_run.err.log
Final stdout log: backtrader_short_run.log
Best-looking early survivors in the finished results are ETH-based short candidates, with the top row currently:

short_cand_076_ETH_USDT
84 trades
63.10% win rate
3.03 expectancy
2.13% max DD
If you want, I can now generate the short survivor report and final short shortlist.



8 previous messages
Created the short-side report pack and the final shortlist. I also cleaned up analyze_backtrader_survivors.py so it generates accurate short-phase commentary instead of reusing long-specific AVAX/ETH assumptions.

Outputs:

backtrader_short_survivor_report.md
backtrader_short_survivor_ranking.csv
backtrader_short_survivor_asset_stats.csv
backtrader_short_final_shortlist.csv
backtrader_short_final_shortlist.md
Key read:

53 short survivors came through from 150 Backtrader-tested shortlist rows.
The short side is strongest in DOGE, then ETH, then BNB. Survivor counts were DOGE 13, ETH 12, BNB 11, XRP 7, LINK 5, BTC 4, SOL 1, with 0 survivors from ADA, AVAX, and TON.
The best overall short candidate is short_cand_061_DOGE_USDT: SMA 80, fib_band 0.686, rw 0.050, eb 0.028, rw_lookback 10, with 63 trades, 65.08% win rate, 3.3044 expectancy, 1.7496% max DD, and 5.6043 consistency score.
The best ETH short is short_cand_076_ETH_USDT, and it’s important because it gives you the cleanest non-DOGE diversifier: 84 trades, 63.10% win rate, 3.0317 expectancy, 2.1310% max DD, and the best consistency score in the whole short pool at 4.5812.
The top short edge is concentrated in a high-SMA DOGE cluster, mostly SMA 75-80, fib_band 0.636-0.686, rw_lookback 10, eb 0.028, and rw 0.041-0.050.
ETH’s short cluster is different and cleaner on consistency: mostly SMA 75, fib_band 0.486-0.536, rw 0.011, eb 0.023, rw_lookback 8.
Broadly across all survivors, SMA 30 appears most often by count, but the top-ranked short candidates are not coming from that low-SMA cluster. So breadth lives lower, but the best edge lives higher.
Only 1 survivor sits within 2 percentage points of the 20% consistency cap, which is a good sign.
There are 4 exact outcome duplicates, so a few rows should be treated as threshold-neighbors rather than independent strategies.
Recommended short top 5:

short_cand_061_DOGE_USDT
short_cand_062_DOGE_USDT
short_cand_070_DOGE_USDT
short_cand_076_ETH_USDT
short_cand_075_DOGE_USDT
Validation:

python -m py_compile passed for the updated analysis script.
The report and shortlist were generated successfully from the finished short Backtrader run.
Next clean move is to freeze the top 3 short candidates, keep ETH as the main diversifier, and only after that build the final combined long+short portfolio validation.


You are an expert quantitative trading systems engineer working on TRADE_ORACLE.

We have now completed:
- Long side: Daily + 4H confirmation (5 final long candidates)
- Short side: Daily-only validation (53 short survivors, with top 5 finalists in backtrader_short_final_shortlist.csv)

The short side was validated without the 4H confirmation layer. To keep the methodology perfectly symmetric with the long side, we now add a targeted 4H confirmation filter to the short survivors.

Task: Create the short-side 4H confirmation optimisation phase.

Requirements:
1. Use ONLY the short survivors (or the top 15-20 from backtrader_short_survivor_ranking.csv) as the base — do NOT do a full grid sweep.
2. The 4H layer is a confirmation filter only (exactly like the long side).
   - For shorts: require price closes below a 4H EMA (tunable period 15-30) with a small minimum distance buffer (0.000 to 0.008).
3. Create a new script: vectorbt_short_4h_confirmation_sweep.py
   - Load the short survivors
   - Sweep a small, targeted 4H grid (EMA period 15/20/25/30, min_distance 0.000/0.004/0.008)
   - Combine each short daily parameter set with each 4H filter variation
   - Output: short_plus_4h_candidates.csv + short_4h_sweep_results.csv + short_4h_optimization_summary.md

4. Extend the Backtrader validator (create backtrader_evaluate_short_4h.py or update the existing one with a short_4h_mode flag):
   - Add inverted short 4H confirmation logic in _signal_is_valid
   - Keep all Maven rules, risk sizing, scale-outs, and portfolio accounting identical
   - Run full validation on the new short + 4H candidates
   - Produce:
     - backtrader_short_4h_results.csv
     - backtrader_short_4h_summary.md
     - backtrader_short_4h_survivor_report.md (same format as previous reports)
     - backtrader_short_4h_final_shortlist.csv + .md (top 5 final short candidates)

5. After the run, create a clean final short shortlist of the top 5 short + 4H candidates (same format and style as the long final shortlist).

Deliverables I want first:
- Full ready-to-run code for vectorbt_short_4h_confirmation_sweep.py
- Full ready-to-run code for the short + 4H Backtrader validator
- Short README with the exact run order

Use the exact same coding style, naming conventions, and Maven rule enforcement as all previous scripts (vectorbt_wider_sweep_v2.py, backtrader_evaluate.py, etc.).

Keep the short side fully independent — do not combine with longs yet.

Start by showing me the complete vectorbt_short_4h_confirmation_sweep.py script first.

Begin.



6 previous messages
vectorbt_short_4h_confirmation_sweep.py

"""
Targeted short-side 4H confirmation sweep for the validated short survivors.

This script mirrors the structure of `vectorbt_4h_confirmation_sweep.py`, but it
uses the short-side survivor pool and a short-side 4H confirmation filter.

Why this script exists:
- The long side already passed through a Daily + 4H confirmation phase.
- The short side has only been validated on the Daily layer so far.
- This step keeps the methodology symmetric by adding the same style of targeted
  4H quality gate on top of the already-surviving short candidates.

Important implementation notes:
- The 4H layer is a confirmation filter only. It can block a Daily short entry,
  but it never creates entries on its own.
- The base parameter sets come from the short survivor ranking file rather than
  from a fresh full-grid sweep.
- By default the script uses only the top 20 short survivors. That keeps the
  combined search compact enough for a normal laptop while still covering the
  strongest short-side neighborhoods.
- When true 4H data exists for a symbol, the confirmation rule uses the latest
  same-day 4H bar.
- When 4H data is missing for a symbol in this workspace, the script falls back
  to a daily EMA proxy using the same confirmation parameters. That matches the
  mixed-feed fallback philosophy already used in the Backtrader validators.

Short confirmation rule:
- execution close must be below the 4H EMA
- the distance below that EMA must meet the configured minimum threshold

Outputs:
- results/short_4h_sweep_results.csv
- results/short_plus_4h_candidates.csv
- results/short_4h_optimization_summary.md

Recommended full run:
    python scripts/vectorbt_short_4h_confirmation_sweep.py

Helpful smaller run:
    python scripts/vectorbt_short_4h_confirmation_sweep.py --top-n-base 10
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    from config import settings
except Exception:
    settings = None


# ==============================================================================
# PATHS AND CONSTANTS
# ==============================================================================

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")
DATA_DIR = os.path.join(ROOT_DIR, "data")

DEFAULT_SURVIVOR_PATH = os.path.join(RESULTS_DIR, "backtrader_short_survivor_ranking.csv")
DEFAULT_DAILY_PATH = os.path.join(DATA_DIR, "market_data_1D.parquet")
DEFAULT_4H_PATH = os.path.join(DATA_DIR, "market_data_4H.parquet")
DEFAULT_RESULTS_CSV = os.path.join(RESULTS_DIR, "short_4h_sweep_results.csv")
DEFAULT_CANDIDATES_CSV = os.path.join(RESULTS_DIR, "short_plus_4h_candidates.csv")
DEFAULT_SUMMARY_MD = os.path.join(RESULTS_DIR, "short_4h_optimization_summary.md")

WATCHLIST = list(
    getattr(
        settings,
        "WATCHLIST",
        ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "TON/USDT", "ADA/USDT", "BNB/USDT"],
    )
)

INIT_CASH = 10_000.0
FEE = 0.0005
FIB_LOOKBACK = 30

# This is the exact targeted confirmation grid requested for the short side.
CONFIRM_EMA_PERIODS = [15, 20, 25, 30]
CONFIRM_MIN_DISTANCES = [0.0, 0.004, 0.008]


# ==============================================================================
# SMALL DATA CONTAINERS
# ==============================================================================


@dataclass(frozen=True)
class ShortSurvivor:
    """A typed view of one short survivor used as the Daily base layer."""

    analysis_rank: int
    base_rank: int
    param_id: str
    source_symbol: str
    side: str
    sma: int
    ema: int
    fib_floor: float
    fib_band: float
    rw: float
    eb: float
    rw_lookback: int

    @classmethod
    def from_row(cls, row: pd.Series) -> "ShortSurvivor":
        """Convert one ranking row into a strongly-typed short survivor object."""
        return cls(
            analysis_rank=int(row["analysis_rank"]),
            base_rank=int(row["rank"]),
            param_id=str(row["param_id"]),
            source_symbol=str(row["source_symbol"]),
            side=str(row.get("side", "short")).lower(),
            sma=int(row["sma"]),
            ema=int(row["ema"]),
            fib_floor=float(row["fib_floor"]),
            fib_band=float(row["fib_band"]),
            rw=float(row["rw"]),
            eb=float(row["eb"]),
            rw_lookback=int(row["rw_lookback"]),
        )


@dataclass(frozen=True)
class ConfirmCombo:
    """One short-side 4H confirmation parameter tuple."""

    ema_period: int
    min_distance: float

    @property
    def combo_id(self) -> str:
        """Stable identifier used in combined candidate ids."""
        return f"ema{self.ema_period}_dist{self.min_distance:.3f}"


# ==============================================================================
# SMALL HELPERS
# ==============================================================================


def ensure_results_dir() -> None:
    """Create the results folder if it does not already exist."""
    os.makedirs(RESULTS_DIR, exist_ok=True)


def rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    """Simple rolling SMA helper used to mirror the Daily discovery logic."""
    out = np.full(values.shape[0], np.nan, dtype=np.float64)
    if window <= 0 or values.size == 0 or window > values.size:
        return out
    kernel = np.ones(window, dtype=np.float64) / float(window)
    out[window - 1 :] = np.convolve(values.astype(np.float64), kernel, mode="valid")
    return out


def ema(values: np.ndarray, window: int) -> np.ndarray:
    """Simple EMA helper used in both the Daily and 4H layers."""
    out = np.full(values.shape[0], np.nan, dtype=np.float64)
    if values.size == 0:
        return out
    alpha = 2.0 / (window + 1.0)
    out[0] = values[0]
    for idx in range(1, values.shape[0]):
        out[idx] = alpha * values[idx] + (1.0 - alpha) * out[idx - 1]
    return out


def rolling_max(values: np.ndarray, window: int) -> np.ndarray:
    """Rolling maximum helper for the short bounce-zone calculation."""
    return pd.Series(values).rolling(window=window, min_periods=1).max().to_numpy(dtype=np.float64, copy=False)


def rolling_min(values: np.ndarray, window: int) -> np.ndarray:
    """Rolling minimum helper for the short bounce-zone calculation."""
    return pd.Series(values).rolling(window=window, min_periods=1).min().to_numpy(dtype=np.float64, copy=False)


def trade_pnls(close: np.ndarray, entries: np.ndarray, exits: np.ndarray) -> List[float]:
    """
    Generate the closed-trade PnL list for one symbol using short-side math.

    This keeps the 4H confirmation stage aligned with the lightweight discovery
    accounting used by the other vectorized scripts.
    """

    trade_list: List[float] = []
    in_position = False
    entry_price = 0.0

    for idx in range(close.shape[0]):
        if entries[idx] and not in_position:
            entry_price = float(close[idx])
            in_position = True

        if exits[idx] and in_position:
            exit_price = float(close[idx])
            pnl_pct = (entry_price - exit_price) / entry_price - (2.0 * FEE)
            trade_list.append(INIT_CASH * pnl_pct)
            in_position = False

    if in_position:
        exit_price = float(close[-1])
        pnl_pct = (entry_price - exit_price) / entry_price - (2.0 * FEE)
        trade_list.append(INIT_CASH * pnl_pct)

    return trade_list


def load_survivors(path: str, top_n_base: int) -> List[ShortSurvivor]:
    """
    Load the ranked short survivors and keep only the strongest base rows.

    The ranking file is already sorted by composite score, so taking the first
    N rows gives us the intended targeted base set for the 4H layer.
    """

    if not os.path.exists(path):
        raise FileNotFoundError(f"Short survivor file not found: {path}")

    df = pd.read_csv(path)
    if df.empty:
        raise ValueError("Short survivor file is empty.")

    df = df.sort_values(by=["analysis_rank"]).reset_index(drop=True)
    df = df.head(max(1, int(top_n_base))).copy()
    return [ShortSurvivor.from_row(row) for _, row in df.iterrows()]


def load_market_by_symbol(path: str) -> Dict[str, pd.DataFrame]:
    """Load one parquet file and split it into one DataFrame per symbol."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Market data file not found: {path}")

    df = pd.read_parquet(path)
    if "symbol" not in df.columns or "timestamp" not in df.columns:
        raise ValueError(f"Expected `symbol` and `timestamp` columns in {path}")

    frames: Dict[str, pd.DataFrame] = {}
    for symbol in sorted(df["symbol"].astype(str).unique().tolist()):
        frame = (
            df.loc[df["symbol"] == symbol, ["timestamp", "open", "high", "low", "close", "volume"]]
            .copy()
            .sort_values("timestamp")
            .set_index("timestamp")
        )
        frames[symbol] = frame
    return frames


# ==============================================================================
# DAILY ENTRY / EXIT LOGIC
# ==============================================================================


def build_daily_entries_exits(df_daily: pd.DataFrame, candidate: ShortSurvivor) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Recreate the exact Daily short-only signal logic from `vectorbt_short_sweep.py`.

    This ensures the 4H layer remains a true confirmation filter rather than a
    second independent short strategy.
    """

    close = df_daily["close"].to_numpy(dtype=np.float64, copy=True)
    high = df_daily["high"].to_numpy(dtype=np.float64, copy=True)
    low = df_daily["low"].to_numpy(dtype=np.float64, copy=True)

    sma_values = rolling_mean(close, candidate.sma)
    ema_values = ema(close, candidate.ema)
    high30 = rolling_max(high, FIB_LOOKBACK)
    low30 = rolling_min(low, FIB_LOOKBACK)

    downside_momentum = np.zeros(close.shape[0], dtype=np.float64)
    if candidate.rw_lookback < close.shape[0]:
        prev = close[:-candidate.rw_lookback]
        curr = close[candidate.rw_lookback :]
        valid = prev != 0.0
        out = np.zeros(prev.shape[0], dtype=np.float64)
        out[valid] = (prev[valid] - curr[valid]) / prev[valid]
        downside_momentum[candidate.rw_lookback :] = out

    bounce_retracement = np.zeros(close.shape[0], dtype=np.float64)
    denom = high30 - low30
    valid = denom != 0.0
    bounce_retracement[valid] = (close[valid] - low30[valid]) / denom[valid]

    ema_distance = np.zeros(close.shape[0], dtype=np.float64)
    valid_close = close != 0.0
    ema_distance[valid_close] = np.abs(close[valid_close] - ema_values[valid_close]) / close[valid_close]

    entries = (
        (~np.isnan(sma_values))
        & (close < sma_values)
        & (bounce_retracement >= candidate.fib_floor)
        & (bounce_retracement <= candidate.fib_band)
        & (ema_distance <= candidate.eb)
        & (downside_momentum >= candidate.rw)
    )
    exits = (~np.isnan(ema_values)) & (close > ema_values)

    return close, entries.astype(bool), exits.astype(bool)


# ==============================================================================
# 4H CONFIRMATION LOGIC
# ==============================================================================


def build_confirmation_series(
    symbol: str,
    daily_index: pd.DatetimeIndex,
    daily_frames: Dict[str, pd.DataFrame],
    intraday_frames: Dict[str, pd.DataFrame],
    combo: ConfirmCombo,
) -> Tuple[np.ndarray, str]:
    """
    Build a daily-aligned short confirmation mask for one symbol.

    Return value:
    - boolean array aligned to the daily bars
    - string describing whether the filter used true 4H data or a daily fallback
    """

    if symbol in intraday_frames:
        intraday = intraday_frames[symbol]
        close_4h = intraday["close"].to_numpy(dtype=np.float64, copy=True)
        ema_4h = ema(close_4h, combo.ema_period)

        distance = np.full(close_4h.shape[0], -np.inf, dtype=np.float64)
        valid = ema_4h > 0.0
        distance[valid] = (ema_4h[valid] - close_4h[valid]) / ema_4h[valid]

        confirm_4h = (~np.isnan(ema_4h)) & (close_4h < ema_4h) & (distance >= combo.min_distance)

        # Reduce the intraday stream to one daily confirmation value using the
        # final 4H bar from each day, which mirrors the long-side methodology.
        daily_confirm = intraday.copy()
        daily_confirm["confirm"] = confirm_4h.astype(bool)
        daily_confirm["day"] = daily_confirm.index.normalize()
        reduced = daily_confirm.groupby("day")["confirm"].last()

        aligned = reduced.reindex(daily_index.normalize()).fillna(False).to_numpy(dtype=bool)
        return aligned, "4H"

    # If 4H data is missing for the symbol, fall back to a Daily EMA proxy.
    daily = daily_frames[symbol]
    close_daily = daily["close"].to_numpy(dtype=np.float64, copy=True)
    ema_daily = ema(close_daily, combo.ema_period)

    distance = np.full(close_daily.shape[0], -np.inf, dtype=np.float64)
    valid = ema_daily > 0.0
    distance[valid] = (ema_daily[valid] - close_daily[valid]) / ema_daily[valid]

    confirm_daily = (~np.isnan(ema_daily)) & (close_daily < ema_daily) & (distance >= combo.min_distance)
    return confirm_daily.astype(bool), "1D_fallback"


# ==============================================================================
# COMBINED EVALUATION
# ==============================================================================


def evaluate_candidate_combo(
    candidate: ShortSurvivor,
    combo: ConfirmCombo,
    daily_frames: Dict[str, pd.DataFrame],
    intraday_frames: Dict[str, pd.DataFrame],
) -> Dict[str, object]:
    """
    Evaluate one short survivor combined with one short-side 4H confirmation combo.

    The metrics are aggregated across the full watchlist so the ranking lines up
    with the later portfolio-wide Backtrader validation stage.
    """

    all_trade_pnls: List[float] = []
    used_modes: List[str] = []

    for symbol in WATCHLIST:
        if symbol not in daily_frames:
            continue

        df_daily = daily_frames[symbol]
        close, daily_entries, daily_exits = build_daily_entries_exits(df_daily, candidate)
        confirm_mask, mode = build_confirmation_series(
            symbol=symbol,
            daily_index=df_daily.index,
            daily_frames=daily_frames,
            intraday_frames=intraday_frames,
            combo=combo,
        )

        combined_entries = daily_entries & confirm_mask
        all_trade_pnls.extend(trade_pnls(close, combined_entries, daily_exits))
        used_modes.append(mode)

    total_trades = len(all_trade_pnls)
    total_profit = float(sum(all_trade_pnls))
    wins = int(sum(1 for pnl in all_trade_pnls if pnl > 0.0))
    win_rate = (wins / total_trades) if total_trades > 0 else 0.0
    expectancy = (total_profit / total_trades) if total_trades > 0 else 0.0
    total_return = total_profit / INIT_CASH if INIT_CASH > 0 else 0.0

    return {
        "base_analysis_rank": int(candidate.analysis_rank),
        "base_rank": int(candidate.base_rank),
        "daily_param_id": candidate.param_id,
        "source_symbol": candidate.source_symbol,
        "side": "short",
        "sma": int(candidate.sma),
        "ema": int(candidate.ema),
        "fib_floor": float(candidate.fib_floor),
        "fib_band": float(candidate.fib_band),
        "rw": float(candidate.rw),
        "eb": float(candidate.eb),
        "rw_lookback": int(candidate.rw_lookback),
        "confirm_enabled": True,
        "confirm_ema_period": int(combo.ema_period),
        "confirm_min_distance": float(combo.min_distance),
        "confirm_mode": "close_below_ema",
        "assets_with_real_4h": int(sum(1 for mode in used_modes if mode == "4H")),
        "assets_with_daily_fallback": int(sum(1 for mode in used_modes if mode == "1D_fallback")),
        "total_trades": int(total_trades),
        "win_rate": float(win_rate),
        "expectancy": float(expectancy),
        "total_profit": float(total_profit),
        "total_return": float(total_return),
    }


def build_candidate_export(results_df: pd.DataFrame, candidate_limit: int | None) -> pd.DataFrame:
    """
    Build the Backtrader-ready candidate export from the full ranked sweep table.

    We keep the full result table separately so research notes can inspect all
    combos, while this export contains the exact columns needed for validation.
    """

    candidate_df = results_df[
        [
            "combined_rank",
            "param_id",
            "daily_param_id",
            "source_symbol",
            "side",
            "sma",
            "ema",
            "fib_floor",
            "fib_band",
            "rw",
            "eb",
            "rw_lookback",
            "confirm_enabled",
            "confirm_mode",
            "confirm_ema_period",
            "confirm_min_distance",
            "total_trades",
            "win_rate",
            "expectancy",
            "total_profit",
            "total_return",
        ]
    ].copy()

    if candidate_limit is not None:
        candidate_df = candidate_df.head(max(1, int(candidate_limit))).copy()

    return candidate_df.reset_index(drop=True)


def write_summary(
    summary_path: str,
    results_df: pd.DataFrame,
    candidate_df: pd.DataFrame,
    survivors: Sequence[ShortSurvivor],
) -> None:
    """Write a compact markdown summary for the short-side 4H confirmation sweep."""
    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write("# Short Daily + 4H confirmation sweep summary\n\n")
        handle.write(f"- **base_short_survivors_used**: {len(survivors)}\n")
        handle.write(f"- **confirm_ema_periods**: {CONFIRM_EMA_PERIODS}\n")
        handle.write(f"- **confirm_min_distances**: {CONFIRM_MIN_DISTANCES}\n")
        handle.write(f"- **full_combined_rows**: {len(results_df)}\n")
        handle.write(f"- **backtrader_candidate_rows**: {len(candidate_df)}\n")
        handle.write(f"- **best_expectancy**: {results_df['expectancy'].max():.4f}\n")
        handle.write(f"- **best_win_rate**: {results_df['win_rate'].max():.4f}\n")
        handle.write(f"- **best_total_trades**: {int(results_df['total_trades'].max())}\n")
        handle.write("\n## Method Notes\n\n")
        handle.write("- The Daily short layer is unchanged from the validated short discovery phase.\n")
        handle.write("- The 4H layer is confirmation-only: execution close must be below the 4H EMA and far enough below it to clear the minimum distance threshold.\n")
        handle.write("- No fresh full-grid search was performed; this pass only combines the strongest short survivors with a compact 4H confirmation grid.\n")
        handle.write("\n## Top 10 Combined Short Candidates\n\n")

        top = results_df.head(10).copy()
        columns = [
            "param_id",
            "source_symbol",
            "confirm_ema_period",
            "confirm_min_distance",
            "total_trades",
            "win_rate",
            "expectancy",
            "total_return",
        ]
        handle.write("| " + " | ".join(columns) + " |\n")
        handle.write("| " + " | ".join(["---"] * len(columns)) + " |\n")
        for _, row in top[columns].iterrows():
            handle.write("| " + " | ".join(str(row[column]) for column in columns) + " |\n")


def parse_args() -> argparse.Namespace:
    """Expose the script inputs and outputs for reuse."""
    parser = argparse.ArgumentParser(description="Targeted short-side 4H confirmation sweep for short survivors.")
    parser.add_argument("--survivors", default=DEFAULT_SURVIVOR_PATH, help="Path to the short survivor ranking CSV.")
    parser.add_argument("--daily-data", default=DEFAULT_DAILY_PATH, help="Path to the daily market parquet.")
    parser.add_argument("--intraday-data", default=DEFAULT_4H_PATH, help="Path to the 4H market parquet.")
    parser.add_argument("--results-csv", default=DEFAULT_RESULTS_CSV, help="Path for the full ranked sweep results.")
    parser.add_argument("--candidates-csv", default=DEFAULT_CANDIDATES_CSV, help="Path for the Backtrader-ready candidate export.")
    parser.add_argument("--summary-md", default=DEFAULT_SUMMARY_MD, help="Path for the markdown summary.")
    parser.add_argument(
        "--top-n-base",
        type=int,
        default=20,
        help="How many ranked short survivors to use as the Daily base set.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=None,
        help="Optional cap on the exported Backtrader candidate rows. Default keeps all combined rows.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the full short Daily + 4H confirmation sweep."""
    args = parse_args()
    ensure_results_dir()

    survivors = load_survivors(args.survivors, top_n_base=args.top_n_base)
    daily_frames = load_market_by_symbol(args.daily_data)
    intraday_frames = load_market_by_symbol(args.intraday_data)

    combos = [ConfirmCombo(period, distance) for period in CONFIRM_EMA_PERIODS for distance in CONFIRM_MIN_DISTANCES]
    rows: List[Dict[str, object]] = []

    for candidate in survivors:
        for combo in combos:
            rows.append(
                evaluate_candidate_combo(
                    candidate=candidate,
                    combo=combo,
                    daily_frames=daily_frames,
                    intraday_frames=intraday_frames,
                )
            )

    results_df = pd.DataFrame(rows)
    results_df = results_df.sort_values(
        by=["expectancy", "win_rate", "total_trades", "total_return"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    results_df.insert(0, "combined_rank", range(1, len(results_df) + 1))
    results_df["param_id"] = results_df.apply(
        lambda row: f"{row['daily_param_id']}__4h_ema{int(row['confirm_ema_period'])}_dist{float(row['confirm_min_distance']):.3f}",
        axis=1,
    )

    candidate_df = build_candidate_export(results_df, candidate_limit=args.candidate_limit)

    results_df.to_csv(args.results_csv, index=False)
    candidate_df.to_csv(args.candidates_csv, index=False)
    write_summary(args.summary_md, results_df, candidate_df, survivors)

    print(f"Short base survivors loaded: {len(survivors)}")
    print(f"4H confirmation combos tested: {len(combos)}")
    print(f"Full combined rows written: {len(results_df)}")
    print(f"Backtrader candidate rows written: {len(candidate_df)}")
    print(f"Results CSV: {args.results_csv}")
    print(f"Candidates CSV: {args.candidates_csv}")
    print(f"Summary MD: {args.summary_md}")


if __name__ == "__main__":
    main()
backtrader_evaluate_short_4h.py

"""
Chronological Backtrader validation for the short Daily + 4H confirmation set.

This script intentionally reuses the validated short-side Backtrader engine from
`backtrader_evaluate_short.py`. The underlying engine already supports:
- short-side signal logic,
- short-side 4H confirmation fields,
- Maven risk sizing and portfolio rules,
- mixed Daily + 4H feeds, and
- short-side stop / scale-out accounting.

Why this wrapper exists:
- It gives the short 4H phase its own clean entrypoint and default output names.
- It keeps the run order symmetric with the long 4H phase.
- It avoids duplicating a large, already-working validator implementation.

Recommended full run:
    python scripts/backtrader_evaluate_short_4h.py

Helpful smoke test:
    python scripts/backtrader_evaluate_short_4h.py --limit 3 --output-prefix results/backtrader_short_4h_smoke
"""

from __future__ import annotations

import argparse
import os

from backtrader_evaluate_short import (
    DEFAULT_DAILY_PATH,
    DEFAULT_INTRADAY_PATH,
    MarketDataCatalog,
    evaluate_candidates,
    load_candidates,
    select_candidates,
)


# ==============================================================================
# PATHS
# ==============================================================================

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

DEFAULT_CANDIDATES_PATH = os.path.join(RESULTS_DIR, "short_plus_4h_candidates.csv")
DEFAULT_OUTPUT_PREFIX = os.path.join(RESULTS_DIR, "backtrader_short_4h")


def retitle_summary(summary_path: str) -> None:
    """
    Rewrite the generic short summary title into a phase-specific 4H title.

    The shared evaluator already writes the correct metrics and confirmation info.
    This tiny post-processing step keeps the output filename and title aligned.
    """

    if not os.path.exists(summary_path):
        return

    with open(summary_path, "r", encoding="utf-8") as handle:
        text = handle.read()

    if text.startswith("# Backtrader short validation summary"):
        text = text.replace(
            "# Backtrader short validation summary",
            "# Backtrader short + 4H validation summary",
            1,
        )

    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write(text)


def parse_args() -> argparse.Namespace:
    """Define the CLI surface for the short + 4H validation phase."""
    parser = argparse.ArgumentParser(description="Chronological Backtrader validation for short Daily + 4H candidates.")
    parser.add_argument("--candidates", default=DEFAULT_CANDIDATES_PATH, help="Path to the short + 4H candidate CSV.")
    parser.add_argument("--daily-data", default=DEFAULT_DAILY_PATH, help="Path to the daily parquet file.")
    parser.add_argument(
        "--intraday-data",
        default=DEFAULT_INTRADAY_PATH,
        help="Path to the 4H parquet file used when intraday execution is available.",
    )
    parser.add_argument(
        "--output-prefix",
        default=DEFAULT_OUTPUT_PREFIX,
        help="Prefix for output files. Example: results/backtrader_short_4h",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional cap for smoke tests.")
    parser.add_argument("--start-rank", type=int, default=None, help="Optional inclusive candidate-rank lower bound.")
    parser.add_argument("--end-rank", type=int, default=None, help="Optional inclusive candidate-rank upper bound.")
    parser.add_argument(
        "--no-intraday",
        action="store_true",
        help="Force Daily-only validation even if 4H data exists.",
    )
    parser.add_argument(
        "--flush-every",
        type=int,
        default=10,
        help="Write partial CSV progress every N candidates.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the shared short evaluator with short + 4H defaults."""
    args = parse_args()

    candidates = load_candidates(args.candidates)
    candidates = select_candidates(candidates, args)

    catalog = MarketDataCatalog(daily_path=args.daily_data, intraday_path=args.intraday_data)

    output_csv = f"{args.output_prefix}_results.csv"
    summary_md = f"{args.output_prefix}_summary.md"

    results_df = evaluate_candidates(
        candidates=candidates,
        catalog=catalog,
        output_csv=output_csv,
        summary_md=summary_md,
        candidates_path=args.candidates,
        prefer_intraday=not args.no_intraday,
        flush_every=max(1, int(args.flush_every)),
    )

    # The shared engine writes the correct metrics already; this just gives the
    # markdown file the short + 4H phase label the user expects.
    retitle_summary(summary_md)

    survivors = int(results_df["overall_survival"].sum())
    print(f"Validation complete. Results: {output_csv}")
    print(f"Summary: {summary_md}")
    print(f"Candidates evaluated: {len(results_df)}")
    print(f"Survivors: {survivors}")


if __name__ == "__main__":
    main()
The short-side 4H confirmation logic itself was already in backtrader_evaluate_short.py, so no extra engine patch was needed beyond this dedicated wrapper. _confirmation_is_valid() already enforces the short filter as close < EMA with the configured minimum distance, and _signal_is_valid() already blocks entries when that confirmation fails.

Run order is in short_4h_confirmation_runbook.md:

# Short 4H Confirmation Runbook

1. Build the combined short Daily + 4H candidate file

python scripts\vectorbt_short_4h_confirmation_sweep.py

2. Run chronological Backtrader validation on the combined short candidates

python scripts\backtrader_evaluate_short_4h.py

3. Generate the short + 4H survivor analysis report

python scripts\analyze_backtrader_survivors.py --validation-results results\backtrader_short_4h_results.csv --shortlist results\short_plus_4h_candidates.csv --ranking-csv results\backtrader_short_4h_survivor_ranking.csv --asset-stats-csv results\backtrader_short_4h_survivor_asset_stats.csv --report-md results\backtrader_short_4h_survivor_report.md

4. Build the final short + 4H shortlist

python scripts\build_short_final_shortlist.py --ranking-csv results\backtrader_short_4h_survivor_ranking.csv --output-csv results\backtrader_short_4h_final_shortlist.csv --output-md results\backtrader_short_4h_final_shortlist.md
Checks passed:

python -m py_compile scripts\vectorbt_short_4h_confirmation_sweep.py
python -m py_compile scripts\backtrader_evaluate_short_4h.py
Smoke sweep passed with top 2 base survivors
Smoke Backtrader run passed on 2 combined candidates
Next full commands:

python scripts\vectorbt_short_4h_confirmation_sweep.py
python scripts\backtrader_evaluate_short_4h.py

continue


I’m moving from code into execution now: first I’ll build the short + 4H candidate file, then I’ll decide whether to run the full Backtrader batch in one shot or trim it slightly if the candidate count would make the wait excessive.

The sweep finished cleanly with 240 combined short + 4H candidates, so I’m launching the full Backtrader validation on all of them rather than trimming the set.


continue




3 previous messages
I created the full handoff at claude_project_handoff.md.

It’s a long, detailed project brief that includes:

the system goal and Maven account constraints
the 10-asset universe and data setup
the exact long and short strategy logic
every completed phase in order
all major scripts and what each one does
the full long-side results and final long shortlist
the full short-side results and final short shortlist
the new short + 4H phase and its current status
what is finished, what is still pending, and the next logical steps
Important current status included in the handoff:

short + 4H sweep is complete
short_4h_sweep_results.csv and short_plus_4h_candidates.csv are done
backtrader_short_4h_results.csv currently has 20 flushed rows
those 20 rows show 15 survivors so far and 0 breaches so far
backtrader_short_4h_summary.md does not exist yet, so that phase is not confirmed finished
If you want, I can also paste the entire handoff directly into chat in one message formatted for Claude.


You’re out of Codex messages
Your rate limit resets on Apr 8, 2026, 4:39 PM. To continue using Codex, upgrade to Plus today.
Upgrade




GPT-5.4

Extra High

IDE context


Local 0%

Default permissions
