# Short Final Shortlist

This shortlist trims the ranked short survivors down to the most actionable top candidates after removing exact outcome duplicates.

| priority | param_id | source_symbol | total_trades | win_rate | expectancy | max_dd_pct | consistency_score | role |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | short_cand_088_ETH_USDT__4h_ema20_dist0.000 | ETH/USDT | 87 | 0.6322 | 2.9313 | 1.8261 | 4.5747 | primary |
| 2 | short_cand_082_ETH_USDT__4h_ema20_dist0.000 | ETH/USDT | 71 | 0.6338 | 2.8008 | 1.6886 | 5.8669 | secondary |
| 3 | short_cand_088_ETH_USDT__4h_ema15_dist0.000 | ETH/USDT | 75 | 0.6267 | 2.9063 | 1.7696 | 5.3523 | throughput_variant |
| 4 | short_cand_076_ETH_USDT__4h_ema15_dist0.000 | ETH/USDT | 67 | 0.6269 | 2.8216 | 1.6805 | 6.1713 | alternate_base |
| 5 | short_cand_067_DOGE_USDT__4h_ema20_dist0.004 | DOGE/USDT | 54 | 0.6296 | 2.8998 | 1.7542 | 7.4506 | reserve |

## Rationale

- **short_cand_088_ETH_USDT__4h_ema20_dist0.000**: Best overall short candidate after deduplication, balancing expectancy, drawdown control, and consistency.
- **short_cand_082_ETH_USDT__4h_ema20_dist0.000**: Closest clean alternate to the primary short candidate with a very similar edge profile.
- **short_cand_088_ETH_USDT__4h_ema15_dist0.000**: Short candidate with especially strong trailing-drawdown control for the short side.
- **short_cand_076_ETH_USDT__4h_ema15_dist0.000**: Short candidate with especially strong trailing-drawdown control for the short side.
- **short_cand_067_DOGE_USDT__4h_ema20_dist0.004**: Short candidate with especially strong trailing-drawdown control for the short side.
