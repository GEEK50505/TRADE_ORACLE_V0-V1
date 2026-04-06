# Backtrader realistic shortlist re-optimization summary

- **objective**: maximize expectancy under the corrected 34-month realistic baseline portfolio engine
- **baseline_friction_preset**: baseline
- **candidate_pairs_in_pool**: 1
- **standalone_realistic_survivors**: 0
- **unique_portfolios_evaluated**: 1
- **target_shortlist_size**: 1
- **search_method**: deterministic forward selection plus bounded swap refinement
- **note**: the portfolio objective includes a small diversity penalty to avoid near-clone concentration.
- **swap_rounds**: 0

## Portfolio Comparison

| portfolio_label | portfolio_param_ids | expectancy | penalized_expectancy | total_profit | max_dd_pct | consistency_score | overall_survival | stacked_same_side_entries | diversity_penalty | stacking_profit_delta_vs_netted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| old_shortlist | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | -1.0455 | -1.0455 | -95.1400 | 3.0264 | 999.0000 | False | 0 | 0.0000 | -450.1638 |
| new_shortlist | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | -1.0455 | -1.0455 | -95.1400 | 3.0264 | 999.0000 | False | 0 | 0.0000 | -450.1638 |

## New Final Shortlist

| shortlist_priority | param_id | long_param_id | short_param_id | expectancy | max_dd_pct | overall_survival | portfolio_penalized_expectancy | portfolio_diversity_penalty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_088_ETH_USDT__4h_ema20_dist0.000 | -1.0455 | 3.0264 | False | -1.0455 | 0.0000 |

## Old vs New Pair Table

| portfolio_label | shortlist_priority | param_id | standalone_expectancy | standalone_max_dd_pct | standalone_overall_survival | realized_pair_total_profit | stacking_impact_proxy_avg_support_pair_count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| new_shortlist | 1 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | -1.0455 | 3.0264 | False | -95.1400 | 1.0000 |
| old_shortlist | 1 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | -1.0455 | 3.0264 | False | -95.1400 | 1.0000 |

## Top Evaluated Target-Size Portfolios

| portfolio_param_ids | overall_survival | penalized_expectancy | expectancy | max_dd_pct | consistency_score | diversity_penalty | stacked_same_side_entries | first_seen_stage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | False | -1.0455 | -1.0455 | 3.0264 | 999.0000 | 0.0000 | 0 | standalone |

## Membership Change

- **kept_pairs**: combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000
- **added_pairs**: none
- **removed_pairs**: none
