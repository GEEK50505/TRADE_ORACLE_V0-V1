# Combined Validation Runbook

This is the exact execution order for the final combined long + short portfolio phase.

## 1. Finish the short 4H validation branch

If the short 4H results are incomplete, rerun:

```powershell
python scripts\backtrader_evaluate_short_4h.py
```

Then generate the short 4H survivor analysis and final shortlist:

```powershell
python scripts\analyze_backtrader_survivors.py --validation-results results\backtrader_short_4h_results.csv --shortlist results\short_plus_4h_candidates.csv --ranking-csv results\backtrader_short_4h_survivor_ranking.csv --asset-stats-csv results\backtrader_short_4h_survivor_asset_stats.csv --report-md results\backtrader_short_4h_survivor_report.md
python scripts\build_short_final_shortlist.py --ranking-csv results\backtrader_short_4h_survivor_ranking.csv --output-csv results\backtrader_short_4h_final_shortlist.csv --output-md results\backtrader_short_4h_final_shortlist.md
```

Outputs:
- `results/backtrader_short_4h_results.csv`
- `results/backtrader_short_4h_summary.md`
- `results/backtrader_short_4h_survivor_ranking.csv`
- `results/backtrader_short_4h_survivor_asset_stats.csv`
- `results/backtrader_short_4h_survivor_report.md`
- `results/backtrader_short_4h_final_shortlist.csv`
- `results/backtrader_short_4h_final_shortlist.md`

## 2. Build the combined candidate matrix

```powershell
python scripts\build_combined_candidates.py
```

Outputs:
- `results/backtrader_combined_candidates.csv`

## 3. Run chronological Backtrader validation on the combined pairs

```powershell
python scripts\backtrader_evaluate_combined.py
```

Outputs:
- `results/backtrader_combined_results.csv`
- `results/backtrader_combined_summary.md`

## 4. Generate the combined survivor analysis report

```powershell
python scripts\analyze_backtrader_combined_survivors.py
```

Outputs:
- `results/backtrader_combined_survivor_ranking.csv`
- `results/backtrader_combined_survivor_report.md`

## 5. Build the final combined shortlist

```powershell
python scripts\build_combined_final_shortlist.py
```

Outputs:
- `results/backtrader_combined_final_shortlist.csv`
- `results/backtrader_combined_final_shortlist.md`

## Notes

- The combined phase is a `25`-pair portfolio study built from `5` long 4H finalists and `5` short 4H finalists.
- Both sides share the same portfolio rules: fixed `$10` risk, max `4` concurrent trades, floating-aware `3%` trailing drawdown, and `20%` consistency ceiling.
- The combined validator allows only one net position per symbol at a time.
- If both sides signal on the same symbol while flat on the same bar, the validator skips both and records a signal conflict instead of choosing a side heuristically.
