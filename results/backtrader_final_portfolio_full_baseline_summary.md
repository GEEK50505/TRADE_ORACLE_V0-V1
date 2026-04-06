# Backtrader final portfolio full summary

- **friction_preset**: baseline
- **raw_data_start**: 2023-04-02 00:00
- **raw_data_end**: 2026-03-31 08:00
- **effective_backtest_start**: 2023-06-16 00:00
- **effective_backtest_end**: 2026-03-31 08:00
- **true_months_traded_window**: 34
- **monthly_return_observations**: 33
- **dynamically_added_symbols**: 1
- **ending_equity**: 4925.58
- **total_profit**: -74.42
- **total_return_pct**: -1.49
- **max_dd_pct**: 3.93
- **consistency_score**: 999.00
- **overall_survival**: False
- **breached**: True
- **same_symbol_stacking_delta_vs_netted_profit**: -429.44
- **friction_delta_vs_frictionless_profit**: -2.15

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
| 48 | 68 | 0.4265 | 0.4167 | -1.0944 | 0.7526 | -0.0054 | -0.3037 | -0.1547 | -0.1364 | 4 | 10 | 107 | 30 | 1 | 2 | 40 |

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
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | 17 | 8 | -9.6971 | -0.5704 | 1.0000 | 0.4706 | 1 | primary | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_088_ETH_USDT__4h_ema20_dist0.000 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema15_dist0.000 | 8 | 3 | -14.3713 | -1.7964 | 1.0000 | 0.3750 | 4 | pair_diversifier | cand_002_AVAX_USDT__4h_ema15_dist0.000 | short_cand_088_ETH_USDT__4h_ema15_dist0.000 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | 12 | 5 | -22.3718 | -1.8643 | 1.0000 | 0.4167 | 2 | secondary | cand_002_AVAX_USDT__4h_ema15_dist0.000 | short_cand_088_ETH_USDT__4h_ema20_dist0.000 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema15_dist0.000 | 11 | 4 | -27.9788 | -2.5435 | 1.0000 | 0.3636 | 3 | throughput_variant | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_088_ETH_USDT__4h_ema15_dist0.000 |

## Symbol Contribution

| symbol | positions | winning_positions | total_profit | avg_position_pnl | position_win_rate |
| --- | --- | --- | --- | --- | --- |
| BNB/USDT | 6 | 6 | 81.6892 | 13.6149 | 1.0000 |
| AVAX/USDT | 11 | 6 | 35.3074 | 3.2098 | 0.5455 |
| ETH/USDT | 3 | 1 | -2.5619 | -0.8540 | 0.3333 |
| ADA/USDT | 1 | 0 | -10.0000 | -10.0000 | 0.0000 |
| LINK/USDT | 8 | 4 | -14.4275 | -1.8034 | 0.5000 |
| BTC/USDT | 2 | 0 | -20.0000 | -10.0000 | 0.0000 |
| XRP/USDT | 5 | 1 | -57.5691 | -11.5138 | 0.2000 |
| DOGE/USDT | 12 | 2 | -86.8571 | -7.2381 | 0.1667 |

## Monthly Returns

| month | monthly_return_pct | month_end_equity |
| --- | --- | --- |
| 2024-10 | 0.0000 | 4925.5810 |
| 2024-11 | 0.0000 | 4925.5810 |
| 2024-12 | 0.0000 | 4925.5810 |
| 2025-01 | 0.0000 | 4925.5810 |
| 2025-02 | 0.0000 | 4925.5810 |
| 2025-03 | 0.0000 | 4925.5810 |
| 2025-04 | 0.0000 | 4925.5810 |
| 2025-05 | 0.0000 | 4925.5810 |
| 2025-06 | 0.0000 | 4925.5810 |
| 2025-07 | 0.0000 | 4925.5810 |
| 2025-08 | 0.0000 | 4925.5810 |
| 2025-09 | 0.0000 | 4925.5810 |
| 2025-10 | 0.0000 | 4925.5810 |
| 2025-11 | 0.0000 | 4925.5810 |
| 2025-12 | 0.0000 | 4925.5810 |
| 2026-01 | 0.0000 | 4925.5810 |
| 2026-02 | 0.0000 | 4925.5810 |
| 2026-03 | 0.0000 | 4925.5810 |

## Prior Netted Comparison

| prior_netted_total_profit | current_total_profit | stacking_profit_delta |
| --- | --- | --- |
| 355.0238 | -74.4190 | -429.4428 |

## Frictionless Reference Comparison

| frictionless_reference_profit | current_profit | friction_delta |
| --- | --- | --- |
| -72.2650 | -74.4190 | -2.1540 |
