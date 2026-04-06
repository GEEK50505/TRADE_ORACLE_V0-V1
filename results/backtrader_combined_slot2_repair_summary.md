# Backtrader slot-2 repair summary

- **fixed_core_slot_1**: combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004
- **fixed_core_slot_3**: combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004
- **fixed_core_slot_4**: combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004
- **replaced_weak_slot_2**: combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000
- **slot_2_replacements_tested**: 4
- **strict_dd_threshold**: 2.9500
- **consistency_threshold**: 20.0000
- **strict_target_survivors_found**: 0
- **selected_replacement**: combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000
- **survivor_output_written**: False

## Portfolio Comparison

| portfolio_label | portfolio_param_ids | expectancy | penalized_expectancy | total_profit | max_dd_pct | consistency_score | overall_survival | stacked_same_side_entries | diversity_penalty | stacking_profit_delta_vs_netted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| old_shortlist | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema15_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema15_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | -1.0944 | -2.9444 | -74.4190 | 3.9271 | 999.0000 | False | 30 | 1.8500 | -429.4428 |
| new_realistic_shortlist | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 1.8921 | 0.7921 | 143.8024 | 3.0446 | 7.9278 | False | 24 | 1.1000 | -211.2214 |
| slot2_repair_best | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 0.4474 | -0.6026 | 34.4507 | 3.0062 | 33.0917 | False | 24 | 1.0500 | -320.5731 |

## Replacement Candidates

| analysis_rank | param_id | expectancy | max_dd_pct | consistency_score | survival_probability_proxy | composite_score |
| --- | --- | --- | --- | --- | --- | --- |
| 3 | combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | 1.0737 | 2.4405 | 5.3198 | 0.8381 | 79.6097 |
| 6 | combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | 0.9277 | 2.8588 | 6.2438 | 0.8102 | 72.4519 |
| 7 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | 0.8419 | 2.8621 | 6.2492 | 0.8100 | 66.4280 |
| 8 | combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000 | 0.8375 | 2.7323 | 6.7525 | 0.8127 | 65.0326 |

## Selected Shortlist

| shortlist_priority | param_id | long_param_id | short_param_id | expectancy | max_dd_pct | overall_survival | portfolio_penalized_expectancy | portfolio_diversity_penalty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 1.1962 | 1.7764 | True | -0.6026 | 1.0500 |
| 2 | combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | cand_002_AVAX_USDT__4h_ema20_dist0.008 | short_cand_076_ETH_USDT__4h_ema15_dist0.000 | 1.0737 | 2.4405 | True | -0.6026 | 1.0500 |
| 3 | combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | cand_002_AVAX_USDT__4h_ema20_dist0.008 | short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 0.8859 | 2.1053 | True | -0.6026 | 1.0500 |
| 4 | combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | cand_008_AVAX_USDT__4h_ema15_dist0.008 | short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 1.0027 | 2.0279 | True | -0.6026 | 1.0500 |

## Pair Comparison

| portfolio_label | shortlist_priority | param_id | standalone_expectancy | standalone_max_dd_pct | standalone_overall_survival | realized_pair_total_profit | stacking_impact_proxy_avg_support_pair_count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| new_realistic_shortlist | 1 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 1.1962 | 1.7764 | True | 37.0733 | 1.0000 |
| new_realistic_shortlist | 2 | combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | -0.2785 | 3.1464 | False | 54.6959 | 1.0000 |
| new_realistic_shortlist | 3 | combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000 | -0.8534 | 3.4691 | False | 51.3369 | 1.0000 |
| new_realistic_shortlist | 4 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 0.9198 | 2.5573 | True | -4.6518 | 1.0000 |
| new_realistic_shortlist | 5 | combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 0.8859 | 2.1053 | True | 5.3482 | 1.0000 |
| old_shortlist | 1 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | -1.0455 | 3.0264 | False | -9.6971 | 1.0000 |
| old_shortlist | 2 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | -1.1719 | 3.1897 | False | -22.3718 | 1.0000 |
| old_shortlist | 3 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema15_dist0.000 | -0.7932 | 3.0320 | False | -27.9788 | 1.0000 |
| old_shortlist | 4 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema15_dist0.000 | -0.9772 | 3.0388 | False | -14.3713 | 1.0000 |
| old_shortlist | 5 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | -0.9361 | 3.1072 | False | 0.0000 | 0.0000 |
| slot2_repair_best | 1 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 1.1962 | 1.7764 | True | 6.7752 | 1.0000 |
| slot2_repair_best | 2 | combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | 1.0737 | 2.4405 | True | 18.7015 | 1.0000 |
| slot2_repair_best | 3 | combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 0.8859 | 2.1053 | True | -3.2115 | 1.0000 |
| slot2_repair_best | 4 | combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 1.0027 | 2.0279 | True | 12.1855 | 1.0000 |

## Repair Results

| replacement_param_id | strict_target_pass | overall_survival | expectancy | penalized_expectancy | total_profit | max_dd_pct | consistency_score | diversity_penalty | stacked_same_side_entries |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | False | False | 0.4474 | -0.6026 | 34.4507 | 3.0062 | 33.0917 | 1.0500 | 24 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | False | False | 0.4585 | -0.5415 | 36.2235 | 3.0609 | 31.4722 | 1.0000 | 21 |
| combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000 | False | False | 0.5050 | -0.5450 | 67.6666 | 3.0687 | 16.8478 | 1.0500 | 47 |
| combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | False | False | 0.5500 | -0.5000 | 108.8912 | 3.1277 | 10.5430 | 1.0500 | 70 |
