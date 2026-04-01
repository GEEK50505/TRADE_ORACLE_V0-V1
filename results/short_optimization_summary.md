# Short sweep optimization summary

- **symbols_processed**: BTC/USDT, ETH/USDT, SOL/USDT, XRP/USDT, DOGE/USDT, AVAX/USDT, LINK/USDT, TON/USDT, ADA/USDT, BNB/USDT
- **combinations_per_symbol**: 311220
- **total_rows_written**: 3112200
- **candidates_after_relaxed_gates**: 258004
- **top_candidates_saved**: 200
- **best_expectancy**: 3220.651947709705
- **best_win_rate**: 1.0
- **best_total_trades**: 84
- **elapsed_seconds**: 157.11

## Temporary Run Logic

- The short side is being discovered independently from the long side to avoid edge contamination.
- The relaxed gates are temporary discovery gates, not deployment gates.
- Success for this pass is 100+ short candidates for Backtrader validation.
- After candidate generation, the next step is chronological Backtrader validation under the same Maven-style rules used on the long side.
