# Backtrader final portfolio summary

- **raw_data_start**: 2023-04-02 00:00
- **raw_data_end**: 2026-03-31 08:00
- **effective_backtest_start**: 2024-10-21 00:00
- **effective_backtest_end**: 2026-03-31 08:00
- **final_pairs_active**: 5
- **watchlist_size**: 10
- **4H execution + Daily signals available**: 4 symbols
- **Daily fallback symbols**: 6 symbols
- **ending_equity**: 5355.02
- **total_profit**: 355.02
- **total_return_pct**: 7.10
- **max_dd_pct**: 1.78
- **consistency_score**: 3.29
- **overall_survival**: True
- **breached**: False

## Execution Assumptions

- The exact final strategy is modeled as the 5 shortlisted combined pairs traded together inside one shared Maven account.
- Only one net position is allowed per symbol at a time.
- If multiple same-side pairs trigger on the same symbol and bar, they collapse into one live-style trade anchored to the highest-priority shortlisted pair.
- If long and short pairs disagree on the same symbol and bar, the trade is skipped rather than resolved heuristically.
- Risk sizing, 4-trade cap, floating-aware 3% trailing drawdown, leverage cap, and fractional scale-outs follow the existing Maven Backtrader engine exactly.
- Because the portfolio uses the full shared watchlist, the effective simulation starts when the latest-starting symbol plus indicator warmup becomes tradable. In the current dataset that pushes the effective start to 2024-10-21.

## Portfolio Metrics

| closed_positions | total_fragments | fragment_win_rate | position_win_rate | expectancy_per_fragment | profit_factor | cagr | daily_sharpe | daily_sortino | calmar | max_concurrent_observed | signal_conflicts | internal_pair_conflicts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 84 | 131 | 0.6260 | 0.5833 | 2.7101 | 2.0144 | 0.0488 | 2.0886 | 2.6602 | 2.7429 | 4 | 0 | 0 |

## Long vs Short Contribution

| side | fragments | positions | total_profit |
| --- | --- | --- | --- |
| long | 48 | 33 | 60.0000 |
| short | 83 | 51 | 295.0238 |

## Final Pairs Traded

| shortlist_priority | param_id | long_param_id | short_param_id | expectancy | composite_score |
| --- | --- | --- | --- | --- | --- |
| 1 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_088_ETH_USDT__4h_ema20_dist0.000 | 2.8093 | 86.3990 |
| 2 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | cand_002_AVAX_USDT__4h_ema15_dist0.000 | short_cand_088_ETH_USDT__4h_ema20_dist0.000 | 2.7101 | 81.7957 |
| 3 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema15_dist0.000 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_088_ETH_USDT__4h_ema15_dist0.000 | 2.7795 | 80.8384 |
| 4 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema15_dist0.000 | cand_002_AVAX_USDT__4h_ema15_dist0.000 | short_cand_088_ETH_USDT__4h_ema15_dist0.000 | 2.6720 | 76.0220 |
| 5 | combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_076_ETH_USDT__4h_ema15_dist0.000 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_076_ETH_USDT__4h_ema15_dist0.000 | 2.7152 | 75.9866 |

## Realized Pair Contribution

| source_pair_id | positions | winning_positions | total_profit | avg_position_pnl | avg_support_pair_count | position_win_rate | shortlist_priority | shortlist_role | long_param_id | short_param_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | 76 | 46 | 350.0238 | 4.6056 | 4.5263 | 0.6053 | 1 | primary | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_088_ETH_USDT__4h_ema20_dist0.000 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_088_ETH_USDT__4h_ema15_dist0.000 | 2 | 1 | 8.3333 | 4.1667 | 2.5000 | 0.5000 | 3 | throughput_variant | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_088_ETH_USDT__4h_ema15_dist0.000 |
| combined__cand_002_AVAX_USDT__4h_ema15_dist0.000__short_cand_088_ETH_USDT__4h_ema20_dist0.000 | 6 | 2 | -3.3333 | -0.5556 | 2.0000 | 0.3333 | 2 | secondary | cand_002_AVAX_USDT__4h_ema15_dist0.000 | short_cand_088_ETH_USDT__4h_ema20_dist0.000 |

## Realized Symbol Contribution

| symbol | positions | winning_positions | total_profit | avg_position_pnl | position_win_rate |
| --- | --- | --- | --- | --- | --- |
| XRP/USDT | 12 | 9 | 88.3333 | 7.3611 | 0.7500 |
| BTC/USDT | 12 | 8 | 83.3333 | 6.9444 | 0.6667 |
| AVAX/USDT | 8 | 7 | 76.7752 | 9.5969 | 0.8750 |
| TON/USDT | 9 | 6 | 48.3981 | 5.3776 | 0.6667 |
| DOGE/USDT | 5 | 3 | 35.0000 | 7.0000 | 0.6000 |
| ETH/USDT | 10 | 5 | 30.0000 | 3.0000 | 0.5000 |
| ADA/USDT | 6 | 3 | 19.5453 | 3.2576 | 0.5000 |
| SOL/USDT | 4 | 2 | 16.6667 | 4.1667 | 0.5000 |
| BNB/USDT | 11 | 5 | -1.3615 | -0.1238 | 0.4545 |
| LINK/USDT | 7 | 1 | -41.6667 | -5.9524 | 0.1429 |

## Monthly Return Snapshot

| month | monthly_return_pct | month_end_equity |
| --- | --- | --- |
| 2025-04 | 0.6555 | 5134.5355 |
| 2025-05 | 0.1344 | 5141.4382 |
| 2025-06 | -0.2191 | 5130.1756 |
| 2025-07 | 0.6831 | 5165.2194 |
| 2025-08 | 0.5766 | 5195.0000 |
| 2025-09 | 0.4653 | 5219.1718 |
| 2025-10 | 0.0794 | 5223.3182 |
| 2025-11 | 1.5170 | 5302.5562 |
| 2025-12 | 0.5417 | 5331.2820 |
| 2026-01 | 0.1948 | 5341.6667 |
| 2026-02 | 0.0392 | 5343.7596 |
| 2026-03 | 0.2108 | 5355.0238 |
