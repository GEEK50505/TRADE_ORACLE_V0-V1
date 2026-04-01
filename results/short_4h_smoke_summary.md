# Short Daily + 4H confirmation sweep summary

- **base_short_survivors_used**: 2
- **confirm_ema_periods**: [15, 20, 25, 30]
- **confirm_min_distances**: [0.0, 0.004, 0.008]
- **full_combined_rows**: 24
- **backtrader_candidate_rows**: 6
- **best_expectancy**: 220.3042
- **best_win_rate**: 0.3380
- **best_total_trades**: 75

## Method Notes

- The Daily short layer is unchanged from the validated short discovery phase.
- The 4H layer is confirmation-only: execution close must be below the 4H EMA and far enough below it to clear the minimum distance threshold.
- No fresh full-grid search was performed; this pass only combines the strongest short survivors with a compact 4H confirmation grid.

## Top 10 Combined Short Candidates

| param_id | source_symbol | confirm_ema_period | confirm_min_distance | total_trades | win_rate | expectancy | total_return |
| --- | --- | --- | --- | --- | --- | --- | --- |
| short_cand_062_DOGE_USDT__4h_ema20_dist0.000 | DOGE/USDT | 20 | 0.0 | 71 | 0.3380281690140845 | 220.30416409295518 | 1.5641595650599818 |
| short_cand_061_DOGE_USDT__4h_ema20_dist0.000 | DOGE/USDT | 20 | 0.0 | 73 | 0.3287671232876712 | 203.78880407688715 | 1.4876582697612761 |
| short_cand_062_DOGE_USDT__4h_ema15_dist0.000 | DOGE/USDT | 15 | 0.0 | 72 | 0.3194444444444444 | 188.26182507163168 | 1.355485140515748 |
| short_cand_061_DOGE_USDT__4h_ema15_dist0.000 | DOGE/USDT | 15 | 0.0 | 75 | 0.32 | 171.04715451540088 | 1.2828536588655066 |
| short_cand_062_DOGE_USDT__4h_ema30_dist0.004 | DOGE/USDT | 30 | 0.004 | 70 | 0.3142857142857143 | 139.34372148204892 | 0.9754060503743425 |
| short_cand_062_DOGE_USDT__4h_ema25_dist0.004 | DOGE/USDT | 25 | 0.004 | 70 | 0.3142857142857143 | 133.72097878204596 | 0.9360468514743218 |
| short_cand_062_DOGE_USDT__4h_ema20_dist0.004 | DOGE/USDT | 20 | 0.004 | 70 | 0.3142857142857143 | 132.87360076222816 | 0.9301152053355971 |
| short_cand_062_DOGE_USDT__4h_ema25_dist0.000 | DOGE/USDT | 25 | 0.0 | 71 | 0.30985915492957744 | 130.51845342171453 | 0.9266810192941731 |
| short_cand_062_DOGE_USDT__4h_ema15_dist0.004 | DOGE/USDT | 15 | 0.004 | 66 | 0.30303030303030304 | 128.11433261017513 | 0.8455545952271559 |
| short_cand_062_DOGE_USDT__4h_ema30_dist0.000 | DOGE/USDT | 30 | 0.0 | 73 | 0.3150684931506849 | 127.57467538157616 | 0.9312951302855059 |
