"""
Build the final deployment shortlist for the combined long + short portfolio study.

This script reads the ranked combined survivor table, removes exact outcome
duplicates, and writes the most actionable top 5-7 pair portfolios.
"""

from __future__ import annotations

import argparse
import os
from typing import List

import pandas as pd


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

DEFAULT_RANKING_CSV = os.path.join(RESULTS_DIR, "backtrader_combined_survivor_ranking.csv")
DEFAULT_OUTPUT_CSV = os.path.join(RESULTS_DIR, "backtrader_combined_final_shortlist.csv")
DEFAULT_OUTPUT_MD = os.path.join(RESULTS_DIR, "backtrader_combined_final_shortlist.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the final combined long + short shortlist.")
    parser.add_argument("--ranking-csv", default=DEFAULT_RANKING_CSV)
    parser.add_argument("--output-csv", default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--output-md", default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--top-n", type=int, default=5)
    return parser.parse_args()


def build_role(priority: int) -> str:
    """Assign a lightweight role label for the final shortlist."""
    if priority == 1:
        return "primary"
    if priority == 2:
        return "secondary"
    if priority == 3:
        return "throughput_variant"
    if priority == 4:
        return "pair_diversifier"
    return "reserve"


def build_rationale(row: pd.Series, priority: int) -> str:
    """Generate a short pair-aware reason for keeping a shortlist row."""
    if priority == 1:
        return "Best overall combined pair after deduplication, balancing expectancy, drawdown control, and consistency."
    if priority == 2:
        return "Closest clean alternate to the primary pair with a very similar edge profile."
    if float(row["max_dd_pct"]) < 2.0:
        return "Combined pair with especially strong trailing-drawdown control under shared portfolio rules."
    if abs(float(row["long_profit_share_pct"])) < 70.0 and abs(float(row["short_profit_share_pct"])) < 70.0:
        return "More balanced long/short profit contribution than the more one-sided pair variants."
    return "High-ranking combined survivor kept as a distinct pair neighborhood rather than a threshold duplicate."


def main() -> None:
    """Build the final combined shortlist from the ranked combined-survivor file."""
    args = parse_args()

    if not os.path.exists(args.ranking_csv):
        raise FileNotFoundError(f"Ranking file not found: {args.ranking_csv}")

    ranking = pd.read_csv(args.ranking_csv)
    if ranking.empty:
        raise ValueError("Ranking file is empty.")

    for column, source in [
        ("win_rate_sig", "win_rate"),
        ("expectancy_sig", "expectancy"),
        ("max_dd_pct_sig", "max_dd_pct"),
        ("consistency_sig", "consistency_score"),
    ]:
        if column not in ranking.columns:
            ranking[column] = ranking[source].round(6)

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
        "long_param_id",
        "short_param_id",
        "long_source_symbol",
        "short_source_symbol",
        "long_confirm_ema_period",
        "long_confirm_min_distance",
        "short_confirm_ema_period",
        "short_confirm_min_distance",
        "total_trades",
        "long_total_trades",
        "short_total_trades",
        "win_rate",
        "expectancy",
        "max_dd_pct",
        "consistency_score",
        "signal_conflicts",
        "composite_score",
        "shortlist_role",
        "shortlist_rationale",
    ]
    shortlist[export_columns].to_csv(args.output_csv, index=False)

    with open(args.output_md, "w", encoding="utf-8") as handle:
        handle.write("# Combined Final Shortlist\n\n")
        handle.write("This shortlist trims the ranked combined survivors down to the most actionable pair portfolios after removing exact outcome duplicates.\n\n")
        handle.write("| priority | long_param_id | short_param_id | total_trades | win_rate | expectancy | max_dd_pct | consistency_score | role |\n")
        handle.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
        for _, row in shortlist.iterrows():
            handle.write(
                f"| {int(row['shortlist_priority'])} | {row['long_param_id']} | {row['short_param_id']} | "
                f"{int(row['total_trades'])} | {float(row['win_rate']):.4f} | {float(row['expectancy']):.4f} | "
                f"{float(row['max_dd_pct']):.4f} | {float(row['consistency_score']):.4f} | {row['shortlist_role']} |\n"
            )

        handle.write("\n## Rationale\n\n")
        for _, row in shortlist.iterrows():
            handle.write(
                f"- **{row['long_param_id']} + {row['short_param_id']}**: {row['shortlist_rationale']}\n"
            )

    print(f"Combined final shortlist CSV: {args.output_csv}")
    print(f"Combined final shortlist MD: {args.output_md}")
    print(f"Rows selected: {len(shortlist)}")


if __name__ == "__main__":
    main()
