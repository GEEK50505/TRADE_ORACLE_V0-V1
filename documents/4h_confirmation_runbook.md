# 4H Confirmation Runbook

This is the exact execution order for the Daily + 4H confirmation phase.

## 1. Build the combined Daily + 4H candidate file

```powershell
python scripts\vectorbt_4h_confirmation_sweep.py
```

Outputs:
- `results/daily_plus_4h_candidates.csv`
- `results/daily_plus_4h_sweep_summary.md`

## 2. Run chronological Backtrader validation on the combined candidates

```powershell
python scripts\backtrader_evaluate.py --candidates results\daily_plus_4h_candidates.csv --output-prefix results\backtrader_4h_validation
```

Outputs:
- `results/backtrader_4h_validation_results.csv`
- `results/backtrader_4h_validation_summary.md`

## 3. Generate the 4H survivor analysis report

```powershell
python scripts\analyze_backtrader_survivors.py --validation-results results\backtrader_4h_validation_results.csv --shortlist results\daily_plus_4h_candidates.csv --ranking-csv results\backtrader_4h_survivor_ranking.csv --asset-stats-csv results\backtrader_4h_survivor_asset_stats.csv --report-md results\backtrader_4h_survivor_report.md
```

Outputs:
- `results/backtrader_4h_survivor_ranking.csv`
- `results/backtrader_4h_survivor_asset_stats.csv`
- `results/backtrader_4h_survivor_report.md`

## Notes

- The 4H layer is a confirmation filter only. It never creates entries on its own.
- The confirmation rule is currently long-only: execution close must be above the execution EMA, and the distance above that EMA must meet the configured threshold.
- Symbols with real 4H data use the 4H execution feed directly.
- Symbols without 4H data fall back to the Daily execution feed so the portfolio remains consistent with the existing mixed-feed Backtrader design.
