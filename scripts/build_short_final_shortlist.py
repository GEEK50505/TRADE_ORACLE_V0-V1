"""
Build the final top-5 shortlist for the short-only phase.

This script reads the ranked short-side survivor table, removes exact outcome
duplicates, and writes a compact final shortlist in the same general format used
for the long-side finalists.

Recommended usage:
    python scripts/build_short_final_shortlist.py
"""

from __future__ import annotations

import argparse
import math
import os
from typing import List

import pandas as pd


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

DEFAULT_RANKING_CSV = os.path.join(RESULTS_DIR, "backtrader_short_survivor_ranking.csv")
DEFAULT_OUTPUT_CSV = os.path.join(RESULTS_DIR, "backtrader_short_final_shortlist.csv")
DEFAULT_OUTPUT_MD = os.path.join(RESULTS_DIR, "backtrader_short_final_shortlist.md")


def parse_args() -> argparse.Namespace:
    """Expose the shortlist paths and row count for reuse."""
    parser = argparse.ArgumentParser(description="Build the final short-side shortlist.")
    parser.add_argument("--ranking-csv", default=DEFAULT_RANKING_CSV)
    parser.add_argument("--output-csv", default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--output-md", default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--top-n", type=int, default=5)
    return parser.parse_args()


def build_rationale(row: pd.Series, priority: int) -> str:
    """Generate a short human-readable reason for keeping a shortlist row."""
    if priority == 1:
        return "Best overall short candidate after deduplication, balancing expectancy, drawdown control, and consistency."
    if priority == 2:
        return "Closest clean alternate to the primary short candidate with a very similar edge profile."
    if float(row["max_dd_pct"]) < 2.0:
        return "Short candidate with especially strong trailing-drawdown control for the short side."
    if float(row["consistency_score"]) < 12.0:
        return "Short candidate with a relatively comfortable consistency profile under Maven rules."
    return "High-ranking short survivor kept as a distinct parameter neighborhood rather than a threshold duplicate."


def build_role(priority: int) -> str:
    """Assign a lightweight shortlist role label."""
    if priority == 1:
        return "primary"
    if priority == 2:
        return "secondary"
    if priority == 3:
        return "throughput_variant"
    if priority == 4:
        return "alternate_base"
    return "reserve"


def main() -> None:
    """Build the final short shortlist from the ranked survivor file."""
    args = parse_args()

    if not os.path.exists(args.ranking_csv):
        raise FileNotFoundError(f"Ranking file not found: {args.ranking_csv}")

    ranking = pd.read_csv(args.ranking_csv)
    if ranking.empty:
        raise ValueError("Ranking file is empty.")

    # If the signature helper columns are missing, derive them on the fly so the
    # shortlist remains robust to future report changes.
    if "win_rate_sig" not in ranking.columns:
        ranking["win_rate_sig"] = ranking["win_rate"].round(6)
    if "expectancy_sig" not in ranking.columns:
        ranking["expectancy_sig"] = ranking["expectancy"].round(6)
    if "max_dd_pct_sig" not in ranking.columns:
        ranking["max_dd_pct_sig"] = ranking["max_dd_pct"].round(6)
    if "consistency_sig" not in ranking.columns:
        ranking["consistency_sig"] = ranking["consistency_score"].round(6)

    deduped = ranking.drop_duplicates(
        subset=["total_trades", "win_rate_sig", "expectancy_sig", "max_dd_pct_sig", "consistency_sig"]
    ).copy()

    shortlist = deduped.head(max(1, int(args.top_n))).copy().reset_index(drop=True)
    shortlist.insert(0, "shortlist_priority", range(1, len(shortlist) + 1))
    shortlist["shortlist_role"] = [build_role(priority) for priority in shortlist["shortlist_priority"]]
    shortlist["shortlist_rationale"] = [
        build_rationale(row, int(row["shortlist_priority"]))
        for _, row in shortlist.iterrows()
    ]

    export_columns: List[str] = [
        "shortlist_priority",
        "param_id",
        "source_symbol",
        "sma",
        "fib_band",
        "rw",
        "eb",
        "rw_lookback",
        "confirm_ema_period",
        "confirm_min_distance",
        "total_trades",
        "win_rate",
        "expectancy",
        "max_dd_pct",
        "consistency_score",
        "composite_score",
        "shortlist_role",
        "shortlist_rationale",
    ]
    shortlist[export_columns].to_csv(args.output_csv, index=False)

    with open(args.output_md, "w", encoding="utf-8") as handle:
        handle.write("# Short Final Shortlist\n\n")
        handle.write("This shortlist trims the ranked short survivors down to the most actionable top candidates after removing exact outcome duplicates.\n\n")
        handle.write("| priority | param_id | source_symbol | total_trades | win_rate | expectancy | max_dd_pct | consistency_score | role |\n")
        handle.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
        for _, row in shortlist.iterrows():
            handle.write(
                f"| {int(row['shortlist_priority'])} | {row['param_id']} | {row['source_symbol']} | "
                f"{int(row['total_trades'])} | {float(row['win_rate']):.4f} | {float(row['expectancy']):.4f} | "
                f"{float(row['max_dd_pct']):.4f} | {float(row['consistency_score']):.4f} | {row['shortlist_role']} |\n"
            )

        handle.write("\n## Rationale\n\n")
        for _, row in shortlist.iterrows():
            handle.write(f"- **{row['param_id']}**: {row['shortlist_rationale']}\n")

    print(f"Final shortlist CSV: {args.output_csv}")
    print(f"Final shortlist MD: {args.output_md}")
    print(f"Rows selected: {len(shortlist)}")


if __name__ == "__main__":
    main()
