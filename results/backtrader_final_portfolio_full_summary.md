# Backtrader final portfolio full summary

- **raw_data_start**: 2023-04-02 00:00
- **raw_data_end**: 2026-03-31 08:00
- **official_reference_preset**: baseline
- **dynamic_symbol_onboarding**: enabled
- **pair_level_same_symbol_stacking**: enabled
- **protective_exit_rejections**: disabled

## Execution Assumptions

- Exact strategy is the locked 5-pair deployment shortlist from backtrader_combined_final_shortlist.csv.
- Effective portfolio start is the first timestamp where any symbol becomes trade-ready after its own warmup.
- Short-history symbols such as TON/USDT are added dynamically when their own data becomes ready.
- Same-symbol same-side signals from different shortlisted pairs may coexist as independent positions.
- Opposite-side self-hedging on the same symbol is blocked across the shared account.
- Deterministic execution frictions model fees, spread, slippage, latency, rejected entries, and partial fills.
- Protective exits are never rejected; only new entries can be rejected or partially filled.
- Risk sizing uses All-In $10: theoretical worst-case loss including fees, spread, and slippage stays at or below about $10 before leverage truncation.

## Scenario Comparison

| friction_preset | backtest_start | backtest_end | true_months_window | ending_equity | total_profit | max_dd_pct | consistency_score | overall_survival | stacked_same_side_entries | entry_rejections | partial_fill_events | extra_latency_events | total_return_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 2023-06-16 00:00 | 2026-03-31 08:00 | 34 | 4925.5810 | -74.4190 | 3.9271 | 999.0000 | False | 30 | 1 | 2 | 40 | -1.4884 |
| stress | 2023-06-16 00:00 | 2026-03-31 08:00 | 34 | 4845.3365 | -154.6635 | 3.2443 | 999.0000 | False | 11 | 1 | 2 | 7 | -3.0933 |

## Final Pairs Active

| shortlist_priority | param_id | long_param_id | short_param_id | expectancy | composite_score |
| --- | --- | --- | --- | --- | --- |
| 1 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_088_ETH_USDT__4h_ema20_dist0.000 | 2.8093 | 86.3990 |
| 2 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | cand_002_AVAX_USDT__4h_ema15_dist0.000 | short_cand_088_ETH_USDT__4h_ema20_dist0.000 | 2.7101 | 81.7957 |
| 3 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema15_dist0.000 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_088_ETH_USDT__4h_ema15_dist0.000 | 2.7795 | 80.8384 |
| 4 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema15_dist0.000 | cand_002_AVAX_USDT__4h_ema15_dist0.000 | short_cand_088_ETH_USDT__4h_ema15_dist0.000 | 2.6720 | 76.0220 |
| 5 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_076_ETH_USDT__4h_ema15_dist0.000 | 2.7152 | 75.9866 |

## Baseline Vs Stress

Baseline total profit is `-74.42` versus stress `-154.66`. Baseline max drawdown is `3.93%` versus stress `3.24%`.

Baseline is the official deployment-grade reference; stress is the downside robustness check.
