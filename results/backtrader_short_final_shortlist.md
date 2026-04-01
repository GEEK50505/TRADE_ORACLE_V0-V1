# Short Final Shortlist

This shortlist trims the ranked short survivors down to the most actionable top candidates after removing exact outcome duplicates.

| priority | param_id | source_symbol | total_trades | win_rate | expectancy | max_dd_pct | consistency_score | role |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | short_cand_061_DOGE_USDT | DOGE/USDT | 63 | 0.6508 | 3.3044 | 1.7496 | 5.6043 | primary |
| 2 | short_cand_062_DOGE_USDT | DOGE/USDT | 63 | 0.6349 | 2.8811 | 1.7553 | 6.4276 | secondary |
| 3 | short_cand_070_DOGE_USDT | DOGE/USDT | 74 | 0.6216 | 2.9258 | 1.7551 | 5.3886 | throughput_variant |
| 4 | short_cand_076_ETH_USDT | ETH/USDT | 84 | 0.6310 | 3.0317 | 2.1310 | 4.5812 | alternate_base |
| 5 | short_cand_075_DOGE_USDT | DOGE/USDT | 75 | 0.6267 | 2.9090 | 1.8682 | 5.3474 | reserve |

## Rationale

- **short_cand_061_DOGE_USDT**: Best overall short candidate after deduplication, balancing expectancy, drawdown control, and consistency.
- **short_cand_062_DOGE_USDT**: Closest clean alternate to the primary short candidate with a very similar edge profile.
- **short_cand_070_DOGE_USDT**: Short candidate with especially strong trailing-drawdown control for the short side.
- **short_cand_076_ETH_USDT**: Short candidate with a relatively comfortable consistency profile under Maven rules.
- **short_cand_075_DOGE_USDT**: Short candidate with especially strong trailing-drawdown control for the short side.
