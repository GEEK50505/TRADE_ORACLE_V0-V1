# Daily Wider v2 sweep optimization summary

- **symbols_processed**: BTC/USDT, ETH/USDT, SOL/USDT, XRP/USDT, DOGE/USDT, AVAX/USDT, LINK/USDT, TON/USDT, ADA/USDT, BNB/USDT
- **combinations_per_symbol**: 311220
- **total_rows_written**: 3112200
- **candidates_after_relaxed_gates**: 3893
- **top_candidates_saved**: 200
- **best_expectancy**: 16369.38790200003
- **best_win_rate**: 1.0
- **best_total_trades**: 114
- **elapsed_seconds**: 149.87

## Temporary Run Logic

- Widening further is intended to break the current trade starvation and surface more parameter neighborhoods.
- The relaxed gates are temporary discovery gates, not deployment gates.
- Success for this pass is 100+ candidates for Backtrader validation.
- After candidate generation, the next step is chronological Backtrader validation under Maven-style constraints.
