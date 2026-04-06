"""
Final clean backtest for the selected 3-pair realistic survivor.

This script re-runs the exact 3-pair shortlist through the same corrected full
realistic Backtrader engine used by the earlier re-optimization and survival
search passes, then writes the final survivor shortlist plus comparison
artifacts.
"""

from __future__ import annotations

import argparse
import os
from typing import Dict, List

import pandas as pd

from backtrader_evaluate import (
    DEFAULT_DAILY_PATH,
    DEFAULT_INTRADAY_PATH,
    MarketDataCatalog,
)
from backtrader_evaluate_final_portfolio_full import DEFAULT_PRIOR_NETTED_RESULTS, load_prior_netted_results
from backtrader_reoptimize_full_realistic import (
    DEFAULT_CANDIDATES_PATH,
    DEFAULT_OLD_SHORTLIST_PATH,
    DEFAULT_REALISTIC_RANKING_PATH,
    DEFAULT_REALISTIC_SHORTLIST_PATH,
    RealisticPortfolioEvaluator,
    build_candidate_lookup,
    build_portfolio_summary_row,
    build_shortlist_output,
    load_candidate_pool,
    markdown_table,
    read_shortlist_priority_maps,
)
from backtrader_survival_first_search import DEFAULT_RESULTS_OUTPUT as DEFAULT_FOUR_PAIR_SEARCH_RESULTS


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

FINAL_3PAIR_IDS = [
    "combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004",
    "combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004",
    "combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004",
]

DEFAULT_SUMMARY_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_final_3pair_backtest_summary.md")
DEFAULT_SURVIVOR_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_final_shortlist_survivor.csv")
DEFAULT_COMPARISON_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_final_3pair_comparison.csv")


def parse_args() -> argparse.Namespace:
    """Define the CLI surface for the final clean 3-pair rerun."""
    parser = argparse.ArgumentParser(
        description="Run the final clean realistic backtest for the fixed 3-pair survivor shortlist."
    )
    parser.add_argument("--candidates", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--ranking", default=DEFAULT_REALISTIC_RANKING_PATH)
    parser.add_argument("--old-shortlist", default=DEFAULT_OLD_SHORTLIST_PATH)
    parser.add_argument("--new-shortlist", default=DEFAULT_REALISTIC_SHORTLIST_PATH)
    parser.add_argument("--four-pair-search-results", default=DEFAULT_FOUR_PAIR_SEARCH_RESULTS)
    parser.add_argument("--daily-data", default=DEFAULT_DAILY_PATH)
    parser.add_argument("--intraday-data", default=DEFAULT_INTRADAY_PATH)
    parser.add_argument("--summary-output", default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--survivor-output", default=DEFAULT_SURVIVOR_OUTPUT)
    parser.add_argument("--comparison-output", default=DEFAULT_COMPARISON_OUTPUT)
    return parser.parse_args()


def as_bool(value: object) -> bool:
    """Normalize CSV values into booleans."""
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def build_selected_ids(row: Dict[str, object]) -> List[str]:
    """Extract the ordered shortlist ids from one portfolio row."""
    portfolio_size = int(row.get("portfolio_size", 0))
    return [str(row.get(f"priority_{priority}_param_id", "")) for priority in range(1, portfolio_size + 1)]


def choose_best_four_pair_near_miss(four_pair_results_df: pd.DataFrame) -> Dict[str, object]:
    """Select the closest 4-pair near-miss from the prior survival-first search."""
    frame = four_pair_results_df.loc[four_pair_results_df["portfolio_size"] == 4].copy()
    if frame.empty:
        raise ValueError("No 4-pair portfolios were found in the prior survival-first search results.")

    near_miss_df = frame.loc[~frame["overall_survival"].apply(as_bool)].copy()
    if near_miss_df.empty:
        near_miss_df = frame.copy()

    ordered = near_miss_df.sort_values(
        by=[
            "max_dd_pct",
            "consistency_score",
            "penalized_expectancy",
            "expectancy",
            "diversity_penalty",
            "portfolio_param_ids",
        ],
        ascending=[True, True, False, False, True, True],
    ).reset_index(drop=True)
    return ordered.iloc[0].to_dict()


def write_summary_markdown(
    summary_path: str,
    final_ids: List[str],
    shortlist_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    final_summary_df: pd.DataFrame,
) -> None:
    """Write the final clean 3-pair backtest summary markdown."""
    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write("# Backtrader final 3-pair clean backtest summary\n\n")
        handle.write("- **objective**: rerun the fixed 3-pair realistic survivor shortlist through the full corrected baseline engine\n")
        handle.write(f"- **selected_portfolio**: {' | '.join(final_ids)}\n")
        handle.write("- **ruleset**: full 34-month window, realistic symbol onboarding, pair-level stacking, baseline friction, All-In $10 risk\n")

        handle.write("\n## Portfolio Comparison\n\n")
        handle.write(markdown_table(comparison_df))

        handle.write("\n## Final 3-Pair Result\n\n")
        handle.write(markdown_table(final_summary_df))

        handle.write("\n## Final Survivor Shortlist\n\n")
        shortlist_display = shortlist_df[
            [
                "shortlist_priority",
                "param_id",
                "long_param_id",
                "short_param_id",
                "expectancy",
                "max_dd_pct",
                "consistency_score",
                "overall_survival",
                "portfolio_expectancy",
                "portfolio_max_dd_pct",
                "portfolio_consistency_score",
                "portfolio_overall_survival",
            ]
        ].copy()
        handle.write(markdown_table(shortlist_display))


def main() -> None:
    """Run the final clean realistic backtest for the fixed 3-pair shortlist."""
    args = parse_args()

    candidate_pool_df = load_candidate_pool(candidates_path=args.candidates, ranking_path=args.ranking)
    realistic_ranking_df = pd.read_csv(args.ranking)
    four_pair_results_df = pd.read_csv(args.four_pair_search_results)

    realistic_pair_lookup = {str(row["param_id"]): row.to_dict() for _, row in realistic_ranking_df.iterrows()}
    candidate_lookup = build_candidate_lookup(candidate_pool_df)

    old_ids, old_role_lookup, old_rationale_lookup = read_shortlist_priority_maps(args.old_shortlist, top_n=5)
    new_ids, new_role_lookup, new_rationale_lookup = read_shortlist_priority_maps(args.new_shortlist, top_n=5)
    best_four_pair_row = choose_best_four_pair_near_miss(four_pair_results_df)
    best_four_pair_ids = build_selected_ids(best_four_pair_row)

    catalog = MarketDataCatalog(daily_path=args.daily_data, intraday_path=args.intraday_data)
    raw_coverage_df = catalog.describe_symbol_coverage(prefer_intraday=True)
    prior_netted_results = load_prior_netted_results(DEFAULT_PRIOR_NETTED_RESULTS)

    evaluator = RealisticPortfolioEvaluator(
        candidate_lookup=candidate_lookup,
        pair_lookup=realistic_pair_lookup,
        catalog=catalog,
        raw_coverage_df=raw_coverage_df,
        prior_netted_results=prior_netted_results,
    )

    old_detail = evaluator.evaluate_with_details(
        old_ids,
        stage_label="old_shortlist_detail",
        role_lookup=old_role_lookup,
        rationale_lookup=old_rationale_lookup,
    )
    new_detail = evaluator.evaluate_with_details(
        new_ids,
        stage_label="new_realistic_shortlist_detail",
        role_lookup=new_role_lookup,
        rationale_lookup=new_rationale_lookup,
    )
    best_four_pair_detail = evaluator.evaluate_with_details(
        best_four_pair_ids,
        stage_label="best_four_pair_near_miss_detail",
    )
    final_three_pair_detail = evaluator.evaluate_with_details(
        FINAL_3PAIR_IDS,
        stage_label="final_3pair_survivor",
    )

    shortlist_df = build_shortlist_output(
        ordered_ids=FINAL_3PAIR_IDS,
        realistic_lookup=realistic_pair_lookup,
        best_portfolio_record=final_three_pair_detail["metrics"],
    )
    shortlist_df.to_csv(args.survivor_output, index=False)

    comparison_df = pd.DataFrame(
        [
            build_portfolio_summary_row("old_5pair_shortlist", old_ids, old_detail["metrics"]),
            build_portfolio_summary_row("new_realistic_5pair_shortlist", new_ids, new_detail["metrics"]),
            build_portfolio_summary_row("best_4pair_near_miss", best_four_pair_ids, best_four_pair_detail["metrics"]),
            build_portfolio_summary_row("final_3pair_survivor", FINAL_3PAIR_IDS, final_three_pair_detail["metrics"]),
        ]
    )
    comparison_df.to_csv(args.comparison_output, index=False)

    final_summary_df = pd.DataFrame(
        [build_portfolio_summary_row("final_3pair_survivor", FINAL_3PAIR_IDS, final_three_pair_detail["metrics"])]
    )
    write_summary_markdown(
        summary_path=args.summary_output,
        final_ids=FINAL_3PAIR_IDS,
        shortlist_df=shortlist_df,
        comparison_df=comparison_df,
        final_summary_df=final_summary_df,
    )

    print(f"Final survivor shortlist: {args.survivor_output}")
    print(f"Comparison: {args.comparison_output}")
    print(f"Summary: {args.summary_output}")


if __name__ == "__main__":
    main()
