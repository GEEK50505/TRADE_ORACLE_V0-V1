# Backtrader final portfolio full summary

- **friction_preset**: stress
- **raw_data_start**: 2023-04-02 00:00
- **raw_data_end**: 2026-03-31 08:00
- **effective_backtest_start**: 2023-06-16 00:00
- **effective_backtest_end**: 2026-03-31 08:00
- **true_months_traded_window**: 34
- **monthly_return_observations**: 33
- **dynamically_added_symbols**: 1
- **ending_equity**: 4845.34
- **total_profit**: -154.66
- **total_return_pct**: -3.09
- **max_dd_pct**: 3.24
- **consistency_score**: 999.00
- **overall_survival**: False
- **breached**: True
- **same_symbol_stacking_delta_vs_netted_profit**: -509.69
- **friction_delta_vs_frictionless_profit**: -82.40

## Execution Assumptions

- Exact strategy is the locked 5-pair deployment shortlist from backtrader_combined_final_shortlist.csv.
- Effective portfolio start is the first timestamp where any symbol becomes trade-ready after its own warmup.
- Short-history symbols such as TON/USDT are added dynamically when their own data becomes ready.
- Same-symbol same-side signals from different shortlisted pairs may coexist as independent positions.
- Opposite-side self-hedging on the same symbol is blocked across the shared account.
- Deterministic execution frictions model fees, spread, slippage, latency, rejected entries, and partial fills.
- Protective exits are never rejected; only new entries can be rejected or partially filled.
- Risk sizing uses All-In $10: theoretical worst-case loss including fees, spread, and slippage stays at or below about $10 before leverage truncation.

## Portfolio Metrics

| closed_positions | total_fragments | fragment_win_rate | position_win_rate | expectancy_per_fragment | profit_factor | cagr | daily_sharpe | daily_sortino | calmar | max_concurrent_observed | same_symbol_opposite_conflicts | same_pair_duplicate_blocks | stacked_same_side_entries | entry_rejections | partial_fill_events | extra_latency_events |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16 | 16 | 0.0000 | 0.0000 | -9.6665 | 0.0000 | -0.0112 | -1.2155 | -0.1828 | -0.3450 | 4 | 0 | 12 | 11 | 1 | 2 | 7 |

## Dynamic Symbol Activation

| symbol | chosen_exec_mode | daily_start | intraday_start | activation_ts | dynamic_added |
| --- | --- | --- | --- | --- | --- |
| BTC/USDT | 4H->1D | 2023-04-02 00:00:00 | 2023-04-01 08:00:00 | 2023-06-16 00:00:00 | False |
| ETH/USDT | 4H->1D | 2023-04-02 00:00:00 | 2023-04-01 08:00:00 | 2023-06-16 00:00:00 | False |
| SOL/USDT | 4H->1D | 2023-04-02 00:00:00 | 2023-04-01 08:00:00 | 2023-06-16 00:00:00 | False |
| XRP/USDT | 1D | 2023-04-02 00:00:00 | NaT | 2023-06-16 00:00:00 | False |
| DOGE/USDT | 1D | 2023-04-02 00:00:00 | NaT | 2023-06-16 00:00:00 | False |
| AVAX/USDT | 1D | 2023-04-02 00:00:00 | NaT | 2023-06-16 00:00:00 | False |
| LINK/USDT | 4H->1D | 2023-04-02 00:00:00 | 2023-04-01 08:00:00 | 2023-06-16 00:00:00 | False |
| TON/USDT | 1D | 2024-08-08 00:00:00 | NaT | 2024-10-22 00:00:00 | True |
| ADA/USDT | 1D | 2023-04-02 00:00:00 | NaT | 2023-06-16 00:00:00 | False |
| BNB/USDT | 1D | 2023-04-02 00:00:00 | NaT | 2023-06-16 00:00:00 | False |

## Pair Contribution

| source_pair_id | positions | winning_positions | total_profit | avg_position_pnl | avg_support_pair_count | position_win_rate | shortlist_priority | shortlist_role | long_param_id | short_param_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema15_dist0.000 | 4 | 0 | -35.6952 | -8.9238 | 1.0000 | 0.0000 | 4 | pair_diversifier | cand_002_AVAX_USDT__4h_ema15_dist0.000 | short_cand_088_ETH_USDT__4h_ema15_dist0.000 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | 4 | 0 | -36.7804 | -9.1951 | 1.0000 | 0.0000 | 2 | secondary | cand_002_AVAX_USDT__4h_ema15_dist0.000 | short_cand_088_ETH_USDT__4h_ema20_dist0.000 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema15_dist0.000 | 4 | 0 | -41.0351 | -10.2588 | 1.0000 | 0.0000 | 3 | throughput_variant | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_088_ETH_USDT__4h_ema15_dist0.000 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | 4 | 0 | -41.1529 | -10.2882 | 1.0000 | 0.0000 | 1 | primary | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_088_ETH_USDT__4h_ema20_dist0.000 |

## Symbol Contribution

| symbol | positions | winning_positions | total_profit | avg_position_pnl | position_win_rate |
| --- | --- | --- | --- | --- | --- |
| LINK/USDT | 2 | 0 | -20.0000 | -10.0000 | 0.0000 |
| AVAX/USDT | 6 | 0 | -54.5423 | -9.0904 | 0.0000 |
| DOGE/USDT | 8 | 0 | -80.1213 | -10.0152 | 0.0000 |

## Monthly Returns

| month | monthly_return_pct | month_end_equity |
| --- | --- | --- |
| 2024-10 | 0.0000 | 4845.3365 |
| 2024-11 | 0.0000 | 4845.3365 |
| 2024-12 | 0.0000 | 4845.3365 |
| 2025-01 | 0.0000 | 4845.3365 |
| 2025-02 | 0.0000 | 4845.3365 |
| 2025-03 | 0.0000 | 4845.3365 |
| 2025-04 | 0.0000 | 4845.3365 |
| 2025-05 | 0.0000 | 4845.3365 |
| 2025-06 | 0.0000 | 4845.3365 |
| 2025-07 | 0.0000 | 4845.3365 |
| 2025-08 | 0.0000 | 4845.3365 |
| 2025-09 | 0.0000 | 4845.3365 |
| 2025-10 | 0.0000 | 4845.3365 |
| 2025-11 | 0.0000 | 4845.3365 |
| 2025-12 | 0.0000 | 4845.3365 |
| 2026-01 | 0.0000 | 4845.3365 |
| 2026-02 | 0.0000 | 4845.3365 |
| 2026-03 | 0.0000 | 4845.3365 |

## Prior Netted Comparison

| prior_netted_total_profit | current_total_profit | stacking_profit_delta |
| --- | --- | --- |
| 355.0238 | -154.6635 | -509.6873 |

## Frictionless Reference Comparison

| frictionless_reference_profit | current_profit | friction_delta |
| --- | --- | --- |
| -72.2650 | -154.6635 | -82.3985 |
