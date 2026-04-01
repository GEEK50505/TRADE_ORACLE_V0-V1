# Backtrader validation summary

- **source_candidates_file**: results\daily_plus_4h_candidates.csv
- **candidates_evaluated**: 2
- **survivors**: 2
- **breached_accounts**: 0
- **median_max_dd_pct**: 1.73
- **median_consistency_score**: 8.19
- **best_expectancy**: 2.11
- **best_total_return_pct**: 2.87
- **confirmation_filter**: enabled for this candidate set

## Data Coverage Notes

- **4H execution + Daily signals available**: 4 symbols
- **Daily fallback symbols**: 6 symbols
- Mixed-timeframe validation is therefore partially intraday-aware, not fully intraday for the whole watchlist.

## Top 10 Surviving Candidates

| rank | param_id | source_symbol | confirm_ema_period | confirm_min_distance | total_trades | win_rate | expectancy | max_dd_pct | consistency_score | overall_survival |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | cand_002_AVAX_USDT__4h_ema15_dist0.008 | AVAX/USDT | 15 | 0.008 | 68 | 0.6029411764705882 | 2.107843137254902 | 1.7254994402072996 | 8.139534883720934 | True |
| 2 | cand_002_AVAX_USDT__4h_ema20_dist0.008 | AVAX/USDT | 20 | 0.008 | 72 | 0.5972222222222222 | 1.9675925925925928 | 1.7280104656168114 | 8.235294117647063 | True |
