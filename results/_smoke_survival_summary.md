# Backtrader survival-first search summary

- **selected_result_label**: survival_search_near_miss
- **survivor_found**: False
- **selected_portfolio**: combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000
- **unique_portfolios_evaluated**: 4
- **searched_survivors_found**: 0

## Search Config

| setting | value |
| --- | --- |
| search_sizes | 4 |
| seed_limit_per_size | 1 |
| ordering_beam_width | 1 |
| replacement_pool_size | 1 |
| two_swap_source_limit | 0 |
| two_swap_replacement_pool_size | 3 |
| continue_after_survivor | False |
| max_orderings_per_seed | 2 |
| max_one_swap_trials_per_source | 2 |
| max_two_swap_trials_per_source | None |

## Portfolio Comparison

| portfolio_label | portfolio_param_ids | expectancy | penalized_expectancy | total_profit | max_dd_pct | consistency_score | overall_survival | stacked_same_side_entries | diversity_penalty | stacking_profit_delta_vs_netted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| old_shortlist | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema15_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema15_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | -1.0944 | -2.9444 | -74.4190 | 3.9271 | 999.0000 | False | 30 | 1.8500 | -429.4428 |
| new_realistic_shortlist | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 1.8921 | 0.7921 | 143.8024 | 3.0446 | 7.9278 | False | 24 | 1.1000 | -211.2214 |
| survival_search_near_miss | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000 | 1.3031 | 0.6531 | 102.9484 | 3.0133 | 11.0738 | False | 26 | 0.6500 | -252.0754 |

## Selected Result

| portfolio_label | portfolio_param_ids | expectancy | penalized_expectancy | total_profit | max_dd_pct | consistency_score | overall_survival | stacked_same_side_entries | diversity_penalty | stacking_profit_delta_vs_netted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| survival_search_near_miss | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000 | 1.3031 | 0.6531 | 102.9484 | 3.0133 | 11.0738 | False | 26 | 0.6500 | -252.0754 |

## Selected Shortlist

| shortlist_priority | param_id | long_param_id | short_param_id | expectancy | max_dd_pct | overall_survival | portfolio_penalized_expectancy | portfolio_diversity_penalty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 1.1962 | 1.7764 | True | 0.6531 | 0.6500 |
| 2 | combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | cand_028_ETH_USDT__4h_ema15_dist0.000 | short_cand_076_ETH_USDT__4h_ema15_dist0.000 | -0.2785 | 3.1464 | False | 0.6531 | 0.6500 |
| 3 | combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | cand_002_AVAX_USDT__4h_ema20_dist0.008 | short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 0.8859 | 2.1053 | True | 0.6531 | 0.6500 |
| 4 | combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000 | cand_008_AVAX_USDT__4h_ema15_dist0.008 | short_cand_082_ETH_USDT__4h_ema20_dist0.000 | -0.8534 | 3.4691 | False | 0.6531 | 0.6500 |

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
| survival_search_near_miss | 1 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 1.1962 | 1.7764 | True | 31.6872 | 1.0000 |
| survival_search_near_miss | 2 | combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | -0.2785 | 3.1464 | False | 58.6363 | 1.0000 |
| survival_search_near_miss | 3 | combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 0.8859 | 2.1053 | True | -50.0379 | 1.0000 |
| survival_search_near_miss | 4 | combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000 | -0.8534 | 3.4691 | False | 62.6629 | 1.0000 |

## Top Search Results

| portfolio_param_ids | portfolio_size | overall_survival | penalized_expectancy | expectancy | max_dd_pct | consistency_score | diversity_penalty | first_seen_stage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 4 | False | 0.6531 | 1.3031 | 3.0133 | 11.0738 | 0.6500 | size_4_seed_01_ordering |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000 | 4 | False | 0.6531 | 1.3031 | 3.0133 | 11.0738 | 0.6500 | size_4_seed_01_ordering |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 4 | False | -0.1207 | 0.8793 | 3.0892 | 16.8370 | 1.0000 | size_4_seed_01_ordering_01_one_swap |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 4 | False | 0.7606 | 1.4106 | 3.3404 | 10.5517 | 0.6500 | size_4_seed_01_ordering_01_one_swap |
