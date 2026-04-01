"""
Prepare a representative Backtrader shortlist from the wider v2 candidate pool.

Why this exists:
- The wider daily v2 sweep intentionally relaxed the gates and surfaced thousands
  of candidate rows.
- Many of those rows are threshold-neighbor duplicates that produce the exact
  same trade sequence and metrics.
- Backtrader validation is chronological and slower, so we want a compact,
  representative shortlist rather than brute-forcing every relaxed hit.

Default behavior:
- Load `results/daily_wider_v2_candidates.csv`
- Sort by expectancy, win_rate, total_trades, total_return
- Deduplicate by symbol + performance signature
- Keep the top N unique signatures per symbol
- Save a Backtrader-ready shortlist CSV and a short markdown summary

Recommended usage:
    python scripts/prepare_backtrader_shortlist.py
"""

from __future__ import annotations

import argparse
import os

import pandas as pd


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

DEFAULT_INPUT = os.path.join(RESULTS_DIR, "daily_wider_v2_candidates.csv")
DEFAULT_OUTPUT = os.path.join(RESULTS_DIR, "daily_wider_v2_backtrader_shortlist.csv")
DEFAULT_SUMMARY = os.path.join(RESULTS_DIR, "daily_wider_v2_backtrader_shortlist_summary.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a representative Backtrader shortlist.")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Candidate CSV from the wider v2 sweep.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Shortlist CSV path.")
    parser.add_argument("--summary", default=DEFAULT_SUMMARY, help="Summary markdown path.")
    parser.add_argument(
        "--per-symbol",
        type=int,
        default=15,
        help="Maximum unique performance signatures to keep per symbol.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not os.path.exists(args.input):
        raise FileNotFoundError(f"Candidate file not found: {args.input}")

    df = pd.read_csv(args.input)
    if df.empty:
        raise ValueError("Candidate file is empty. Run the wider v2 sweep first.")

    # Round performance metrics to stabilize float-based signature comparisons.
    df["total_return_sig"] = df["total_return"].round(8)
    df["win_rate_sig"] = df["win_rate"].round(8)
    df["expectancy_sig"] = df["expectancy"].round(6)

    ranked = df.sort_values(
        by=["expectancy", "win_rate", "total_trades", "total_return"],
        ascending=[False, False, False, False],
    ).copy()

    unique_perf = ranked.drop_duplicates(
        subset=["symbol", "total_return_sig", "total_trades", "win_rate_sig", "expectancy_sig"]
    ).copy()

    shortlist = (
        unique_perf.groupby("symbol", group_keys=False)
        .head(args.per_symbol)
        .sort_values(by=["symbol", "expectancy", "win_rate", "total_trades"], ascending=[True, False, False, False])
        .reset_index(drop=True)
    )
    shortlist.insert(0, "backtrader_rank", range(1, len(shortlist) + 1))

    drop_cols = ["total_return_sig", "win_rate_sig", "expectancy_sig"]
    shortlist = shortlist.drop(columns=drop_cols)
    shortlist.to_csv(args.output, index=False)

    symbol_counts = shortlist.groupby("symbol").size().sort_values(ascending=False)
    with open(args.summary, "w", encoding="utf-8") as handle:
        handle.write("# Backtrader shortlist summary\n\n")
        handle.write(f"- **source_candidates**: {len(df)}\n")
        handle.write(f"- **unique_performance_signatures**: {len(unique_perf)}\n")
        handle.write(f"- **per_symbol_cap**: {args.per_symbol}\n")
        handle.write(f"- **shortlist_rows**: {len(shortlist)}\n")
        handle.write("\n## Rows per symbol\n\n")
        for symbol, count in symbol_counts.items():
            handle.write(f"- **{symbol}**: {count}\n")

    print(f"Source candidates: {len(df):,}")
    print(f"Unique performance signatures: {len(unique_perf):,}")
    print(f"Shortlist rows saved: {len(shortlist):,}")
    print(f"Shortlist CSV: {args.output}")
    print(f"Summary MD: {args.summary}")


if __name__ == "__main__":
    main()
