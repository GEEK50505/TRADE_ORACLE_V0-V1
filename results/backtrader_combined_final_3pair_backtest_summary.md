# Backtrader final 3-pair clean backtest summary

- **objective**: rerun the fixed 3-pair realistic survivor shortlist through the full corrected baseline engine
- **selected_portfolio**: combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004
- **ruleset**: full 34-month window, realistic symbol onboarding, pair-level stacking, baseline friction, All-In $10 risk

## Portfolio Comparison

| portfolio_label | portfolio_param_ids | expectancy | penalized_expectancy | total_profit | max_dd_pct | consistency_score | overall_survival | stacked_same_side_entries | diversity_penalty | stacking_profit_delta_vs_netted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| old_5pair_shortlist | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema15_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema15_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | -1.0944 | -2.9444 | -74.4190 | 3.9271 | 999.0000 | False | 30 | 1.8500 | -429.4428 |
| new_realistic_5pair_shortlist | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_082_ETH_USDT__4h_ema20_dist0.000|combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 1.8921 | 0.7921 | 143.8024 | 3.0446 | 7.9278 | False | 24 | 1.1000 | -211.2214 |
| best_4pair_near_miss | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 0.4623 | -0.4377 | 64.7243 | 3.0002 | 17.6137 | False | 44 | 0.9000 | -290.2995 |
| final_3pair_survivor | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 1.0542 | 0.1542 | 295.1776 | 2.9641 | 3.8893 | True | 86 | 0.9000 | -59.8462 |

## Final 3-Pair Result

| portfolio_label | portfolio_param_ids | expectancy | penalized_expectancy | total_profit | max_dd_pct | consistency_score | overall_survival | stacked_same_side_entries | diversity_penalty | stacking_profit_delta_vs_netted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| final_3pair_survivor | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004|combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 1.0542 | 0.1542 | 295.1776 | 2.9641 | 3.8893 | True | 86 | 0.9000 | -59.8462 |

## Final Survivor Shortlist

| shortlist_priority | param_id | long_param_id | short_param_id | expectancy | max_dd_pct | consistency_score | overall_survival | portfolio_expectancy | portfolio_max_dd_pct | portfolio_consistency_score | portfolio_overall_survival |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 1.1962 | 1.7764 | 4.8423 | True | 1.0542 | 2.9641 | 3.8893 | True |
| 2 | combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | cand_008_AVAX_USDT__4h_ema15_dist0.008 | short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 1.0027 | 2.0279 | 5.7768 | True | 1.0542 | 2.9641 | 3.8893 | True |
| 3 | combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | cand_002_AVAX_USDT__4h_ema20_dist0.008 | short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | 0.8859 | 2.1053 | 6.6118 | True | 1.0542 | 2.9641 | 3.8893 | True |
