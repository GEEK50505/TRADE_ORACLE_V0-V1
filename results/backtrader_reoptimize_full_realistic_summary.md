# Backtrader realistic shortlist re-optimization summary

- **objective**: maximize expectancy under the corrected 34-month realistic baseline portfolio engine
- **baseline_friction_preset**: baseline
- **candidate_pairs_in_pool**: 25
- **standalone_realistic_survivors**: 8
- **unique_portfolios_evaluated**: 195
- **target_shortlist_size**: 5
- **search_method**: deterministic forward selection plus bounded swap refinement
- **note**: the portfolio objective includes a small diversity penalty to avoid near-clone concentration.
- **swap_rounds**: 1

## Portfolio Comparison

| portfolio_label | portfolio_param_ids | expectancy | penalized_expectancy | total_profit | max_dd_pct | consistency_score | overall_survival | stacked_same_side_entries | diversity_penalty | stacking_profit_delta_vs_netted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| old_shortlist | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema15_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema15_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | -1.0944 | -2.9444 | -74.4190 | 3.9271 | 999.0000 | False | 30 | 1.8500 | -429.4428 |
| new_shortlist | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 1.8921 | 0.7921 | 143.8024 | 3.0446 | 7.9278 | False | 24 | 1.1000 | -211.2214 |

## New Final Shortlist

| shortlist_priority | param_id | long_param_id | short_param_id | expectancy | max_dd_pct | overall_survival | portfolio_penalized_expectancy | portfolio_diversity_penalty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 1.1962 | 1.7764 | True | 0.7921 | 1.1000 |
| 2 | combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | cand_028_ETH_USDT__4h_ema15_dist0.000 | short_cand_076_ETH_USDT__4h_ema15_dist0.000 | -0.2785 | 3.1464 | False | 0.7921 | 1.1000 |
| 3 | combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000 | cand_008_AVAX_USDT__4h_ema15_dist0.008 | short_cand_082_ETH_USDT__4h_ema20_dist0.000 | -0.8534 | 3.4691 | False | 0.7921 | 1.1000 |
| 4 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | cand_002_AVAX_USDT__4h_ema15_dist0.000 | short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 0.9198 | 2.5573 | True | 0.7921 | 1.1000 |
| 5 | combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | cand_002_AVAX_USDT__4h_ema20_dist0.008 | short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 0.8859 | 2.1053 | True | 0.7921 | 1.1000 |

## Old vs New Pair Table

| portfolio_label | shortlist_priority | param_id | standalone_expectancy | standalone_max_dd_pct | standalone_overall_survival | realized_pair_total_profit | stacking_impact_proxy_avg_support_pair_count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| new_shortlist | 1 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 1.1962 | 1.7764 | True | 37.0733 | 1.0000 |
| new_shortlist | 2 | combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | -0.2785 | 3.1464 | False | 54.6959 | 1.0000 |
| new_shortlist | 3 | combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000 | -0.8534 | 3.4691 | False | 51.3369 | 1.0000 |
| new_shortlist | 4 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 0.9198 | 2.5573 | True | -4.6518 | 1.0000 |
| new_shortlist | 5 | combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 0.8859 | 2.1053 | True | 5.3482 | 1.0000 |
| old_shortlist | 1 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | -1.0455 | 3.0264 | False | -9.6971 | 1.0000 |
| old_shortlist | 2 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | -1.1719 | 3.1897 | False | -22.3718 | 1.0000 |
| old_shortlist | 3 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema15_dist0.000 | -0.7932 | 3.0320 | False | -27.9788 | 1.0000 |
| old_shortlist | 4 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema15_dist0.000 | -0.9772 | 3.0388 | False | -14.3713 | 1.0000 |
| old_shortlist | 5 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | -0.9361 | 3.1072 | False | 0.0000 | 0.0000 |

## Top Evaluated Target-Size Portfolios

| portfolio_param_ids | overall_survival | penalized_expectancy | expectancy | max_dd_pct | consistency_score | diversity_penalty | stacked_same_side_entries | first_seen_stage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | False | 0.7921 | 1.8921 | 3.0446 | 7.9278 | 1.1000 | 24 | forward_step_5 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | False | 0.7053 | 1.8053 | 3.2162 | 7.6412 | 1.1000 | 28 | swap_round_1 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | False | 0.6193 | 1.7693 | 3.1858 | 8.0542 | 1.1500 | 26 | swap_round_1 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | False | 0.5893 | 1.7393 | 3.0504 | 8.5124 | 1.1500 | 24 | forward_step_5 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema15_dist0.000|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | False | 0.5459 | 1.5959 | 3.3100 | 8.8598 | 1.0500 | 27 | swap_round_1 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | False | 0.5399 | 1.6399 | 3.0959 | 8.5824 | 1.1000 | 28 | swap_round_1 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | False | 0.5209 | 1.6209 | 3.0960 | 8.6829 | 1.1000 | 28 | forward_step_5 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema15_dist0.000 | False | 0.5209 | 1.6209 | 3.0960 | 8.6829 | 1.1000 | 28 | forward_step_5 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | False | 0.5204 | 1.6204 | 3.0968 | 8.6858 | 1.1000 | 28 | swap_round_1 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | False | 0.5143 | 1.6643 | 3.0082 | 8.7822 | 1.1500 | 26 | swap_round_1 |

## Membership Change

- **kept_pairs**: none
- **added_pairs**: combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004, combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000, combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000, combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004, combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004
- **removed_pairs**: combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000, combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema20_dist0.000, combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema15_dist0.000, combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema15_dist0.000, combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000
