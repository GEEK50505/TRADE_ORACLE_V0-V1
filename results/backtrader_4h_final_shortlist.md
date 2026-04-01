# 4H Final Shortlist

This shortlist trims the 41 combined survivors down to the most actionable 5 long-side candidates.

| priority | param_id | source_symbol | confirm_ema_period | confirm_min_distance | total_trades | win_rate | expectancy | max_dd_pct | consistency_score | role |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | AVAX/USDT | 15 | 0.008 | 68 | 0.6029 | 2.1078 | 1.7255 | 8.1395 | primary |
| 2 | cand_002_AVAX_USDT__4h_ema20_dist0.008 | AVAX/USDT | 20 | 0.008 | 72 | 0.5972 | 1.9676 | 1.7280 | 8.2353 | secondary |
| 3 | cand_002_AVAX_USDT__4h_ema15_dist0.000 | AVAX/USDT | 15 | 0.000 | 76 | 0.5921 | 1.8421 | 1.8051 | 8.3333 | throughput_variant |
| 4 | cand_008_AVAX_USDT__4h_ema15_dist0.008 | AVAX/USDT | 15 | 0.008 | 73 | 0.5890 | 1.8037 | 1.7813 | 8.8608 | alternate_base |
| 5 | cand_028_ETH_USDT__4h_ema15_dist0.000 | ETH/USDT | 15 | 0.000 | 68 | 0.5294 | 1.5735 | 2.0654 | 10.9036 | diversifier |

## Rationale

- **cand_002_AVAX_USDT__4h_ema15_dist0.008**: Best overall balance: strongest expectancy, tightest drawdown, best consistency, and still healthy trade count.
- **cand_002_AVAX_USDT__4h_ema20_dist0.008**: Very close to the leader with slightly more trades and nearly identical risk profile.
- **cand_002_AVAX_USDT__4h_ema15_dist0.000**: Keeps the same strong AVAX base while allowing more trades at only a modest quality drop.
- **cand_008_AVAX_USDT__4h_ema15_dist0.008**: Best non-cand_002 AVAX branch, useful as an alternate daily base rather than another threshold clone.
- **cand_028_ETH_USDT__4h_ema15_dist0.000**: Best ETH-based survivor and the cleanest way to keep some source-family diversification in the final set.
