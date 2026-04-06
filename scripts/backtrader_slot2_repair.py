"""
Focused slot-2 repair search around the best 4-pair realistic near-miss.

This script locks the three strong pairs from the best 4-pair near-miss,
replaces only slot #2 with standalone ETH survivor candidates, and searches
for a stricter 4-pair outcome with drawdown <= 2.95% and consistency <= 20.
"""

from __future__ import annotations

import argparse
import os
from typing import Dict, Iterable, List, Optional, Tuple

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
    build_pair_comparison_rows,
    build_portfolio_summary_row,
    build_shortlist_output,
    load_candidate_pool,
    markdown_table,
    read_shortlist_priority_maps,
)


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

FIXED_SLOT_1_PARAM_ID = "combined__cand_002_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004"
FIXED_SLOT_3_PARAM_ID = "combined__cand_002_AVAX_USDT__4h_ema20_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004"
FIXED_SLOT_4_PARAM_ID = "combined__cand_008_AVAX_USDT__4h_ema15_dist0.008__short_cand_067_DOGE_USDT__4h_ema20_dist0.004"
DEFAULT_WEAK_SLOT_2_PARAM_ID = "combined__cand_028_ETH_USDT__4h_ema15_dist0.000__short_cand_076_ETH_USDT__4h_ema15_dist0.000"

DEFAULT_RESULTS_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_slot2_repair_results.csv")
DEFAULT_SUMMARY_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_slot2_repair_summary.md")
DEFAULT_SURVIVOR_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_final_shortlist_survivor.csv")
DEFAULT_BEST_SHORTLIST_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_slot2_repair_best_shortlist.csv")
DEFAULT_COMPARISON_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_slot2_repair_comparison.csv")
DEFAULT_PAIR_COMPARISON_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_slot2_repair_pair_comparison.csv")


def parse_args() -> argparse.Namespace:
    """Define the CLI surface for the focused slot-2 repair search."""
    parser = argparse.ArgumentParser(description="Repair slot #2 in the best 4-pair realistic near-miss shortlist.")
    parser.add_argument("--candidates", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--ranking", default=DEFAULT_REALISTIC_RANKING_PATH)
    parser.add_argument("--old-shortlist", default=DEFAULT_OLD_SHORTLIST_PATH)
    parser.add_argument("--new-shortlist", default=DEFAULT_REALISTIC_SHORTLIST_PATH)
    parser.add_argument("--daily-data", default=DEFAULT_DAILY_PATH)
    parser.add_argument("--intraday-data", default=DEFAULT_INTRADAY_PATH)
    parser.add_argument("--weak-slot-2-param-id", default=DEFAULT_WEAK_SLOT_2_PARAM_ID)
    parser.add_argument("--strict-dd-threshold", type=float, default=2.95)
    parser.add_argument("--consistency-threshold", type=float, default=20.0)
    parser.add_argument(
        "--replacement-limit",
        type=int,
        default=None,
        help="Optional cap for smoke tests or tighter manual iteration.",
    )
    parser.add_argument("--results-output", default=DEFAULT_RESULTS_OUTPUT)
    parser.add_argument("--summary-output", default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--survivor-output", default=DEFAULT_SURVIVOR_OUTPUT)
    parser.add_argument("--best-shortlist-output", default=DEFAULT_BEST_SHORTLIST_OUTPUT)
    parser.add_argument("--comparison-output", default=DEFAULT_COMPARISON_OUTPUT)
    parser.add_argument("--pair-comparison-output", default=DEFAULT_PAIR_COMPARISON_OUTPUT)
    return parser.parse_args()


def as_bool(value: object) -> bool:
    """Normalize CSV values into booleans."""
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def build_fixed_core_ids(replacement_param_id: str) -> List[str]:
    """Build the ordered 4-pair shortlist with a custom slot-2 replacement."""
    return [
        FIXED_SLOT_1_PARAM_ID,
        str(replacement_param_id),
        FIXED_SLOT_3_PARAM_ID,
        FIXED_SLOT_4_PARAM_ID,
    ]


def strict_target_passes(
    row: Dict[str, object],
    strict_dd_threshold: float,
    consistency_threshold: float,
) -> bool:
    """Apply the stricter target objective requested by the user."""
    return (
        (not as_bool(row.get("breached", True)))
        and (float(row.get("max_dd_pct", 999.0)) <= float(strict_dd_threshold))
        and (float(row.get("consistency_score", 999.0)) <= float(consistency_threshold))
    )


def slot2_sort_key(
    row: Dict[str, object],
    strict_dd_threshold: float,
    consistency_threshold: float,
) -> Tuple[object, ...]:
    """Sort slot-2 repair results under the strict repair objective."""
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
        str(row.get("replacement_param_id", "")),
    )


def choose_best_result(
    rows: Iterable[Dict[str, object]],
    strict_dd_threshold: float,
    consistency_threshold: float,
) -> Dict[str, object]:
    """Select the best slot-2 repair result under the strict objective."""
    records = list(rows)
    if not records:
        raise ValueError("No repair rows were supplied to choose_best_result.")
    return max(
        records,
        key=lambda row: slot2_sort_key(
            row,
            strict_dd_threshold=strict_dd_threshold,
            consistency_threshold=consistency_threshold,
        ),
    )


def build_replacement_candidates(
    realistic_ranking_df: pd.DataFrame,
    weak_slot_2_param_id: str,
    replacement_limit: Optional[int],
) -> pd.DataFrame:
    """Choose standalone ETH survivor candidates for the slot-2 repair sweep."""
    frame = realistic_ranking_df.copy()
    frame = frame.loc[frame["overall_survival"].apply(as_bool)].copy()
    frame = frame.loc[frame["short_source_symbol"].astype(str) == "ETH/USDT"].copy()
    frame = frame.loc[frame["param_id"].astype(str) != str(weak_slot_2_param_id)].copy()
    frame = frame.loc[~frame["param_id"].astype(str).isin([FIXED_SLOT_1_PARAM_ID, FIXED_SLOT_3_PARAM_ID, FIXED_SLOT_4_PARAM_ID])].copy()
    frame = frame.sort_values(
        by=["analysis_rank", "max_dd_pct", "consistency_score", "expectancy", "param_id"],
        ascending=[True, True, True, False, True],
    ).reset_index(drop=True)
    if replacement_limit is not None:
        frame = frame.head(max(0, int(replacement_limit))).reset_index(drop=True)
    return frame


def write_summary_markdown(
    summary_path: str,
    fixed_core_ids: List[str],
    weak_slot_2_param_id: str,
    replacement_candidates_df: pd.DataFrame,
    results_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    pair_comparison_df: pd.DataFrame,
    best_shortlist_df: pd.DataFrame,
    strict_dd_threshold: float,
    consistency_threshold: float,
    survivor_output_written: bool,
) -> None:
    """Write the slot-2 repair summary markdown."""
    best_row = results_df.iloc[0].to_dict()
    strict_survivor_count = int(results_df["strict_target_pass"].astype(int).sum()) if not results_df.empty else 0

    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write("# Backtrader slot-2 repair summary\n\n")
        handle.write(f"- **fixed_core_slot_1**: {fixed_core_ids[0]}\n")
        handle.write(f"- **fixed_core_slot_3**: {fixed_core_ids[1]}\n")
        handle.write(f"- **fixed_core_slot_4**: {fixed_core_ids[2]}\n")
        handle.write(f"- **replaced_weak_slot_2**: {weak_slot_2_param_id}\n")
        handle.write(f"- **slot_2_replacements_tested**: {len(results_df)}\n")
        handle.write(f"- **strict_dd_threshold**: {strict_dd_threshold:.4f}\n")
        handle.write(f"- **consistency_threshold**: {consistency_threshold:.4f}\n")
        handle.write(f"- **strict_target_survivors_found**: {strict_survivor_count}\n")
        handle.write(f"- **selected_replacement**: {best_row['replacement_param_id']}\n")
        handle.write(f"- **survivor_output_written**: {survivor_output_written}\n")

        handle.write("\n## Portfolio Comparison\n\n")
        handle.write(markdown_table(comparison_df))

        handle.write("\n## Replacement Candidates\n\n")
        candidate_display = replacement_candidates_df[
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

        handle.write("\n## Selected Shortlist\n\n")
        shortlist_display = best_shortlist_df[
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

        handle.write("\n## Pair Comparison\n\n")
        pair_display = pair_comparison_df[
            [
                "portfolio_label",
                "shortlist_priority",
                "param_id",
                "standalone_expectancy",
                "standalone_max_dd_pct",
                "standalone_overall_survival",
                "realized_pair_total_profit",
                "stacking_impact_proxy_avg_support_pair_count",
            ]
        ].copy()
        handle.write(markdown_table(pair_display))

        handle.write("\n## Repair Results\n\n")
        results_display = results_df[
            [
                "replacement_param_id",
                "strict_target_pass",
                "overall_survival",
                "expectancy",
                "penalized_expectancy",
                "total_profit",
                "max_dd_pct",
                "consistency_score",
                "diversity_penalty",
                "stacked_same_side_entries",
            ]
        ].copy()
        handle.write(markdown_table(results_display))


def main() -> None:
    """Run the focused slot-2 repair search."""
    args = parse_args()

    candidate_pool_df = load_candidate_pool(candidates_path=args.candidates, ranking_path=args.ranking)
    realistic_ranking_df = pd.read_csv(args.ranking)
    realistic_pair_lookup = {str(row["param_id"]): row.to_dict() for _, row in realistic_ranking_df.iterrows()}
    candidate_lookup = build_candidate_lookup(candidate_pool_df)

    replacement_candidates_df = build_replacement_candidates(
        realistic_ranking_df=realistic_ranking_df,
        weak_slot_2_param_id=args.weak_slot_2_param_id,
        replacement_limit=args.replacement_limit,
    )
    if replacement_candidates_df.empty:
        raise ValueError("No standalone ETH survivor replacements were found for slot #2.")

    old_ids, old_role_lookup, old_rationale_lookup = read_shortlist_priority_maps(args.old_shortlist, top_n=5)
    new_ids, new_role_lookup, new_rationale_lookup = read_shortlist_priority_maps(args.new_shortlist, top_n=5)

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
    for _, replacement_row in replacement_candidates_df.iterrows():
        replacement_param_id = str(replacement_row["param_id"])
        ordered_ids = build_fixed_core_ids(replacement_param_id)
        record = evaluator.evaluate(ordered_ids, stage_label="slot2_repair")
        record["replacement_param_id"] = replacement_param_id
        record["replacement_analysis_rank"] = int(replacement_row["analysis_rank"])
        record["replacement_standalone_expectancy"] = float(replacement_row["expectancy"])
        record["replacement_standalone_max_dd_pct"] = float(replacement_row["max_dd_pct"])
        record["replacement_standalone_consistency_score"] = float(replacement_row["consistency_score"])
        record["strict_target_pass"] = bool(
            strict_target_passes(
                record,
                strict_dd_threshold=args.strict_dd_threshold,
                consistency_threshold=args.consistency_threshold,
            )
        )
        rows.append(record)

    results_df = pd.DataFrame(
        sorted(
            rows,
            key=lambda row: slot2_sort_key(
                row,
                strict_dd_threshold=args.strict_dd_threshold,
                consistency_threshold=args.consistency_threshold,
            ),
            reverse=True,
        )
    )
    results_df.to_csv(args.results_output, index=False)

    best_row = choose_best_result(
        rows,
        strict_dd_threshold=args.strict_dd_threshold,
        consistency_threshold=args.consistency_threshold,
    )
    best_ids = build_fixed_core_ids(best_row["replacement_param_id"])
    best_detail = evaluator.evaluate_with_details(best_ids, stage_label="slot2_repair_best")

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

    best_shortlist_df = build_shortlist_output(
        ordered_ids=best_ids,
        realistic_lookup=realistic_pair_lookup,
        best_portfolio_record=best_detail["metrics"],
    )
    best_shortlist_df.to_csv(args.best_shortlist_output, index=False)

    survivor_output_written = bool(best_row["strict_target_pass"])
    if survivor_output_written:
        best_shortlist_df.to_csv(args.survivor_output, index=False)

    comparison_df = pd.DataFrame(
        [
            build_portfolio_summary_row("old_shortlist", old_ids, old_detail["metrics"]),
            build_portfolio_summary_row("new_realistic_shortlist", new_ids, new_detail["metrics"]),
            build_portfolio_summary_row("slot2_repair_best", best_ids, best_detail["metrics"]),
        ]
    )
    comparison_df.to_csv(args.comparison_output, index=False)

    pair_comparison_df = pd.DataFrame(
        build_pair_comparison_rows("old_shortlist", old_detail, realistic_pair_lookup)
        + build_pair_comparison_rows("new_realistic_shortlist", new_detail, realistic_pair_lookup)
        + build_pair_comparison_rows("slot2_repair_best", best_detail, realistic_pair_lookup)
    ).sort_values(["portfolio_label", "shortlist_priority"]).reset_index(drop=True)
    pair_comparison_df.to_csv(args.pair_comparison_output, index=False)

    write_summary_markdown(
        summary_path=args.summary_output,
        fixed_core_ids=[FIXED_SLOT_1_PARAM_ID, FIXED_SLOT_3_PARAM_ID, FIXED_SLOT_4_PARAM_ID],
        weak_slot_2_param_id=args.weak_slot_2_param_id,
        replacement_candidates_df=replacement_candidates_df,
        results_df=results_df,
        comparison_df=comparison_df,
        pair_comparison_df=pair_comparison_df,
        best_shortlist_df=best_shortlist_df,
        strict_dd_threshold=args.strict_dd_threshold,
        consistency_threshold=args.consistency_threshold,
        survivor_output_written=survivor_output_written,
    )

    print(f"Repair results: {args.results_output}")
    print(f"Best shortlist: {args.best_shortlist_output}")
    if survivor_output_written:
        print(f"True survivor shortlist: {args.survivor_output}")
    print(f"Comparison: {args.comparison_output}")
    print(f"Pair comparison: {args.pair_comparison_output}")
    print(f"Summary: {args.summary_output}")


if __name__ == "__main__":
    main()
