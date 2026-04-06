"""
Focused 3-pair survival search under the corrected full realistic objective.

This script:
1. builds a deterministic 3-pair search pool from the strongest standalone
   realistic survivors,
2. evaluates every 3-pair membership and ordering under the same corrected
   full Backtrader engine used by the realistic re-optimization, and
3. compares the best 3-pair result against the old 5-pair shortlist, the
   new realistic 5-pair shortlist, and the best 4-pair near-miss.
"""

from __future__ import annotations

import argparse
import itertools
import os
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd
from tqdm import tqdm

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

DEFAULT_RESULTS_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_3pair_search_results.csv")
DEFAULT_SUMMARY_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_3pair_survival_summary.md")
DEFAULT_SURVIVOR_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_final_shortlist_survivor.csv")
DEFAULT_COMPARISON_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_3pair_comparison.csv")


def parse_args() -> argparse.Namespace:
    """Define the CLI surface for the focused 3-pair search."""
    parser = argparse.ArgumentParser(
        description="Search deterministic 3-pair realistic portfolios for the first strict Maven survivor."
    )
    parser.add_argument("--candidates", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--ranking", default=DEFAULT_REALISTIC_RANKING_PATH)
    parser.add_argument("--old-shortlist", default=DEFAULT_OLD_SHORTLIST_PATH)
    parser.add_argument("--new-shortlist", default=DEFAULT_REALISTIC_SHORTLIST_PATH)
    parser.add_argument("--four-pair-search-results", default=DEFAULT_FOUR_PAIR_SEARCH_RESULTS)
    parser.add_argument("--daily-data", default=DEFAULT_DAILY_PATH)
    parser.add_argument("--intraday-data", default=DEFAULT_INTRADAY_PATH)
    parser.add_argument(
        "--candidate-pool-size",
        type=int,
        default=None,
        help="Optional cap on the standalone-survivor search pool. Default uses all standalone survivors.",
    )
    parser.add_argument("--strict-dd-threshold", type=float, default=2.95)
    parser.add_argument("--consistency-threshold", type=float, default=20.0)
    parser.add_argument("--results-output", default=DEFAULT_RESULTS_OUTPUT)
    parser.add_argument("--summary-output", default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--survivor-output", default=DEFAULT_SURVIVOR_OUTPUT)
    parser.add_argument("--comparison-output", default=DEFAULT_COMPARISON_OUTPUT)
    return parser.parse_args()


def as_bool(value: object) -> bool:
    """Normalize CSV or metrics payload values into booleans."""
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def portfolio_param_ids_to_list(raw_value: object) -> List[str]:
    """Split one pipe-separated portfolio id payload into ordered ids."""
    return [item.strip() for item in str(raw_value).split("|") if item.strip()]


def build_selected_ids(row: Dict[str, object]) -> List[str]:
    """Extract the ordered shortlist ids from one portfolio row."""
    portfolio_size = int(row.get("portfolio_size", 0))
    return [str(row.get(f"priority_{priority}_param_id", "")) for priority in range(1, portfolio_size + 1)]


def strict_target_passes(
    row: Dict[str, object],
    strict_dd_threshold: float,
    consistency_threshold: float,
) -> bool:
    """Apply the stricter survival filter requested for the 3-pair search."""
    return (
        as_bool(row.get("overall_survival", False))
        and (not as_bool(row.get("breached", True)))
        and (float(row.get("max_dd_pct", 999.0)) <= float(strict_dd_threshold))
        and (float(row.get("consistency_score", 999.0)) <= float(consistency_threshold))
    )


def strict_sort_key(
    row: Dict[str, object],
    strict_dd_threshold: float,
    consistency_threshold: float,
) -> Tuple[object, ...]:
    """Sort 3-pair results under the strict survival-first objective."""
    return (
        int(strict_target_passes(row, strict_dd_threshold=strict_dd_threshold, consistency_threshold=consistency_threshold)),
        int(as_bool(row.get("overall_survival", False))),
        int(not as_bool(row.get("breached", True))),
        -float(row.get("max_dd_pct", 999.0)),
        -float(row.get("consistency_score", 999.0)),
        float(row.get("penalized_expectancy", row.get("expectancy", 0.0))),
        float(row.get("expectancy", 0.0)),
        float(row.get("total_profit", 0.0)),
        -float(row.get("diversity_penalty", 999.0)),
        str(row.get("portfolio_param_ids", "")),
    )


def sort_result_records(
    rows: Iterable[Dict[str, object]],
    strict_dd_threshold: float,
    consistency_threshold: float,
) -> List[Dict[str, object]]:
    """Return result rows in deterministic strict survival-first order."""
    return sorted(
        list(rows),
        key=lambda row: strict_sort_key(
            row,
            strict_dd_threshold=strict_dd_threshold,
            consistency_threshold=consistency_threshold,
        ),
        reverse=True,
    )


def choose_best_result(
    rows: Iterable[Dict[str, object]],
    strict_dd_threshold: float,
    consistency_threshold: float,
) -> Dict[str, object]:
    """Select the best 3-pair result under the strict survival-first objective."""
    records = list(rows)
    if not records:
        raise ValueError("No 3-pair search results were supplied to choose_best_result.")
    return max(
        records,
        key=lambda row: strict_sort_key(
            row,
            strict_dd_threshold=strict_dd_threshold,
            consistency_threshold=consistency_threshold,
        ),
    )


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


def build_three_pair_candidate_pool(
    realistic_ranking_df: pd.DataFrame,
    candidate_pool_size: Optional[int],
) -> pd.DataFrame:
    """Choose the standalone realistic survivor pool used in the exhaustive 3-pair search."""
    frame = realistic_ranking_df.copy()
    frame = frame.loc[frame["overall_survival"].apply(as_bool)].copy()
    frame = frame.sort_values(
        by=[
            "max_dd_pct",
            "consistency_score",
            "analysis_rank",
            "survival_probability_proxy",
            "composite_score",
            "expectancy",
            "param_id",
        ],
        ascending=[True, True, True, False, False, False, True],
    ).reset_index(drop=True)
    if candidate_pool_size is not None:
        frame = frame.head(max(0, int(candidate_pool_size))).reset_index(drop=True)
    if len(frame) < 3:
        raise ValueError("The 3-pair search pool must contain at least 3 standalone survivors.")
    return frame


def evaluate_three_pair_search(
    candidate_ids: Sequence[str],
    evaluator: RealisticPortfolioEvaluator,
    strict_dd_threshold: float,
    consistency_threshold: float,
) -> pd.DataFrame:
    """Evaluate every 3-pair membership and every ordering under the realistic engine."""
    memberships = list(itertools.combinations(candidate_ids, 3))
    total_orderings = len(memberships) * 6
    rows: List[Dict[str, object]] = []

    progress = tqdm(total=total_orderings, desc="3-pair realistic search", unit="portfolio")
    for membership_index, membership_ids in enumerate(memberships, start=1):
        for ordering_index, ordered_ids in enumerate(itertools.permutations(membership_ids, 3), start=1):
            record = evaluator.evaluate(list(ordered_ids), stage_label=f"three_pair_membership_{membership_index:03d}")
            row = dict(record)
            row["membership_index"] = int(membership_index)
            row["ordering_index"] = int(ordering_index)
            row["membership_param_ids"] = "|".join(str(item) for item in membership_ids)
            row["strict_target_pass"] = bool(
                strict_target_passes(
                    row,
                    strict_dd_threshold=strict_dd_threshold,
                    consistency_threshold=consistency_threshold,
                )
            )
            rows.append(row)

            progress.set_postfix(
                strict=int(bool(row["strict_target_pass"])),
                dd=f"{float(row['max_dd_pct']):.4f}",
                exp=f"{float(row['expectancy']):.4f}",
            )
            progress.update(1)
    progress.close()

    return pd.DataFrame(
        sort_result_records(
            rows,
            strict_dd_threshold=strict_dd_threshold,
            consistency_threshold=consistency_threshold,
        )
    )


def write_summary_markdown(
    summary_path: str,
    candidate_pool_df: pd.DataFrame,
    results_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    shortlist_df: pd.DataFrame,
    selected_summary_df: pd.DataFrame,
    strict_dd_threshold: float,
    consistency_threshold: float,
    survivor_output_written: bool,
) -> None:
    """Write the 3-pair search summary markdown."""
    best_row = results_df.iloc[0].to_dict()
    strict_survivor_count = int(results_df["strict_target_pass"].astype(int).sum()) if not results_df.empty else 0
    overall_survivor_count = int(results_df["overall_survival"].apply(as_bool).sum()) if not results_df.empty else 0

    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write("# Backtrader 3-pair survival search summary\n\n")
        handle.write("- **objective**: find a 3-pair realistic portfolio that survives under the stricter drawdown target\n")
        handle.write(f"- **strict_dd_threshold**: {strict_dd_threshold:.4f}\n")
        handle.write(f"- **consistency_threshold**: {consistency_threshold:.4f}\n")
        handle.write(f"- **standalone_survivors_in_search_pool**: {len(candidate_pool_df)}\n")
        handle.write(f"- **three_pair_memberships_tested**: {int(len(results_df) / 6) if not results_df.empty else 0}\n")
        handle.write(f"- **ordered_portfolios_tested**: {len(results_df)}\n")
        handle.write(f"- **strict_target_survivors_found**: {strict_survivor_count}\n")
        handle.write(f"- **overall_survivors_found**: {overall_survivor_count}\n")
        handle.write(f"- **selected_result_label**: {selected_summary_df.iloc[0]['portfolio_label']}\n")
        handle.write(f"- **selected_portfolio**: {best_row['portfolio_param_ids']}\n")
        handle.write(f"- **survivor_output_written**: {survivor_output_written}\n")

        handle.write("\n## Search Pool\n\n")
        candidate_display = candidate_pool_df[
            [
                "analysis_rank",
                "param_id",
                "expectancy",
                "max_dd_pct",
                "consistency_score",
                "survival_probability_proxy",
                "composite_score",
            ]
        ].copy()
        handle.write(markdown_table(candidate_display))

        handle.write("\n## Portfolio Comparison\n\n")
        handle.write(markdown_table(comparison_df))

        handle.write("\n## Selected Result\n\n")
        handle.write(markdown_table(selected_summary_df))

        handle.write("\n## Selected Shortlist\n\n")
        shortlist_display = shortlist_df[
            [
                "shortlist_priority",
                "param_id",
                "long_param_id",
                "short_param_id",
                "expectancy",
                "max_dd_pct",
                "overall_survival",
                "portfolio_penalized_expectancy",
                "portfolio_diversity_penalty",
            ]
        ].copy()
        handle.write(markdown_table(shortlist_display))

        handle.write("\n## Top Search Results\n\n")
        results_display = results_df[
            [
                "portfolio_param_ids",
                "strict_target_pass",
                "overall_survival",
                "expectancy",
                "penalized_expectancy",
                "total_profit",
                "max_dd_pct",
                "consistency_score",
                "diversity_penalty",
                "membership_param_ids",
            ]
        ].head(20)
        handle.write(markdown_table(results_display))


def main() -> None:
    """Run the focused deterministic 3-pair realistic survival search."""
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

    search_pool_df = build_three_pair_candidate_pool(
        realistic_ranking_df=realistic_ranking_df,
        candidate_pool_size=args.candidate_pool_size,
    )
    search_candidate_ids = [str(value) for value in search_pool_df["param_id"].tolist()]

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

    results_df = evaluate_three_pair_search(
        candidate_ids=search_candidate_ids,
        evaluator=evaluator,
        strict_dd_threshold=args.strict_dd_threshold,
        consistency_threshold=args.consistency_threshold,
    )
    results_df.to_csv(args.results_output, index=False)

    best_row = choose_best_result(
        rows=results_df.to_dict(orient="records"),
        strict_dd_threshold=args.strict_dd_threshold,
        consistency_threshold=args.consistency_threshold,
    )
    best_ids = build_selected_ids(best_row)
    best_label = "three_pair_survivor" if as_bool(best_row["strict_target_pass"]) else "three_pair_near_miss"

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
    best_three_pair_detail = evaluator.evaluate_with_details(
        best_ids,
        stage_label=best_label,
    )

    shortlist_df = build_shortlist_output(
        ordered_ids=best_ids,
        realistic_lookup=realistic_pair_lookup,
        best_portfolio_record=best_three_pair_detail["metrics"],
    )

    survivor_output_written = bool(as_bool(best_row["strict_target_pass"]))
    if survivor_output_written:
        shortlist_df.to_csv(args.survivor_output, index=False)

    comparison_df = pd.DataFrame(
        [
            build_portfolio_summary_row("old_5pair_shortlist", old_ids, old_detail["metrics"]),
            build_portfolio_summary_row("new_realistic_5pair_shortlist", new_ids, new_detail["metrics"]),
            build_portfolio_summary_row("best_4pair_near_miss", best_four_pair_ids, best_four_pair_detail["metrics"]),
            build_portfolio_summary_row(best_label, best_ids, best_three_pair_detail["metrics"]),
        ]
    )
    comparison_df.to_csv(args.comparison_output, index=False)

    selected_summary_df = pd.DataFrame(
        [build_portfolio_summary_row(best_label, best_ids, best_three_pair_detail["metrics"])]
    )
    write_summary_markdown(
        summary_path=args.summary_output,
        candidate_pool_df=search_pool_df,
        results_df=results_df,
        comparison_df=comparison_df,
        shortlist_df=shortlist_df,
        selected_summary_df=selected_summary_df,
        strict_dd_threshold=args.strict_dd_threshold,
        consistency_threshold=args.consistency_threshold,
        survivor_output_written=survivor_output_written,
    )

    print(f"3-pair search results: {args.results_output}")
    if survivor_output_written:
        print(f"True survivor shortlist: {args.survivor_output}")
    print(f"Comparison: {args.comparison_output}")
    print(f"Summary: {args.summary_output}")


if __name__ == "__main__":
    main()
