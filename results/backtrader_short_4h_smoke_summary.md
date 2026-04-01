# Backtrader short + 4H validation summary

- **source_candidates_file**: results\short_plus_4h_smoke_candidates.csv
- **candidates_evaluated**: 2
- **survivors**: 2
- **breached_accounts**: 0
- **median_max_dd_pct**: 1.76
- **median_consistency_score**: 10.17
- **best_expectancy**: 2.40
- **best_total_return_pct**: 2.40
- **strategy_side**: short-only
- **confirmation_filter**: enabled for this candidate set

## Data Coverage Notes

- **4H execution + Daily signals available**: 4 symbols
- **Daily fallback symbols**: 6 symbols
- Mixed-timeframe validation is therefore partially intraday-aware, not fully intraday for the whole watchlist.

## Top 10 Surviving Candidates

| rank | param_id | source_symbol | confirm_ema_period | confirm_min_distance | total_trades | win_rate | expectancy | max_dd_pct | consistency_score | overall_survival |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | short_cand_061_DOGE_USDT__4h_ema20_dist0.000 | DOGE/USDT | 20 | 0.0 | 50 | 0.6 | 2.398417813050405 | 1.7604723347062021 | 9.728635772454117 | True |
| 1 | short_cand_062_DOGE_USDT__4h_ema20_dist0.000 | DOGE/USDT | 20 | 0.0 | 51 | 0.5882352941176471 | 2.1553115814219654 | 1.7639359509945047 | 10.613693718646356 | True |
