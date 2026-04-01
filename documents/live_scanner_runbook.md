# TRADE_ORACLE Live Scanner Runbook

## Purpose

`scanner_live.py` is the production entry point for the final TRADE_ORACLE deployment stack.
It does not optimize or rank new ideas. It only scans the exact five validated combined
long + short pairs from `results/backtrader_combined_final_shortlist.csv`.

## Pipeline Position

1. `scanner_live.py`
   - Reads the final combined shortlist.
   - Rebuilds the full parameter blocks from `results/backtrader_combined_survivor_ranking.csv`.
   - Scans the latest Daily signal bars plus 4H execution bars.
   - Emits only currently valid setups.
2. MT5 bridge
   - Consumes the scanner output table or JSON.
   - Converts each setup into a broker-ready order ticket.
   - Applies account-state checks before sending orders.
3. Live trading executor
   - Sizes risk at the fixed Maven amount of `$10`.
   - Places the initial stop, TP1, and TP2.
   - Enforces max concurrent trades, trailing drawdown protection, and account locking.

## Standard Commands

Dry run against the local research dataset:

```powershell
python scripts\scanner_live.py --test
```

Live-style scan with JSON output for downstream automation:

```powershell
python scripts\scanner_live.py --live
```

Explicit JSON output path:

```powershell
python scripts\scanner_live.py --live --json-output results\scanner_live_setups.json
```

## Operational Notes

- The scanner prints a human-readable table first so you can visually verify the setups.
- In `--live` mode it also writes JSON by default to `results/scanner_live_setups.json`.
- If no setups qualify, the scanner exits cleanly and prints `No valid setups right now.`
- Same-symbol long and short conflicts are skipped intentionally to stay aligned with the combined validator.
- The scanner is signal-only. It does not place trades, manage positions, or track MT5 account state.

## Recommended Production Flow

1. Run the scanner at the Daily close or immediately after each relevant 4H close.
2. Validate the printed setups and JSON payload.
3. Pass the JSON payload into the MT5 bridge.
4. Let the bridge submit orders only if all Maven portfolio constraints still pass in the live account.
