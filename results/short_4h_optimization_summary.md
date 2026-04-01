# Short Daily + 4H confirmation sweep summary

- **base_short_survivors_used**: 20
- **confirm_ema_periods**: [15, 20, 25, 30]
- **confirm_min_distances**: [0.0, 0.004, 0.008]
- **full_combined_rows**: 240
- **backtrader_candidate_rows**: 240
- **best_expectancy**: 329.9184
- **best_win_rate**: 0.3864
- **best_total_trades**: 132

## Method Notes

- The Daily short layer is unchanged from the validated short discovery phase.
- The 4H layer is confirmation-only: execution close must be below the 4H EMA and far enough below it to clear the minimum distance threshold.
- No fresh full-grid search was performed; this pass only combines the strongest short survivors with a compact 4H confirmation grid.

## Top 10 Combined Short Candidates

| param_id | source_symbol | confirm_ema_period | confirm_min_distance | total_trades | win_rate | expectancy | total_return |
| --- | --- | --- | --- | --- | --- | --- | --- |
| short_cand_068_DOGE_USDT__4h_ema15_dist0.000 | DOGE/USDT | 15 | 0.0 | 44 | 0.38636363636363635 | 329.91840440874915 | 1.4516409793984963 |
| short_cand_068_DOGE_USDT__4h_ema20_dist0.000 | DOGE/USDT | 20 | 0.0 | 47 | 0.3617021276595745 | 303.97450783933095 | 1.4286801868448553 |
| short_cand_068_DOGE_USDT__4h_ema15_dist0.004 | DOGE/USDT | 15 | 0.004 | 34 | 0.35294117647058826 | 278.21299926335837 | 0.9459241974954185 |
| short_cand_068_DOGE_USDT__4h_ema15_dist0.008 | DOGE/USDT | 15 | 0.008 | 23 | 0.30434782608695654 | 241.57256840376493 | 0.5556169073286593 |
| short_cand_062_DOGE_USDT__4h_ema20_dist0.000 | DOGE/USDT | 20 | 0.0 | 71 | 0.3380281690140845 | 220.30416409295518 | 1.5641595650599818 |
| short_cand_071_DOGE_USDT__4h_ema15_dist0.008 | DOGE/USDT | 15 | 0.008 | 73 | 0.3424657534246575 | 217.78407726617914 | 1.5898237640431079 |
| short_cand_079_ETH_USDT__4h_ema15_dist0.000 | ETH/USDT | 15 | 0.0 | 64 | 0.3125 | 212.91480157909464 | 1.3626547301062057 |
| short_cand_067_DOGE_USDT__4h_ema20_dist0.000 | DOGE/USDT | 20 | 0.0 | 74 | 0.33783783783783783 | 210.232252247272 | 1.5557186666298126 |
| short_cand_071_DOGE_USDT__4h_ema20_dist0.004 | DOGE/USDT | 20 | 0.004 | 92 | 0.31521739130434784 | 204.33662088134363 | 1.8798969121083613 |
| short_cand_061_DOGE_USDT__4h_ema20_dist0.000 | DOGE/USDT | 20 | 0.0 | 73 | 0.3287671232876712 | 203.78880407688715 | 1.4876582697612761 |
