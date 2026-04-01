# Backtrader Survivor Analysis Report

## Overview

- **survivors_found**: 7
- **source_assets_with_survivors**: ETH/USDT, AVAX/USDT
- **best_overall_candidate**: cand_002_AVAX_USDT
- **best_expectancy**: 2.2428
- **best_win_rate**: 0.6049
- **lowest_max_dd_pct**: 2.0124
- **best_consistency_score**: 6.4220

## Ranking Table

| analysis_rank | param_id | source_symbol | win_rate | expectancy | max_dd_pct | consistency_score | composite_score |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | cand_002_AVAX_USDT | AVAX/USDT | 0.6049 | 2.2428 | 2.0124 | 6.422 | 100.0 |
| 2 | cand_008_AVAX_USDT | AVAX/USDT | 0.5765 | 1.6667 | 2.3164 | 8.2353 | 67.3889 |
| 3 | cand_028_ETH_USDT | ETH/USDT | 0.5139 | 1.1582 | 2.6241 | 13.9903 | 21.5481 |
| 4 | cand_023_ETH_USDT | ETH/USDT | 0.5147 | 1.1479 | 2.6283 | 14.9458 | 19.9661 |
| 5 | cand_030_ETH_USDT | ETH/USDT | 0.5072 | 1.0878 | 2.6283 | 15.5435 | 15.8346 |
| 6 | cand_031_ETH_USDT | ETH/USDT | 0.5169 | 0.6611 | 2.4271 | 19.8286 | 8.9936 |
| 7 | cand_032_ETH_USDT | ETH/USDT | 0.5169 | 0.6611 | 2.4271 | 19.8286 | 8.9936 |

## Source Asset Analysis

These stats use the full validation set, not just the survivors, so they show which source-asset parameter families held up best under chronological testing.

| source_symbol | candidates_tested | survivors | survival_rate_pct | best_expectancy | median_max_dd_pct |
| --- | --- | --- | --- | --- | --- |
| ETH/USDT | 15 | 5 | 33.3333 | 1.166 | 3.0268 |
| AVAX/USDT | 15 | 2 | 13.3333 | 2.2428 | 2.8252 |
| LINK/USDT | 6 | 0 | 0.0 | 1.1763 | 4.4993 |
| SOL/USDT | 15 | 0 | 0.0 | 0.8526 | 3.144 |
| XRP/USDT | 15 | 0 | 0.0 | 0.4689 | 3.3878 |
| BNB/USDT | 1 | 0 | 0.0 | -0.6383 | 2.5486 |
| DOGE/USDT | 1 | 0 | 0.0 | -1.4657 | 3.0435 |

## Parameter Pattern Analysis

- **SMA distribution**: {30: 6, 35: 1}
- **Fib band distribution**: {0.436: 5, 0.536: 2}
- **RW lookback distribution**: {25: 3, 21: 2, 18: 2}
- **EMA buffer distribution**: {0.053: 3, 0.068: 2, 0.038: 1, 0.043: 1}
- **Interpretation**: all survivors stayed in the low-SMA regime (30-35), all retained the same 0.236 fib floor, and only the AVAX and ETH source neighborhoods survived chronological validation.
- **Interpretation**: AVAX produced the strongest edge per candidate, while ETH produced the wider and more redundant survivor family.
- **Interpretation**: candidates 31 and 32 are effectively threshold duplicates because they produced identical Backtrader outcome metrics.

## Survivor-by-Survivor Detail

### 1. cand_002_AVAX_USDT

- **source_symbol**: AVAX/USDT
- **exact_parameters**: SMA=35, EMA=20, fib_floor=0.236, fib_band=0.436, rw=0.002, eb=0.068, rw_lookback=21
- **cluster_label**: AVAX/USDT | fib=0.436 | rw_lb=21 (cluster size 2)
- **backtrader_metrics**: total_trades=81, win_rate=0.6049, expectancy=2.2428, max_dd_pct=2.0124, consistency_score=6.4220
- **headroom**: drawdown_headroom=0.9876 pct points, consistency_headroom=13.5780 pct points
- **composite_score**: 100.00
- **ai_note**: Best overall balance in the survivor pool. Highest expectancy of all survivors. Highest win rate of all survivors. Tightest trailing drawdown control. Safest consistency profile. Belongs to the highest-edge AVAX parameter family.

### 2. cand_008_AVAX_USDT

- **source_symbol**: AVAX/USDT
- **exact_parameters**: SMA=30, EMA=20, fib_floor=0.236, fib_band=0.436, rw=0.002, eb=0.068, rw_lookback=21
- **cluster_label**: AVAX/USDT | fib=0.436 | rw_lb=21 (cluster size 2)
- **backtrader_metrics**: total_trades=85, win_rate=0.5765, expectancy=1.6667, max_dd_pct=2.3164, consistency_score=8.2353
- **headroom**: drawdown_headroom=0.6836 pct points, consistency_headroom=11.7647 pct points
- **composite_score**: 67.39
- **ai_note**: Belongs to the highest-edge AVAX parameter family.

### 3. cand_028_ETH_USDT

- **source_symbol**: ETH/USDT
- **exact_parameters**: SMA=30, EMA=20, fib_floor=0.236, fib_band=0.436, rw=0.005, eb=0.053, rw_lookback=25
- **cluster_label**: ETH/USDT | fib=0.436 | rw_lb=25 (cluster size 3)
- **backtrader_metrics**: total_trades=72, win_rate=0.5139, expectancy=1.1582, max_dd_pct=2.6241, consistency_score=13.9903
- **headroom**: drawdown_headroom=0.3759 pct points, consistency_headroom=6.0097 pct points
- **composite_score**: 21.55
- **ai_note**: Limited drawdown headroom below the 3% trailing cap. Belongs to the more redundant ETH parameter family.

### 4. cand_023_ETH_USDT

- **source_symbol**: ETH/USDT
- **exact_parameters**: SMA=30, EMA=20, fib_floor=0.236, fib_band=0.436, rw=0.011, eb=0.053, rw_lookback=25
- **cluster_label**: ETH/USDT | fib=0.436 | rw_lb=25 (cluster size 3)
- **backtrader_metrics**: total_trades=68, win_rate=0.5147, expectancy=1.1479, max_dd_pct=2.6283, consistency_score=14.9458
- **headroom**: drawdown_headroom=0.3717 pct points, consistency_headroom=5.0542 pct points
- **composite_score**: 19.97
- **ai_note**: Limited drawdown headroom below the 3% trailing cap. Belongs to the more redundant ETH parameter family.

### 5. cand_030_ETH_USDT

- **source_symbol**: ETH/USDT
- **exact_parameters**: SMA=30, EMA=20, fib_floor=0.236, fib_band=0.436, rw=0.008, eb=0.053, rw_lookback=25
- **cluster_label**: ETH/USDT | fib=0.436 | rw_lb=25 (cluster size 3)
- **backtrader_metrics**: total_trades=69, win_rate=0.5072, expectancy=1.0878, max_dd_pct=2.6283, consistency_score=15.5435
- **headroom**: drawdown_headroom=0.3717 pct points, consistency_headroom=4.4565 pct points
- **composite_score**: 15.83
- **ai_note**: Limited drawdown headroom below the 3% trailing cap. Belongs to the more redundant ETH parameter family.

### 6. cand_031_ETH_USDT

- **source_symbol**: ETH/USDT
- **exact_parameters**: SMA=30, EMA=20, fib_floor=0.236, fib_band=0.536, rw=0.014, eb=0.038, rw_lookback=18
- **cluster_label**: ETH/USDT | fib=0.536 | rw_lb=18 (cluster size 2)
- **backtrader_metrics**: total_trades=89, win_rate=0.5169, expectancy=0.6611, max_dd_pct=2.4271, consistency_score=19.8286
- **headroom**: drawdown_headroom=0.5729 pct points, consistency_headroom=0.1714 pct points
- **composite_score**: 8.99
- **ai_note**: Very close to the 20% consistency ceiling. Shares identical outcome metrics with another survivor; treat as a threshold duplicate. Belongs to the more redundant ETH parameter family.

### 7. cand_032_ETH_USDT

- **source_symbol**: ETH/USDT
- **exact_parameters**: SMA=30, EMA=20, fib_floor=0.236, fib_band=0.536, rw=0.014, eb=0.043, rw_lookback=18
- **cluster_label**: ETH/USDT | fib=0.536 | rw_lb=18 (cluster size 2)
- **backtrader_metrics**: total_trades=89, win_rate=0.5169, expectancy=0.6611, max_dd_pct=2.4271, consistency_score=19.8286
- **headroom**: drawdown_headroom=0.5729 pct points, consistency_headroom=0.1714 pct points
- **composite_score**: 8.99
- **ai_note**: Very close to the 20% consistency ceiling. Shares identical outcome metrics with another survivor; treat as a threshold duplicate. Belongs to the more redundant ETH parameter family.

## AI Conclusions

- **Best source asset family**: ETH/USDT by survivor count / survival rate, but the strongest single candidate is cand_002_AVAX_USDT.
- **Top deployment shortlist**: cand_002_AVAX_USDT, cand_008_AVAX_USDT, cand_028_ETH_USDT, cand_023_ETH_USDT, cand_030_ETH_USDT
- **Practical view**: keep both AVAX survivors, keep the best three ETH survivors, and treat the final ETH duplicate pair as a lower-priority reserve unless you want extra redundancy.
- **Risk view**: none of the 7 survivors are loose on trailing drawdown, but the ETH tail candidates are much closer to the 20% consistency ceiling than the AVAX pair.
