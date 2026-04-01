# Backtrader short + 4H validation summary

- **source_candidates_file**: C:\Users\G_R_E\Documents\REPOSITORIES\TRADE_ORACLE\TRADE_ORACLE\results\short_plus_4h_candidates.csv
- **candidates_evaluated**: 240
- **survivors**: 223
- **breached_accounts**: 0
- **median_max_dd_pct**: 1.76
- **median_consistency_score**: 9.15
- **best_expectancy**: 2.93
- **best_total_return_pct**: 5.10
- **strategy_side**: short-only
- **confirmation_filter**: enabled for this candidate set

## Data Coverage Notes

- **4H execution + Daily signals available**: 4 symbols
- **Daily fallback symbols**: 6 symbols
- Mixed-timeframe validation is therefore partially intraday-aware, not fully intraday for the whole watchlist.

## Top 10 Surviving Candidates

| rank | param_id | source_symbol | confirm_ema_period | confirm_min_distance | total_trades | win_rate | expectancy | max_dd_pct | consistency_score | overall_survival |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 98 | short_cand_088_ETH_USDT__4h_ema20_dist0.000 | ETH/USDT | 20 | 0.0 | 87 | 0.632183908045977 | 2.9313081560482193 | 1.826122828219074 | 4.574736251511037 | True |
| 132 | short_cand_088_ETH_USDT__4h_ema25_dist0.000 | ETH/USDT | 25 | 0.0 | 85 | 0.611764705882353 | 2.7545826239360642 | 1.824384497490081 | 4.982783989418287 | True |
| 136 | short_cand_088_ETH_USDT__4h_ema30_dist0.000 | ETH/USDT | 30 | 0.0 | 86 | 0.6046511627906976 | 2.606273523657738 | 1.8342790348056286 | 5.205091234564422 | True |
| 89 | short_cand_076_ETH_USDT__4h_ema20_dist0.000 | ETH/USDT | 20 | 0.0 | 80 | 0.625 | 2.742919639950776 | 1.6842656788051444 | 5.316719134212422 | True |
| 109 | short_cand_088_ETH_USDT__4h_ema15_dist0.000 | ETH/USDT | 15 | 0.0 | 75 | 0.6266666666666667 | 2.9063189671533225 | 1.7695810723662224 | 5.35232220942077 | True |
| 43 | short_cand_074_DOGE_USDT__4h_ema25_dist0.000 | DOGE/USDT | 25 | 0.0 | 77 | 0.6103896103896104 | 2.779235120000406 | 2.5601292623922274 | 5.451685264941868 | True |
| 71 | short_cand_074_DOGE_USDT__4h_ema30_dist0.000 | DOGE/USDT | 30 | 0.0 | 77 | 0.6103896103896104 | 2.779235120000406 | 2.5601292623922274 | 5.451685264941868 | True |
| 121 | short_cand_076_ETH_USDT__4h_ema25_dist0.000 | ETH/USDT | 25 | 0.0 | 78 | 0.6153846153846154 | 2.709356533800576 | 1.6826357017680378 | 5.520596780329798 | True |
| 47 | short_cand_074_DOGE_USDT__4h_ema20_dist0.000 | DOGE/USDT | 20 | 0.0 | 75 | 0.6133333333333333 | 2.764459167644861 | 2.5634076813874174 | 5.626979677478064 | True |
| 129 | short_cand_076_ETH_USDT__4h_ema30_dist0.000 | ETH/USDT | 30 | 0.0 | 79 | 0.6075949367088608 | 2.548478602992973 | 1.7563143182106247 | 5.794803406278471 | True |
