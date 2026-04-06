"""
Exhaustive priority-order search for one fixed 5-pair shortlist under the
corrected realistic full-portfolio engine.

Why this exists:
- shortlist priority changes execution when multiple pairs compete for the same
  symbol or concurrency budget,
- some near-miss realistic portfolios fail Maven by a tiny drawdown margin, and
- reordering the same 5 members is much cheaper than changing the membership.
"""

from __future__ import annotations

import argparse
import gc
import itertools
import os
from typing import Dict, List, Optional, Tuple

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
    DEFAULT_REALISTIC_RANKING_PATH,
    RealisticPortfolioEvaluator,
    build_candidate_lookup,
    build_pair_comparison_rows,
    build_portfolio_summary_row,
    build_shortlist_output,
    load_candidate_pool,
    markdown_table,
    objective_sort_key,
    sort_portfolio_frame,
)


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

DEFAULT_ORDERING_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_order_permutations.csv")
DEFAULT_BEST_SHORTLIST_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_order_permutations_best_shortlist.csv")
DEFAULT_COMPARISON_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_order_permutations_comparison.csv")
DEFAULT_SUMMARY_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_order_permutations_summary.md")


def parse_args() -> argparse.Namespace:
    """Define the CLI surface for ordering-only realistic search."""
    parser = argparse.ArgumentParser(description="Exhaustively search priority orderings for one fixed realistic 5-pair set.")
    parser.add_argument("--candidates", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--ranking", default=DEFAULT_REALISTIC_RANKING_PATH)
    parser.add_argument("--daily-data", default=DEFAULT_DAILY_PATH)
    parser.add_argument("--intraday-data", default=DEFAULT_INTRADAY_PATH)
    parser.add_argument(
        "--portfolio-param-ids",
        required=True,
        help="Pipe-separated 5-pair membership list. Example: a|b|c|d|e",
    )
    parser.add_argument("--ordering-output", default=DEFAULT_ORDERING_OUTPUT)
    parser.add_argument("--best-shortlist-output", default=DEFAULT_BEST_SHORTLIST_OUTPUT)
    parser.add_argument("--comparison-output", default=DEFAULT_COMPARISON_OUTPUT)
    parser.add_argument("--summary-output", default=DEFAULT_SUMMARY_OUTPUT)
    return parser.parse_args()


def parse_portfolio_ids(raw_value: str) -> List[str]:
    """Split the incoming pipe-separated param-id payload."""
    ordered_ids = [item.strip() for item in str(raw_value).split("|") if str(item).strip()]
    unique_ids = list(dict.fromkeys(ordered_ids))
    if len(unique_ids) != len(ordered_ids):
        raise ValueError("Duplicate param_ids were supplied to --portfolio-param-ids.")
    if len(ordered_ids) != 5:
        raise ValueError(f"--portfolio-param-ids must contain exactly 5 ids; received {len(ordered_ids)}.")
    return ordered_ids


def write_summary_markdown(
    summary_path: str,
    seed_ids: List[str],
    best_ids: List[str],
    results_df: pd.DataFrame,
    best_summary_df: pd.DataFrame,
    seed_summary_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
) -> None:
    """Write the markdown summary for the exhaustive ordering search."""
    survivor_count = int(results_df["overall_survival"].sum()) if not results_df.empty else 0
    low_dd_count = int((results_df["max_dd_pct"] < 3.0).sum()) if not results_df.empty else 0

    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write("# Backtrader realistic ordering search summary\n\n")
        handle.write(f"- **seed_membership**: {' | '.join(seed_ids)}\n")
        handle.write(f"- **permutations_tested**: {len(results_df)}\n")
        handle.write(f"- **surviving_permutations**: {survivor_count}\n")
        handle.write(f"- **sub_3pct_drawdown_permutations**: {low_dd_count}\n")
        handle.write(f"- **best_ordering**: {' | '.join(best_ids)}\n")

        handle.write("\n## Seed Vs Best Ordering\n\n")
        handle.write(markdown_table(pd.concat([seed_summary_df, best_summary_df], ignore_index=True)))

        handle.write("\n## Best Ordering Pair Table\n\n")
        handle.write(markdown_table(comparison_df))

        handle.write("\n## Top Ordering Results\n\n")
        display = results_df[
            [
                "portfolio_param_ids",
                "overall_survival",
                "penalized_expectancy",
                "expectancy",
                "max_dd_pct",
                "consistency_score",
                "diversity_penalty",
            ]
        ].head(15)
        handle.write(markdown_table(display))


def main() -> None:
    """Run the exhaustive priority-ordering search for one fixed 5-pair set."""
    args = parse_args()
    seed_ids = parse_portfolio_ids(args.portfolio_param_ids)

    candidate_pool_df = load_candidate_pool(candidates_path=args.candidates, ranking_path=args.ranking)
    realistic_ranking_df = pd.read_csv(args.ranking)
    realistic_pair_lookup = {str(row["param_id"]): row.to_dict() for _, row in realistic_ranking_df.iterrows()}
    candidate_lookup = build_candidate_lookup(candidate_pool_df)

    for param_id in seed_ids:
        if param_id not in candidate_lookup:
            raise KeyError(f"param_id not found in candidate pool: {param_id}")
        if param_id not in realistic_pair_lookup:
            raise KeyError(f"param_id not found in ranking metadata: {param_id}")

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

    rows: List[Dict[str, object]] = []
    permutations = list(itertools.permutations(seed_ids, len(seed_ids)))
    progress = tqdm(permutations, desc="Ordering search", unit="perm")
    for perm in progress:
        ordered_ids = list(perm)
        record = evaluator.evaluate(ordered_ids, stage_label="ordering_search")
        rows.append(record)
        progress.set_postfix(
            survive=int(bool(record["overall_survival"])),
            dd=f"{float(record['max_dd_pct']):.4f}",
            exp=f"{float(record['expectancy']):.4f}",
        )
        gc.collect()

    results_df = sort_portfolio_frame(pd.DataFrame(rows)).drop_duplicates(subset=["portfolio_param_ids"], keep="first")
    results_df.to_csv(args.ordering_output, index=False)

    best_row = max(results_df.to_dict(orient="records"), key=objective_sort_key)
    best_ids = [str(best_row[f"priority_{priority}_param_id"]) for priority in range(1, 6)]

    best_detail = evaluator.evaluate_with_details(best_ids, stage_label="ordering_best")
    seed_detail = evaluator.evaluate_with_details(seed_ids, stage_label="ordering_seed")

    best_shortlist_df = build_shortlist_output(
        ordered_ids=best_ids,
        realistic_lookup=realistic_pair_lookup,
        best_portfolio_record=best_detail["metrics"],
    )
    best_shortlist_df.to_csv(args.best_shortlist_output, index=False)

    comparison_df = pd.DataFrame(
        build_pair_comparison_rows(
            portfolio_label="best_ordering",
            detail_payload=best_detail,
            realistic_lookup=realistic_pair_lookup,
        )
    ).sort_values("shortlist_priority").reset_index(drop=True)
    comparison_df.to_csv(args.comparison_output, index=False)

    seed_summary_df = pd.DataFrame([build_portfolio_summary_row("seed_ordering", seed_ids, seed_detail["metrics"])])
    best_summary_df = pd.DataFrame([build_portfolio_summary_row("best_ordering", best_ids, best_detail["metrics"])])
    write_summary_markdown(
        summary_path=args.summary_output,
        seed_ids=seed_ids,
        best_ids=best_ids,
        results_df=results_df,
        best_summary_df=best_summary_df,
        seed_summary_df=seed_summary_df,
        comparison_df=comparison_df,
    )

    print(f"Ordering results: {args.ordering_output}")
    print(f"Best shortlist: {args.best_shortlist_output}")
    print(f"Comparison: {args.comparison_output}")
    print(f"Summary: {args.summary_output}")


if __name__ == "__main__":
    main()
