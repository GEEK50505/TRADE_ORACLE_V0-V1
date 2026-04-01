# Backtrader validation summary

- **source_candidates_file**: results\daily_plus_4h_candidates.csv
- **candidates_evaluated**: 84
- **survivors**: 41
- **breached_accounts**: 24
- **median_max_dd_pct**: 2.07
- **median_consistency_score**: 17.46
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
| 10 | cand_002_AVAX_USDT__4h_ema15_dist0.000 | AVAX/USDT | 15 | 0.0 | 76 | 0.5921052631578947 | 1.8421052631578945 | 1.805129430257359 | 8.33333333333334 | True |
| 7 | cand_008_AVAX_USDT__4h_ema15_dist0.008 | AVAX/USDT | 15 | 0.008 | 73 | 0.589041095890411 | 1.8036529680365296 | 1.781269321465426 | 8.86075949367089 | True |
| 3 | cand_002_AVAX_USDT__4h_ema25_dist0.008 | AVAX/USDT | 25 | 0.008 | 73 | 0.589041095890411 | 1.8036529680365299 | 1.8517202350057012 | 8.86075949367089 | True |
| 5 | cand_002_AVAX_USDT__4h_ema30_dist0.008 | AVAX/USDT | 30 | 0.008 | 73 | 0.589041095890411 | 1.8036529680365299 | 1.8517202350057012 | 8.86075949367089 | True |
| 14 | cand_002_AVAX_USDT__4h_ema30_dist0.004 | AVAX/USDT | 30 | 0.004 | 73 | 0.589041095890411 | 1.8036529680365299 | 1.8517202350057012 | 8.86075949367089 | True |
| 4 | cand_002_AVAX_USDT__4h_ema15_dist0.004 | AVAX/USDT | 15 | 0.004 | 73 | 0.589041095890411 | 1.8036529680365296 | 1.8080165927115806 | 8.860759493670892 | True |
| 15 | cand_002_AVAX_USDT__4h_ema25_dist0.000 | AVAX/USDT | 25 | 0.0 | 77 | 0.5844155844155844 | 1.6883116883116882 | 1.8517202350057012 | 8.97435897435898 | True |
| 9 | cand_002_AVAX_USDT__4h_ema25_dist0.004 | AVAX/USDT | 25 | 0.004 | 74 | 0.581081081081081 | 1.6441441441441447 | 1.8517202350057012 | 9.589041095890414 | True |
