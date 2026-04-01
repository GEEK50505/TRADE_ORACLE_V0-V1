# Backtrader combined validation summary

- **source_candidates_file**: results/backtrader_combined_smoke_candidates.csv
- **pair_portfolios_evaluated**: 2
- **survivors**: 2
- **breached_accounts**: 0
- **median_max_dd_pct**: 2.05
- **median_consistency_score**: 5.60
- **best_expectancy**: 2.10
- **best_total_return_pct**: 4.45
- **median_signal_conflicts**: 0.00

## Data Coverage Notes

- **4H execution + Daily signals available**: 4 symbols
- **Daily fallback symbols**: 6 symbols
- Mixed-timeframe validation is therefore partially intraday-aware, not fully intraday for the whole watchlist.

## Top 10 Surviving Pair Portfolios

| rank | long_param_id | short_param_id | total_trades | win_rate | expectancy | max_dd_pct | consistency_score | signal_conflicts | overall_survival |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_061_DOGE_USDT | 106 | 0.5943396226415094 | 2.0980780102858336 | 1.9763918289889482 | 5.245891360672836 | 0 | True |
| 2 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | short_cand_062_DOGE_USDT | 106 | 0.5849056603773585 | 1.846505683241808 | 2.1327660530992314 | 5.960604079405254 | 0 | True |
