# Short Optimization Runbook

This is the exact execution order for the short-only phase.

## 1. Build the short discovery candidate file

```powershell
python scripts\vectorbt_short_sweep.py
```

Outputs:
- `results/short_wider_sweep_results.csv`
- `results/short_candidates.csv`
- `results/short_top_candidates.csv`
- `results/short_optimization_summary.md`

## 2. Run chronological Backtrader validation on the short candidates

```powershell
python scripts\backtrader_evaluate_short.py --candidates results\short_candidates.csv --output-prefix results\backtrader_short
```

Outputs:
- `results/backtrader_short_results.csv`
- `results/backtrader_short_summary.md`

## 3. Generate the short survivor analysis report

```powershell
python scripts\analyze_backtrader_survivors.py --validation-results results\backtrader_short_results.csv --shortlist results\short_candidates.csv --ranking-csv results\backtrader_short_survivor_ranking.csv --asset-stats-csv results\backtrader_short_survivor_asset_stats.csv --report-md results\backtrader_short_survivor_report.md
```

Outputs:
- `results/backtrader_short_survivor_ranking.csv`
- `results/backtrader_short_survivor_asset_stats.csv`
- `results/backtrader_short_survivor_report.md`

## 4. Build the final top-5 short shortlist

```powershell
python scripts\build_short_final_shortlist.py
```

Outputs:
- `results/backtrader_short_final_shortlist.csv`
- `results/backtrader_short_final_shortlist.md`

## Notes

- This phase is purely short-only. Do not combine it with the long finalists yet.
- The short signal logic mirrors the long architecture, but the trade mechanics are fully inverted: short entry, short stop, and downside profit targets.
- Symbols with real 4H data use the 4H execution feed directly.
- Symbols without 4H data fall back to the Daily execution feed so the portfolio remains consistent with the existing mixed-feed Backtrader design.
