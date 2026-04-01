# Backtrader Combined Survivor Analysis Report

## Overview

- **survivors_found**: 2
- **best_overall_pair**: combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_061_DOGE_USDT
- **best_expectancy**: 2.0981
- **best_win_rate**: 0.5943
- **lowest_max_dd_pct**: 1.9764
- **best_consistency_score**: 5.2459
- **pair_family_distribution**: AVAX/USDT + DOGE/USDT=2
- **long_side_distribution**: AVAX/USDT=2
- **short_side_distribution**: DOGE/USDT=2

## Ranking Table

| analysis_rank | long_param_id | short_param_id | pair_family | win_rate | expectancy | max_dd_pct | consistency_score | signal_conflicts | composite_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_061_DOGE_USDT | AVAX/USDT + DOGE/USDT | 0.5943 | 2.0981 | 1.9764 | 5.2459 | 0 | 100.0 |
| 2 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_062_DOGE_USDT | AVAX/USDT + DOGE/USDT | 0.5849 | 1.8465 | 2.1328 | 5.9606 | 0 | 0.0 |

## Pair Family Analysis

| pair_family | candidates_tested | survivors | survival_rate_pct | best_expectancy | median_max_dd_pct | median_signal_conflicts |
| --- | --- | --- | --- | --- | --- | --- |
| AVAX/USDT + DOGE/USDT | 2 | 2 | 100.0 | 2.0981 | 2.0546 | 0.0 |

- **Interpretation**: the combined survivor pool is concentrated by pair family as AVAX/USDT + DOGE/USDT=2.
- **Interpretation**: long-side contribution among survivors is AVAX/USDT=2, while short-side contribution is DOGE/USDT=2.

## Survivor-by-Survivor Detail

### 1. combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_061_DOGE_USDT

- **pair_family**: AVAX/USDT + DOGE/USDT (cluster size 2)
- **long_leg**: cand_002_AVAX_USDT__4h_ema15_dist0.008 | AVAX/USDT | SMA=35, fib_band=0.436, rw=0.002, eb=0.068, rw_lookback=21, confirm_ema_period=15, confirm_min_distance=0.008
- **short_leg**: short_cand_061_DOGE_USDT | DOGE/USDT | SMA=80, fib_band=0.686, rw=0.050, eb=0.028, rw_lookback=10, confirm_ema_period=20, confirm_min_distance=0.000
- **portfolio_metrics**: total_trades=106, long_trades=47, short_trades=59, win_rate=0.5943, expectancy=2.0981, max_dd_pct=1.9764, consistency_score=5.2459
- **profit_split**: long_total_profit=31.6667 (14.24%), short_total_profit=190.7296 (85.76%)
- **operational_detail**: signal_conflicts=0, max_concurrent_observed=4
- **headroom**: drawdown_headroom=1.0236 pct points, consistency_headroom=14.7541 pct points
- **composite_score**: 100.00
- **ai_note**: Best overall balance in the combined survivor pool. Highest expectancy among the combined survivors. Highest win rate among the combined survivors. Tightest trailing-drawdown control in the pair set. Safest consistency profile in the pair set. Portfolio profit is heavily short-dominated.

### 2. combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_062_DOGE_USDT

- **pair_family**: AVAX/USDT + DOGE/USDT (cluster size 2)
- **long_leg**: cand_002_AVAX_USDT__4h_ema15_dist0.008 | AVAX/USDT | SMA=35, fib_band=0.436, rw=0.002, eb=0.068, rw_lookback=21, confirm_ema_period=15, confirm_min_distance=0.008
- **short_leg**: short_cand_062_DOGE_USDT | DOGE/USDT | SMA=75, fib_band=0.686, rw=0.050, eb=0.028, rw_lookback=10, confirm_ema_period=20, confirm_min_distance=0.000
- **portfolio_metrics**: total_trades=106, long_trades=47, short_trades=59, win_rate=0.5849, expectancy=1.8465, max_dd_pct=2.1328, consistency_score=5.9606
- **profit_split**: long_total_profit=31.6667 (16.18%), short_total_profit=164.0629 (83.82%)
- **operational_detail**: signal_conflicts=0, max_concurrent_observed=4
- **headroom**: drawdown_headroom=0.8672 pct points, consistency_headroom=14.0394 pct points
- **composite_score**: 0.00
- **ai_note**: Portfolio profit is heavily short-dominated.

## AI Conclusions

- **Top deployment shortlist**: combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_061_DOGE_USDT, combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_062_DOGE_USDT
- **Practical view**: the strongest combined pairs currently cluster around AVAX/USDT + DOGE/USDT=2. That concentration is useful signal, but it also means we should trim exact metric clones before promoting live candidates.
- **Risk view**: none of the combined survivors are pressing tightly against the 20% consistency ceiling, which is a good sign for portfolio robustness.
