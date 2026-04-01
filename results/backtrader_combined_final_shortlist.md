# Combined Final Shortlist

This shortlist trims the ranked combined survivors down to the most actionable pair portfolios after removing exact outcome duplicates.

| priority | long_param_id | short_param_id | total_trades | win_rate | expectancy | max_dd_pct | consistency_score | role |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_088_ETH_USDT__4h_ema20_dist0.000 | 124 | 0.6290 | 2.8093 | 1.7909 | 3.3491 | primary |
| 2 | cand_002_AVAX_USDT__4h_ema15_dist0.000 | short_cand_088_ETH_USDT__4h_ema20_dist0.000 | 131 | 0.6260 | 2.7101 | 1.7886 | 3.2862 | secondary |
| 3 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_088_ETH_USDT__4h_ema15_dist0.000 | 112 | 0.6250 | 2.7795 | 1.7757 | 3.7476 | throughput_variant |
| 4 | cand_002_AVAX_USDT__4h_ema15_dist0.000 | short_cand_088_ETH_USDT__4h_ema15_dist0.000 | 119 | 0.6218 | 2.6720 | 1.7735 | 3.6691 | pair_diversifier |
| 5 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_076_ETH_USDT__4h_ema15_dist0.000 | 104 | 0.6250 | 2.7152 | 1.7768 | 4.1316 | reserve |

## Rationale

- **cand_002_AVAX_USDT__4h_ema15_dist0.008 + short_cand_088_ETH_USDT__4h_ema20_dist0.000**: Best overall combined pair after deduplication, balancing expectancy, drawdown control, and consistency.
- **cand_002_AVAX_USDT__4h_ema15_dist0.000 + short_cand_088_ETH_USDT__4h_ema20_dist0.000**: Closest clean alternate to the primary pair with a very similar edge profile.
- **cand_002_AVAX_USDT__4h_ema15_dist0.008 + short_cand_088_ETH_USDT__4h_ema15_dist0.000**: Combined pair with especially strong trailing-drawdown control under shared portfolio rules.
- **cand_002_AVAX_USDT__4h_ema15_dist0.000 + short_cand_088_ETH_USDT__4h_ema15_dist0.000**: Combined pair with especially strong trailing-drawdown control under shared portfolio rules.
- **cand_002_AVAX_USDT__4h_ema15_dist0.008 + short_cand_076_ETH_USDT__4h_ema15_dist0.000**: Combined pair with especially strong trailing-drawdown control under shared portfolio rules.
