# TRADE_ORACLE Full Project Handoff For Claude

This document is a detailed handoff of the current TRADE_ORACLE research and engineering state so another model or engineer can pick up the work without losing context.

It covers:
- what the system is trying to achieve,
- what files and scripts exist,
- what optimization and validation phases have been completed,
- what the key findings were,
- what the current best long and short candidates are,
- what work is currently in progress,
- and what the next logical steps are.

The goal of the project is to build a prop-firm-compliant quantitative crypto trading system for a Maven Trading `$5,000` Instant Funding account. The system is being engineered with a strong emphasis on chronological validation, drawdown compliance, consistency rule compliance, and portability between vectorized discovery and event-driven Backtrader validation.

---

## 1. Core Objective

The system being built is called `TRADE_ORACLE`.

The practical objective is:
- discover tradeable long and short parameter sets across a basket of crypto assets,
- validate them under event-driven chronology rather than only vectorized approximations,
- enforce Maven-style account rules,
- and eventually combine independently validated long and short modules into one final portfolio-level system.

The development philosophy has been:
- do not trust vectorized discovery alone,
- separate research phases cleanly,
- validate longs and shorts independently before combining them,
- treat 4H confirmation as a filter layer rather than a separate strategy,
- and keep the codebase understandable for a solo “vibe coder”, with heavy comments and readable structure.

---

## 2. Trading Constraints And Prop-Firm Rules

The Backtrader validation layer is built around a Maven-style rule set. The system currently enforces the following:

- Starting balance: `$5,000`
- Fixed risk per trade: `$10` per trade, which is `0.2%` of account equity
- Maximum concurrent trades: `4`
- Maximum trailing drawdown: `3%` from the absolute equity high-water mark
- The drawdown check is floating-PnL-aware and not just closed-PnL-aware
- Consistency rule: no single trade should represent more than `20%` of total profit
- Trade management:
  - 50% scale-out at `2.0 x ATR`
  - remaining 50% scale-out at `3.5 x ATR`
  - stop distance based on `1.5 x ATR`
- Leverage cap: crypto leverage capped according to the config used in the validator

The Backtrader layer is custom because the system needs precise control over:
- floating drawdown snapshots,
- Maven trailing watermark logic,
- consistency tracking,
- mixed daily + 4H feed handling,
- and manual partial exits.

---

## 3. Market Universe And Data

The main universe expanded to 10 assets:

- `BTC/USDT`
- `ETH/USDT`
- `SOL/USDT`
- `XRP/USDT`
- `DOGE/USDT`
- `AVAX/USDT`
- `LINK/USDT`
- `TON/USDT`
- `ADA/USDT`
- `BNB/USDT`

Primary data files:
- `data/market_data_1D.parquet`
- `data/market_data_4H.parquet`

Important note on data coverage:
- The system supports both Daily and 4H data.
- In the Backtrader validator, some symbols have real 4H execution data and others fall back to Daily execution.
- The mixed-feed validator explicitly supports “4H execution + Daily signals” where available, and a “Daily fallback” mode otherwise.

In the completed long and short validations so far, the validator reported:
- `4` symbols with real `4H -> 1D` mixed coverage
- `6` symbols using Daily fallback

So the system is partially intraday-aware, but not fully intraday for every symbol in the watchlist.

---

## 4. High-Level Research Architecture

The project has been built in distinct phases:

1. Daily long-only discovery using a wide parameter relaxation sweep
2. Daily long-only chronological Backtrader validation
3. Long survivor analysis and shortlist generation
4. Long Daily + 4H confirmation sweep
5. Long Daily + 4H Backtrader validation
6. Long final shortlist generation
7. Short-only discovery as a fully separate phase
8. Short-only Backtrader validation
9. Short survivor analysis and shortlist generation
10. Short Daily + 4H confirmation phase started, with targeted sweep completed and Backtrader validation currently in progress

The key design decision was:
- optimize and validate longs first,
- optimize and validate shorts separately afterward,
- only combine them at the end once both modules have independently survived.

That decision was made because crypto long and short behavior are not assumed to be symmetric, and because mixing unproven long and short branches too early can obscure attribution of performance, drawdown, and consistency problems.

---

## 5. Main Strategy Logic

### 5.1 Long Daily logic

The Daily long discovery and validation logic used this confluence:

- `close > SMA`
- retracement inside a fib zone using:
  - `retracement = (rolling_high - close) / (rolling_high - rolling_low)`
  - valid when `fib_floor <= retracement <= fib_band`
- price near EMA within a configured EMA buffer
- downside pullback / relative weakness threshold satisfied over a configurable lookback

The long side uses:
- Daily EMA exit proxy in the lightweight vectorized stage
- ATR stop and ATR targets in Backtrader

### 5.2 Short Daily logic

The short side mirrors the long architecture structurally, but it is not treated as simply the inverse system philosophically.

Short confluence:
- `close < SMA`
- price inside a short bounce zone using:
  - `bounce_retracement = (close - rolling_low) / (rolling_high - rolling_low)`
  - valid when `fib_floor <= bounce_retracement <= fib_band`
- price near EMA within a configured EMA buffer
- downside momentum threshold satisfied:
  - `(prev_close - close) / prev_close >= rw`

Short exit proxy in the vectorized stage:
- `close > EMA`

Short Backtrader trade management:
- short entry
- stop above entry
- TP1 and TP2 below entry
- 50% / 50% scale-out

### 5.3 4H confirmation logic

The 4H layer is intentionally a filter only.

It does not generate its own trades.

For longs:
- price must be above a 4H EMA
- and above it by at least a minimum distance threshold

For shorts:
- price must be below a 4H EMA
- and below it by at least a minimum distance threshold

This layer exists to improve trade quality, not to define a completely separate system.

---

## 6. Key Scripts In The Repo

### Long discovery and validation

- `scripts/vectorbt_wider_sweep_v2.py`
  - Daily-only long sweep across all 10 assets
  - dependency-light and numba-style rather than relying on unstable direct vectorbt imports
  - writes full sweep results, candidate file, top candidates, and markdown summary

- `scripts/prepare_backtrader_shortlist.py`
  - compresses large vectorized candidate pools into a representative shortlist for Backtrader
  - deduplicates by outcome signature and controls per-symbol sampling

- `scripts/backtrader_evaluate.py`
  - the main long-side chronological validator
  - enforces Maven rules
  - supports mixed Daily + 4H feeds
  - supports optional 4H confirmation columns in candidate files

- `scripts/analyze_backtrader_survivors.py`
  - reads validated Backtrader results
  - filters survivors
  - ranks survivors with a weighted composite score
  - writes:
    - ranking CSV
    - source asset stats CSV
    - markdown report
  - this script was later generalized so it works for both long and short phases

### Long 4H phase

- `scripts/vectorbt_4h_confirmation_sweep.py`
  - targeted 4H confirmation sweep for the validated long survivors

- `documents/4h_confirmation_runbook.md`
  - exact command order for the long 4H phase

### Short discovery and validation

- `scripts/vectorbt_short_sweep.py`
  - short-only Daily discovery sweep
  - mirrors the architecture and style of the long Daily sweep

- `scripts/backtrader_evaluate_short.py`
  - short-only Backtrader validator
  - supports optional short-side 4H confirmation fields already

- `scripts/build_short_final_shortlist.py`
  - builds the final short shortlist from ranked short survivors
  - removes exact duplicate outcome signatures

- `documents/short_optimization_runbook.md`
  - exact command order for the short Daily-only phase

### Short 4H phase

- `scripts/vectorbt_short_4h_confirmation_sweep.py`
  - targeted short Daily + 4H confirmation sweep
  - base set comes from short survivors

- `scripts/backtrader_evaluate_short_4h.py`
  - wrapper around the short Backtrader engine
  - gives the short + 4H phase its own entrypoint and output naming

- `documents/short_4h_confirmation_runbook.md`
  - exact command order for the short + 4H phase

### Supporting analysis artifacts

- `results/*.csv`
- `results/*.md`
- run logs in `results/*run.log` and `results/*run.err.log`

---

## 7. Daily Long Discovery Phase

### Problem at the start

The long strategy was suffering from severe trade starvation even after earlier relaxations. A large Daily-only sweep across all 10 assets produced no candidates passing the existing gates.

### Requested wider Daily ranges

The next wider sweep used:

- SMA Window: `30` to `90`, step `5`
- Relative Weakness Threshold: `0.002` to `0.055`, step `0.003`
- Fibonacci Band: `0.236` to `0.786`, step `0.05`
- EMA Buffer: `0.003` to `0.070`, step `0.005`
- Relative Weakness Lookback: `8, 10, 12, 14, 18, 21, 25`

Temporary relaxed gates for discovery:
- total trades `>= 12`
- win rate `>= 35%`
- expectancy `>= $1.00`

### Long Daily wider sweep results

File:
- `results/daily_wider_v2_optimization_summary.md`

Results:
- `3,112,200` rows written
- `311,220` combinations per symbol
- `3,893` relaxed candidates
- success target of `100+` candidates was comfortably exceeded

Key output files:
- `results/daily_wider_v2_sweep_results.csv`
- `results/daily_wider_v2_candidates.csv`
- `results/daily_wider_v2_top_candidates.csv`
- `results/daily_wider_v2_optimization_summary.md`

### Long shortlist compression for Backtrader

The large candidate pool was reduced into a smaller representative candidate file:

- `results/daily_wider_v2_backtrader_shortlist.csv`
- `results/daily_wider_v2_backtrader_shortlist_summary.md`

The shortlist size was:
- `68` representative candidates

Distribution notes from that stage:
- candidate pool was concentrated in `SOL`, `AVAX`, `ETH`, and `XRP`
- weaker or no support from `LINK`, `DOGE`, `BNB`, `BTC`, `TON`, and `ADA`

---

## 8. Long Daily Backtrader Validation Phase

Main validator:
- `scripts/backtrader_evaluate.py`

Outputs:
- `results/backtrader_validation_results.csv`
- `results/backtrader_validation_summary.md`

Results:
- `68` candidates evaluated
- `7` survivors
- `48` trailing drawdown breaches

Summary stats from `results/backtrader_validation_summary.md`:
- median max DD: `3.22%`
- median consistency score: `143.06`
- best expectancy: `2.24`
- best total return: `3.63%`

### Long Daily survivor analysis

Files:
- `results/backtrader_survivor_report.md`
- `results/backtrader_survivor_ranking.csv`
- `results/backtrader_survivor_asset_stats.csv`

Key findings:
- Only `AVAX/USDT` and `ETH/USDT` survived
- `ETH` was broader by survivor count
- `AVAX` had the stronger edge
- the best overall long daily candidate was:
  - `cand_002_AVAX_USDT`

Top daily long survivors:
1. `cand_002_AVAX_USDT`
2. `cand_008_AVAX_USDT`
3. `cand_028_ETH_USDT`
4. `cand_023_ETH_USDT`
5. `cand_030_ETH_USDT`

Notable qualitative conclusion:
- the long survivor pool was narrow and concentrated
- `cand_031_ETH_USDT` and `cand_032_ETH_USDT` were effectively duplicates

---

## 9. Long 4H Confirmation Phase

The long methodology was then extended with a targeted 4H confirmation layer rather than another full grid sweep.

### Long 4H sweep

Script:
- `scripts/vectorbt_4h_confirmation_sweep.py`

Purpose:
- load the already-surviving long candidates
- sweep a small 4H confirmation grid
- generate combined Daily + 4H candidate rows

### Long 4H Backtrader validation

Results file:
- `results/backtrader_4h_validation_results.csv`

Summary file:
- `results/backtrader_4h_validation_summary.md`

Results:
- `84` candidates evaluated
- `41` survivors
- `24` breached accounts

Key performance summary:
- median max DD: `2.07%`
- median consistency score: `17.46`
- best expectancy: `2.11`
- best total return: `2.87%`

### Long 4H survivor analysis

Files:
- `results/backtrader_4h_survivor_report.md`
- `results/backtrader_4h_survivor_ranking.csv`
- `results/backtrader_4h_survivor_asset_stats.csv`

Key findings:
- `AVAX` dominated the long + 4H phase
- `ETH` remained present but secondary
- the 4H layer acted like a real quality gate:
  - fewer trades,
  - similar or slightly lower win rate,
  - improved drawdown control,
  - acceptable expectancy retention

Best long + 4H candidate:
- `cand_002_AVAX_USDT__4h_ema15_dist0.008`

### Final long shortlist

Files:
- `results/backtrader_4h_final_shortlist.csv`
- `results/backtrader_4h_final_shortlist.md`

Final recommended long candidates:
1. `cand_002_AVAX_USDT__4h_ema15_dist0.008`
2. `cand_002_AVAX_USDT__4h_ema20_dist0.008`
3. `cand_002_AVAX_USDT__4h_ema15_dist0.000`
4. `cand_008_AVAX_USDT__4h_ema15_dist0.008`
5. `cand_028_ETH_USDT__4h_ema15_dist0.000`

Interpretation:
- AVAX is the core long edge family
- ETH is kept as the main diversifier

---

## 10. Short Discovery Phase

After the long side was finalized, a separate short-only optimization phase was built instead of mixing long and short together.

This was a deliberate architectural decision:
- shorts are not assumed to be mirror images of longs in crypto,
- they need separate discovery and separate validation,
- and they should only be combined later after both sides stand on their own.

### Short Daily sweep

Script:
- `scripts/vectorbt_short_sweep.py`

This mirrored the same wider relaxed ranges used for longs:
- SMA `30-90` step `5`
- fib band `0.236-0.786` step `0.05`
- rw `0.002-0.055` step `0.003`
- eb `0.003-0.070` step `0.005`
- rw lookback `8, 10, 12, 14, 18, 21, 25`

Relaxed gates:
- total trades `>= 12`
- win rate `>= 35%`
- expectancy `>= $1.00`

### Short Daily sweep results

Summary file:
- `results/short_optimization_summary.md`

Results:
- `3,112,200` rows written
- `258,004` relaxed candidates
- elapsed about `157` seconds

Important qualitative result:
- the short side was far more fertile than the long side at the raw discovery stage

Candidate counts by symbol from the short discovery stage were roughly:
- `SOL`: 59k+
- `ETH`: 55k+
- `TON`: 36k+
- `DOGE`: 32k+
- `AVAX`: 31k+
- `BTC`: 19k+
- `LINK`: 14k+
- `ADA`: 7.8k+
- `XRP`: 801
- `BNB`: 542

### Short Backtrader shortlist compression

Using:
- `scripts/prepare_backtrader_shortlist.py`

Outputs:
- `results/short_backtrader_shortlist.csv`
- `results/short_backtrader_shortlist_summary.md`

Result:
- `150` Backtrader candidates
- `15` per symbol

---

## 11. Short Daily Backtrader Validation Phase

Main validator:
- `scripts/backtrader_evaluate_short.py`

Outputs:
- `results/backtrader_short_results.csv`
- `results/backtrader_short_summary.md`

Results:
- `150` candidates evaluated
- `53` survivors
- `90` breaches

Summary stats:
- median max DD: `3.12%`
- median consistency score: `31.03`
- best expectancy: `3.31`
- best total return: `5.09%`

### Short survivor analysis

Files:
- `results/backtrader_short_survivor_report.md`
- `results/backtrader_short_survivor_ranking.csv`
- `results/backtrader_short_survivor_asset_stats.csv`

Key findings:
- the best short family is not AVAX or ETH-long-style
- the best short edge emerged from `DOGE`
- `ETH` is the main short diversifier
- `BNB` also has a meaningful secondary family

Source family survivor counts:
- `DOGE`: 13
- `ETH`: 12
- `BNB`: 11
- `XRP`: 7
- `LINK`: 5
- `BTC`: 4
- `SOL`: 1
- `ADA`: 0
- `AVAX`: 0
- `TON`: 0

Best short candidate:
- `short_cand_061_DOGE_USDT`

Top ranked short survivors:
1. `short_cand_061_DOGE_USDT`
2. `short_cand_062_DOGE_USDT`
3. `short_cand_070_DOGE_USDT`
4. `short_cand_076_ETH_USDT`
5. `short_cand_075_DOGE_USDT`

Important structural insights:
- the best short edge is in a high-SMA DOGE regime rather than the low-SMA regime that was more common in count terms
- top DOGE short cluster:
  - mostly `SMA 75-80`
  - `fib_band 0.636-0.686`
  - `rw_lookback 10`
  - `eb 0.028`
  - `rw 0.041-0.050`
- ETH short cluster:
  - mostly `SMA 75`
  - `fib_band 0.486-0.536`
  - `rw 0.011`
  - `eb 0.023`
  - `rw_lookback 8`

Risk observations:
- only `1` short survivor sat within two percentage points of the `20%` consistency ceiling
- `4` exact duplicate outcome signatures existed among short survivors and needed deduplication

### Final short Daily shortlist

Files:
- `results/backtrader_short_final_shortlist.csv`
- `results/backtrader_short_final_shortlist.md`

Final recommended short candidates:
1. `short_cand_061_DOGE_USDT`
2. `short_cand_062_DOGE_USDT`
3. `short_cand_070_DOGE_USDT`
4. `short_cand_076_ETH_USDT`
5. `short_cand_075_DOGE_USDT`

Interpretation:
- DOGE is the short core edge family
- ETH is the main short diversifier

---

## 12. Short 4H Confirmation Phase

The short Daily-only phase was considered incomplete methodologically because the long side had already passed through a 4H confirmation layer.

To make the methodology symmetric, a new short Daily + 4H confirmation phase was created.

### New short 4H scripts created

- `scripts/vectorbt_short_4h_confirmation_sweep.py`
- `scripts/backtrader_evaluate_short_4h.py`
- `documents/short_4h_confirmation_runbook.md`

Design:
- base set is not a new full grid
- base set comes from the short survivors
- default uses the top `20` short survivors from `results/backtrader_short_survivor_ranking.csv`
- 4H grid is compact:
  - EMA periods: `15, 20, 25, 30`
  - min distances: `0.000, 0.004, 0.008`

This produces:
- `20 * 12 = 240` combined short + 4H candidates

### Short 4H sweep status

Completed.

Files:
- `results/short_4h_sweep_results.csv`
- `results/short_plus_4h_candidates.csv`
- `results/short_4h_optimization_summary.md`

Summary:
- base short survivors used: `20`
- combined rows: `240`
- candidate rows exported for Backtrader: `240`

Important caution:
- the vectorized short + 4H metrics in this phase show some extremely large expectancy values and relatively weak win rates in the top rows. These are discovery-stage approximations only and should not be trusted without Backtrader chronology.

### Short 4H Backtrader validation status

This phase has been started but is **not confirmed complete yet**.

Current state at the time this handoff was written:
- file exists: `results/backtrader_short_4h_results.csv`
- current flushed rows observed: `20`
- current observed survivors in flushed rows: `15`
- current observed breaches in flushed rows: `0`
- first few rows indicate the validator is evaluating short + 4H candidates correctly
- summary file `results/backtrader_short_4h_summary.md` does **not** exist yet
- log files:
  - `results/backtrader_short_4h_run.log`
  - `results/backtrader_short_4h_run.err.log`
  are currently empty

There are active Python processes in the environment, so the short + 4H validation may still be running in the background, but it has not yet been fully verified complete.

The first flushed rows in `results/backtrader_short_4h_results.csv` already show that:
- the short 4H confirmation fields are being read correctly
- `confirm_mode = close_below_ema`
- `confirm_ema_period` and `confirm_min_distance` are flowing through into the validator
- some candidates are already surviving

Example early rows:
- `short_cand_068_DOGE_USDT__4h_ema20_dist0.000`
  - 40 trades
  - win rate 0.55
  - expectancy 1.6667
  - max DD 1.6582%
  - survived
- `short_cand_062_DOGE_USDT__4h_ema20_dist0.000`
  - 51 trades
  - win rate 0.5882
  - expectancy 2.1553
  - max DD 1.7639%
  - survived

So the short + 4H engine appears operational, but the final result set has not yet been finalized.

---

## 13. Current Best Candidates Across The Project

### Best long candidates

Final long shortlist:
1. `cand_002_AVAX_USDT__4h_ema15_dist0.008`
2. `cand_002_AVAX_USDT__4h_ema20_dist0.008`
3. `cand_002_AVAX_USDT__4h_ema15_dist0.000`
4. `cand_008_AVAX_USDT__4h_ema15_dist0.008`
5. `cand_028_ETH_USDT__4h_ema15_dist0.000`

Best single long candidate:
- `cand_002_AVAX_USDT__4h_ema15_dist0.008`

### Best short candidates

Current final short Daily-only shortlist:
1. `short_cand_061_DOGE_USDT`
2. `short_cand_062_DOGE_USDT`
3. `short_cand_070_DOGE_USDT`
4. `short_cand_076_ETH_USDT`
5. `short_cand_075_DOGE_USDT`

Best single short Daily-only candidate:
- `short_cand_061_DOGE_USDT`

### Most likely combined structure later

If the short + 4H phase succeeds, the final combined system will likely be built from:
- AVAX-led long core
- ETH long diversifier
- DOGE-led short core
- ETH short diversifier

But this combined portfolio step has **not** been done yet and should only be done after the short + 4H phase is fully complete.

---

## 14. Important Project-Level Conclusions So Far

### Long side conclusions

- The original long Daily discovery problem was trade starvation.
- Very wide relaxation solved discovery but not necessarily final robustness.
- Chronological validation compressed the long edge into a narrow AVAX/ETH family.
- The 4H confirmation layer improved long-side quality and drawdown control.
- AVAX is clearly the strongest long family.

### Short side conclusions

- The short side produced far more raw discovery candidates than the long side.
- Chronological validation showed the strongest short edge in DOGE, not in AVAX.
- ETH is the main short diversifier.
- The short side appears richer and broader than the long side at the Daily-only stage.
- The short + 4H phase is necessary before combined portfolio work so the methodology stays symmetric.

### Engineering conclusions

- Vectorized discovery is useful for search-space reduction, but not sufficient for trust.
- Backtrader chronology is the real gate.
- Long and short should remain separate branches until fully validated.
- The codebase has evolved toward a modular phase-by-phase pipeline rather than one giant script.

---

## 15. Operational Notes About The Codebase

### Style and readability requirement

The user explicitly asked that code be heavily commented and easy to understand “at a glance” for a vibe-coding workflow.

That means:
- new code should include clear comments,
- names should remain explicit and descriptive,
- runbook docs are preferred,
- and small wrapper scripts are acceptable if they improve clarity.

### Long-running runs and logs

The project has used a mix of:
- foreground command runs,
- and background `Start-Process` runs with stdout/stderr logs.

The user does not like “silent” long runs, so future work should ideally:
- either run in the foreground,
- or make log tails explicit and easy to monitor.

### Important runbooks already present

- `documents/4h_confirmation_runbook.md`
- `documents/short_optimization_runbook.md`
- `documents/short_4h_confirmation_runbook.md`

---

## 16. Exact Important Files To Know

### Core long artifacts

- `scripts/vectorbt_wider_sweep_v2.py`
- `scripts/backtrader_evaluate.py`
- `scripts/vectorbt_4h_confirmation_sweep.py`
- `results/daily_wider_v2_sweep_results.csv`
- `results/daily_wider_v2_candidates.csv`
- `results/daily_wider_v2_backtrader_shortlist.csv`
- `results/backtrader_validation_results.csv`
- `results/backtrader_survivor_report.md`
- `results/backtrader_4h_validation_results.csv`
- `results/backtrader_4h_survivor_report.md`
- `results/backtrader_4h_final_shortlist.csv`

### Core short artifacts

- `scripts/vectorbt_short_sweep.py`
- `scripts/backtrader_evaluate_short.py`
- `scripts/build_short_final_shortlist.py`
- `results/short_wider_sweep_results.csv`
- `results/short_candidates.csv`
- `results/short_backtrader_shortlist.csv`
- `results/backtrader_short_results.csv`
- `results/backtrader_short_survivor_report.md`
- `results/backtrader_short_final_shortlist.csv`

### Short 4H phase artifacts

- `scripts/vectorbt_short_4h_confirmation_sweep.py`
- `scripts/backtrader_evaluate_short_4h.py`
- `results/short_4h_sweep_results.csv`
- `results/short_plus_4h_candidates.csv`
- `results/backtrader_short_4h_results.csv` (partial / in progress at time of handoff)
- `documents/short_4h_confirmation_runbook.md`

---

## 17. What Is Done Versus What Is Still Pending

### Fully completed

- Long Daily wider discovery
- Long Daily Backtrader validation
- Long survivor analysis
- Long 4H confirmation sweep
- Long 4H Backtrader validation
- Long final shortlist
- Short Daily discovery
- Short Daily Backtrader validation
- Short survivor analysis
- Short final Daily-only shortlist
- Short 4H targeted sweep
- Short 4H code infrastructure

### In progress / not yet finalized

- Full short + 4H Backtrader validation
- Short + 4H survivor report
- Short + 4H final shortlist
- Final combined long + short portfolio validation

### Not started yet

- Final long + short portfolio combination under one portfolio-level validator
- Comparative portfolio study:
  - long-only
  - short-only
  - combined long + short
- walk-forward or out-of-sample deployment phase after both branches are locked

---

## 18. Recommended Immediate Next Steps

The next clean sequence is:

1. Confirm whether `results/backtrader_short_4h_results.csv` is still actively being written or whether the background run stalled
2. If it stalled, rerun:
   - `python scripts\\backtrader_evaluate_short_4h.py`
3. When the short + 4H Backtrader run completes, generate:
   - `results/backtrader_short_4h_survivor_ranking.csv`
   - `results/backtrader_short_4h_survivor_asset_stats.csv`
   - `results/backtrader_short_4h_survivor_report.md`
4. Build:
   - `results/backtrader_short_4h_final_shortlist.csv`
   - `results/backtrader_short_4h_final_shortlist.md`
5. Only after that, begin the final combined portfolio phase that merges:
   - top long + 4H candidates
   - top short + 4H candidates

---

## 19. Best Single-Sentence Summary Of The Project

TRADE_ORACLE is a Maven-prop-firm-focused crypto trading research pipeline that has already produced a narrow AVAX-led long system with 4H confirmation, a DOGE-led short system at the Daily-only stage, and is currently finishing the short-side 4H confirmation validation before the final combined long + short portfolio phase.

