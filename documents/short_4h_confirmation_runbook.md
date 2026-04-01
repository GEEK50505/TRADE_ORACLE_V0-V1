# Short 4H Confirmation Runbook

This is the exact execution order for the short Daily + 4H confirmation phase.

## 1. Build the combined short Daily + 4H candidate file

```powershell
python scripts\vectorbt_short_4h_confirmation_sweep.py
```

Outputs:
- `results/short_4h_sweep_results.csv`
- `results/short_plus_4h_candidates.csv`
- `results/short_4h_optimization_summary.md`

## 2. Run chronological Backtrader validation on the combined short candidates

```powershell
python scripts\backtrader_evaluate_short_4h.py
```

Outputs:
- `results/backtrader_short_4h_results.csv`
- `results/backtrader_short_4h_summary.md`

## 3. Generate the short + 4H survivor analysis report

```powershell
python scripts\analyze_backtrader_survivors.py --validation-results results\backtrader_short_4h_results.csv --shortlist results\short_plus_4h_candidates.csv --ranking-csv results\backtrader_short_4h_survivor_ranking.csv --asset-stats-csv results\backtrader_short_4h_survivor_asset_stats.csv --report-md results\backtrader_short_4h_survivor_report.md
```

Outputs:
- `results/backtrader_short_4h_survivor_ranking.csv`
- `results/backtrader_short_4h_survivor_asset_stats.csv`
- `results/backtrader_short_4h_survivor_report.md`

## 4. Build the final short + 4H shortlist

```powershell
python scripts\build_short_final_shortlist.py --ranking-csv results\backtrader_short_4h_survivor_ranking.csv --output-csv results\backtrader_short_4h_final_shortlist.csv --output-md results\backtrader_short_4h_final_shortlist.md
```

Outputs:
- `results/backtrader_short_4h_final_shortlist.csv`
- `results/backtrader_short_4h_final_shortlist.md`

## Notes

- The Daily short layer is unchanged from the validated short-only phase.
- The 4H layer is confirmation-only: execution close must be below the 4H EMA and far enough below it to clear the configured minimum-distance threshold.
- By default the sweep uses only the top 20 short survivors as the Daily base set.
- Symbols with real 4H data use the 4H execution feed directly.
- Symbols without 4H data fall back to the Daily execution feed so the portfolio remains consistent with the existing mixed-feed Backtrader design.
