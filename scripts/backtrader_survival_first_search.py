"""
Focused survival-first search around the closest realistic near-miss portfolios.

This script starts from the best 4-pair and 5-pair realistic near-miss states,
tests every ordering for those memberships, expands the strongest ordered states
with one-swap neighbors, and then runs a bounded two-swap search around the
best local candidates.

The primary goal is to find the first realistic Maven survivor under the full
34-month Backtrader portfolio engine. If no survivor is found, the script
reports the absolute closest near-miss by lowest drawdown.
"""

from __future__ import annotations

import argparse
import gc
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
    DEFAULT_PORTFOLIO_SEARCH_PATH,
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

DEFAULT_RESULTS_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_survival_search_results.csv")
DEFAULT_SHORTLIST_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_final_shortlist_survivor.csv")
DEFAULT_COMPARISON_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_survival_search_comparison.csv")
DEFAULT_PAIR_COMPARISON_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_survival_search_pair_comparison.csv")
DEFAULT_SUMMARY_OUTPUT = os.path.join(RESULTS_DIR, "backtrader_combined_survival_search_summary.md")


def parse_args() -> argparse.Namespace:
    """Define the CLI surface for the focused survival-first search."""
    parser = argparse.ArgumentParser(
        description="Run a targeted survival-first Backtrader search around realistic near-miss portfolios."
    )
    parser.add_argument("--candidates", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--ranking", default=DEFAULT_REALISTIC_RANKING_PATH)
    parser.add_argument("--portfolio-search", default=DEFAULT_PORTFOLIO_SEARCH_PATH)
    parser.add_argument("--old-shortlist", default=DEFAULT_OLD_SHORTLIST_PATH)
    parser.add_argument("--new-shortlist", default=DEFAULT_REALISTIC_SHORTLIST_PATH)
    parser.add_argument("--daily-data", default=DEFAULT_DAILY_PATH)
    parser.add_argument("--intraday-data", default=DEFAULT_INTRADAY_PATH)
    parser.add_argument(
        "--search-sizes",
        default="4,5",
        help="Comma-separated shortlist sizes to search in order. Example: 4,5",
    )
    parser.add_argument(
        "--seed-limit-per-size",
        type=int,
        default=2,
        help="How many unique near-miss memberships to seed per search size.",
    )
    parser.add_argument(
        "--ordering-beam-width",
        type=int,
        default=1,
        help="How many best ordered variants per seed should feed the swap stages.",
    )
    parser.add_argument(
        "--replacement-pool-size",
        type=int,
        default=5,
        help="How many focused replacement candidates to consider in the one-swap stage.",
    )
    parser.add_argument(
        "--two-swap-source-limit",
        type=int,
        default=1,
        help="How many best local non-survivor states per seed should feed the two-swap stage.",
    )
    parser.add_argument(
        "--two-swap-replacement-pool-size",
        type=int,
        default=3,
        help="How many focused replacement candidates to consider in the two-swap stage.",
    )
    parser.add_argument(
        "--max-orderings-per-seed",
        type=int,
        default=None,
        help="Optional cap used only for smoke tests or fast local iteration.",
    )
    parser.add_argument(
        "--max-one-swap-trials-per-source",
        type=int,
        default=None,
        help="Optional cap used only for smoke tests or fast local iteration.",
    )
    parser.add_argument(
        "--max-two-swap-trials-per-source",
        type=int,
        default=None,
        help="Optional cap used only for smoke tests or fast local iteration.",
    )
    parser.add_argument(
        "--continue-after-survivor",
        action="store_true",
        help="Keep searching even after the first survivor is found.",
    )
    parser.add_argument("--results-output", default=DEFAULT_RESULTS_OUTPUT)
    parser.add_argument("--shortlist-output", default=DEFAULT_SHORTLIST_OUTPUT)
    parser.add_argument("--comparison-output", default=DEFAULT_COMPARISON_OUTPUT)
    parser.add_argument("--pair-comparison-output", default=DEFAULT_PAIR_COMPARISON_OUTPUT)
    parser.add_argument("--summary-output", default=DEFAULT_SUMMARY_OUTPUT)
    return parser.parse_args()


def parse_search_sizes(raw_value: str) -> List[int]:
    """Parse and validate the requested shortlist sizes."""
    values = [item.strip() for item in str(raw_value).split(",") if item.strip()]
    sizes = [int(item) for item in values]
    if not sizes:
        raise ValueError("At least one search size must be supplied.")
    for size in sizes:
        if size < 1 or size > 5:
            raise ValueError(f"Search size must be between 1 and 5; received {size}.")
    return sizes


def as_bool(value: object) -> bool:
    """Normalize CSV values into booleans."""
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def portfolio_param_ids_to_list(raw_value: object) -> List[str]:
    """Split one pipe-separated portfolio id payload into ordered ids."""
    return [item.strip() for item in str(raw_value).split("|") if item.strip()]


def membership_key(ordered_ids: Sequence[str]) -> Tuple[str, ...]:
    """Collapse one portfolio into its unordered membership key."""
    return tuple(sorted(str(item) for item in ordered_ids))


def prioritized_portfolio_key(row: Dict[str, object]) -> Tuple[object, ...]:
    """Sort realistic portfolios for survival-first search and reporting."""
    max_dd_pct = float(row.get("max_dd_pct", 999.0))
    consistency_score = float(row.get("consistency_score", 999.0))
    priority_ids = [str(row.get(f"priority_{index}_param_id", "")) for index in range(1, 6)]
    return (
        int(as_bool(row.get("overall_survival", False))),
        int(not as_bool(row.get("breached", True))),
        int(max_dd_pct <= 3.0),
        int(consistency_score <= 20.0),
        -max_dd_pct,
        -consistency_score,
        float(row.get("penalized_expectancy", row.get("expectancy", 0.0))),
        float(row.get("expectancy", 0.0)),
        float(row.get("total_profit", 0.0)),
        -float(row.get("diversity_penalty", 999.0)),
        int(row.get("portfolio_size", 0)),
        "|".join(priority_ids),
    )


def sort_portfolio_records(rows: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    """Return portfolio records in deterministic survival-first order."""
    return sorted(list(rows), key=prioritized_portfolio_key, reverse=True)


def sort_portfolio_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Sort a portfolio frame under the survival-first objective."""
    if frame.empty:
        return frame
    return pd.DataFrame(sort_portfolio_records(frame.to_dict(orient="records")))


def choose_best_portfolio_record(rows: Iterable[Dict[str, object]]) -> Dict[str, object]:
    """Select the best portfolio row under the survival-first objective."""
    records = list(rows)
    if not records:
        raise ValueError("No portfolio records were supplied to choose_best_portfolio_record.")
    return sort_portfolio_records(records)[0]


def choose_closest_near_miss(rows: Iterable[Dict[str, object]]) -> Dict[str, object]:
    """Select the closest realistic near-miss by absolute lowest drawdown."""
    records = [row for row in rows if not as_bool(row.get("overall_survival", False))]
    if not records:
        raise ValueError("No near-miss rows were supplied to choose_closest_near_miss.")
    return sorted(
        records,
        key=lambda row: (
            float(row.get("max_dd_pct", 999.0)),
            float(row.get("consistency_score", 999.0)),
            -float(row.get("penalized_expectancy", row.get("expectancy", 0.0))),
            -float(row.get("expectancy", 0.0)),
            float(row.get("diversity_penalty", 999.0)),
            str(row.get("portfolio_param_ids", "")),
        ),
    )[0]


def sorted_candidate_ids_for_survival(realistic_ranking_df: pd.DataFrame) -> List[str]:
    """Prioritize standalone candidates by survival-first standalone quality."""
    ordered = realistic_ranking_df.sort_values(
        by=[
            "overall_survival",
            "max_dd_pct",
            "consistency_score",
            "survival_probability_proxy",
            "composite_score",
            "expectancy",
            "analysis_rank",
            "param_id",
        ],
        ascending=[False, True, True, False, False, False, True, True],
    ).reset_index(drop=True)
    return [str(value) for value in ordered["param_id"].tolist()]


def build_seed_replacement_priority(
    portfolio_search_df: pd.DataFrame,
    realistic_ranking_df: pd.DataFrame,
    seed_memberships: List[List[str]],
    old_ids: List[str],
    new_ids: List[str],
) -> List[str]:
    """Build one focused replacement priority list near the realistic frontier."""
    prioritized_ids: List[str] = []

    for ids in seed_memberships:
        prioritized_ids.extend(ids)
    prioritized_ids.extend(new_ids)
    prioritized_ids.extend(old_ids)

    ranked_portfolios = sort_portfolio_frame(portfolio_search_df.copy())
    for _, row in ranked_portfolios.head(25).iterrows():
        prioritized_ids.extend(portfolio_param_ids_to_list(row["portfolio_param_ids"]))

    prioritized_ids.extend(sorted_candidate_ids_for_survival(realistic_ranking_df))
    return list(dict.fromkeys(str(value) for value in prioritized_ids))


def extract_seed_memberships(
    portfolio_search_df: pd.DataFrame,
    search_size: int,
    seed_limit_per_size: int,
) -> List[List[str]]:
    """Choose the best unique near-miss memberships for one search size."""
    size_df = portfolio_search_df.loc[portfolio_search_df["portfolio_size"] == search_size].copy()
    if size_df.empty:
        return []

    rows = sort_portfolio_records(size_df.to_dict(orient="records"))
    selected: List[List[str]] = []
    seen_memberships = set()

    for row in rows:
        ordered_ids = portfolio_param_ids_to_list(row["portfolio_param_ids"])
        if len(ordered_ids) != search_size:
            continue
        key = membership_key(ordered_ids)
        if key in seen_memberships:
            continue
        selected.append(ordered_ids)
        seen_memberships.add(key)
        if len(selected) >= seed_limit_per_size:
            break
    return selected


def evaluate_orderings_for_seed(
    seed_ids: List[str],
    seed_label: str,
    evaluator: RealisticPortfolioEvaluator,
    max_orderings_per_seed: Optional[int],
) -> pd.DataFrame:
    """Evaluate every reasonable ordering for one fixed membership seed."""
    permutations = list(itertools.permutations(seed_ids, len(seed_ids)))
    if max_orderings_per_seed is not None:
        permutations = permutations[: max(0, int(max_orderings_per_seed))]

    rows: List[Dict[str, object]] = []
    progress = tqdm(permutations, desc=f"Ordering {seed_label}", unit="ordering")
    for ordered_ids in progress:
        record = evaluator.evaluate(list(ordered_ids), stage_label=f"{seed_label}_ordering")
        rows.append(record)
        progress.set_postfix(
            survive=int(as_bool(record["overall_survival"])),
            dd=f"{float(record['max_dd_pct']):.4f}",
            exp=f"{float(record['expectancy']):.4f}",
        )
    progress.close()

    results_df = sort_portfolio_frame(pd.DataFrame(rows))
    if results_df.empty:
        return results_df
    return results_df.drop_duplicates(subset=["portfolio_param_ids"], keep="first").reset_index(drop=True)


def evaluate_one_swap_neighbors(
    source_ids: List[str],
    seed_label: str,
    source_label: str,
    replacement_priority: List[str],
    replacement_pool_size: int,
    evaluator: RealisticPortfolioEvaluator,
    max_trials_per_source: Optional[int],
) -> pd.DataFrame:
    """Evaluate deterministic one-swap neighbors around one ordered source."""
    replacement_ids = [param_id for param_id in replacement_priority if param_id not in source_ids][:replacement_pool_size]
    rows: List[Dict[str, object]] = []

    source_record = evaluator.evaluate(source_ids, stage_label=f"{seed_label}_{source_label}_one_swap_seed")
    rows.append(source_record)

    trials: List[Tuple[int, str]] = []
    for slot_index in range(len(source_ids)):
        for replacement_id in replacement_ids:
            trials.append((slot_index, replacement_id))
    if max_trials_per_source is not None:
        trials = trials[: max(0, int(max_trials_per_source))]

    progress = tqdm(trials, desc=f"1-swap {seed_label} {source_label}", unit="portfolio")
    for slot_index, replacement_id in progress:
        trial_ids = list(source_ids)
        trial_ids[slot_index] = replacement_id
        if len(set(trial_ids)) != len(trial_ids):
            continue
        record = evaluator.evaluate(trial_ids, stage_label=f"{seed_label}_{source_label}_one_swap")
        rows.append(record)
        progress.set_postfix(
            survive=int(as_bool(record["overall_survival"])),
            dd=f"{float(record['max_dd_pct']):.4f}",
            exp=f"{float(record['expectancy']):.4f}",
        )
        gc.collect()
    progress.close()

    results_df = sort_portfolio_frame(pd.DataFrame(rows))
    if results_df.empty:
        return results_df
    return results_df.drop_duplicates(subset=["portfolio_param_ids"], keep="first").reset_index(drop=True)


def evaluate_two_swap_neighbors(
    source_ids: List[str],
    seed_label: str,
    source_label: str,
    replacement_priority: List[str],
    replacement_pool_size: int,
    evaluator: RealisticPortfolioEvaluator,
    max_trials_per_source: Optional[int],
) -> pd.DataFrame:
    """Evaluate deterministic bounded two-swap neighbors around one ordered source."""
    replacement_ids = [param_id for param_id in replacement_priority if param_id not in source_ids][:replacement_pool_size]
    rows: List[Dict[str, object]] = []

    source_record = evaluator.evaluate(source_ids, stage_label=f"{seed_label}_{source_label}_two_swap_seed")
    rows.append(source_record)

    trials: List[Tuple[Tuple[int, int], Tuple[str, str]]] = []
    for slot_pair in itertools.combinations(range(len(source_ids)), 2):
        for replacement_pair in itertools.permutations(replacement_ids, 2):
            trials.append((slot_pair, replacement_pair))
    if max_trials_per_source is not None:
        trials = trials[: max(0, int(max_trials_per_source))]

    progress = tqdm(trials, desc=f"2-swap {seed_label} {source_label}", unit="portfolio")
    for slot_pair, replacement_pair in progress:
        trial_ids = list(source_ids)
        trial_ids[slot_pair[0]] = replacement_pair[0]
        trial_ids[slot_pair[1]] = replacement_pair[1]
        if len(set(trial_ids)) != len(trial_ids):
            continue
        record = evaluator.evaluate(trial_ids, stage_label=f"{seed_label}_{source_label}_two_swap")
        rows.append(record)
        progress.set_postfix(
            survive=int(as_bool(record["overall_survival"])),
            dd=f"{float(record['max_dd_pct']):.4f}",
            exp=f"{float(record['expectancy']):.4f}",
        )
        gc.collect()
    progress.close()

    results_df = sort_portfolio_frame(pd.DataFrame(rows))
    if results_df.empty:
        return results_df
    return results_df.drop_duplicates(subset=["portfolio_param_ids"], keep="first").reset_index(drop=True)


def first_survivor_record(frame: pd.DataFrame) -> Optional[Dict[str, object]]:
    """Return the best survivor in one search frame if any exists."""
    if frame.empty:
        return None
    survivor_df = frame.loc[frame["overall_survival"].astype(str).str.lower() == "true"].copy()
    if survivor_df.empty:
        return None
    return choose_best_portfolio_record(survivor_df.to_dict(orient="records"))


def build_selected_ids(selected_row: Dict[str, object]) -> List[str]:
    """Extract the ordered shortlist ids from one selected portfolio row."""
    portfolio_size = int(selected_row.get("portfolio_size", 0))
    return [str(selected_row[f"priority_{priority}_param_id"]) for priority in range(1, portfolio_size + 1)]


def build_search_config_rows(args: argparse.Namespace, search_sizes: List[int]) -> pd.DataFrame:
    """Render the main search configuration into a flat table."""
    return pd.DataFrame(
        [
            {"setting": "search_sizes", "value": ",".join(str(value) for value in search_sizes)},
            {"setting": "seed_limit_per_size", "value": int(args.seed_limit_per_size)},
            {"setting": "ordering_beam_width", "value": int(args.ordering_beam_width)},
            {"setting": "replacement_pool_size", "value": int(args.replacement_pool_size)},
            {"setting": "two_swap_source_limit", "value": int(args.two_swap_source_limit)},
            {"setting": "two_swap_replacement_pool_size", "value": int(args.two_swap_replacement_pool_size)},
            {"setting": "continue_after_survivor", "value": bool(args.continue_after_survivor)},
            {"setting": "max_orderings_per_seed", "value": args.max_orderings_per_seed},
            {"setting": "max_one_swap_trials_per_source", "value": args.max_one_swap_trials_per_source},
            {"setting": "max_two_swap_trials_per_source", "value": args.max_two_swap_trials_per_source},
        ]
    )


def write_summary_markdown(
    summary_path: str,
    search_config_df: pd.DataFrame,
    selected_label: str,
    selected_ids: List[str],
    survivor_found: bool,
    results_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    pair_comparison_df: pd.DataFrame,
    shortlist_df: pd.DataFrame,
    selected_summary_df: pd.DataFrame,
) -> None:
    """Write the focused survival-search summary markdown."""
    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write("# Backtrader survival-first search summary\n\n")
        handle.write(f"- **selected_result_label**: {selected_label}\n")
        handle.write(f"- **survivor_found**: {survivor_found}\n")
        handle.write(f"- **selected_portfolio**: {' | '.join(selected_ids)}\n")
        handle.write(f"- **unique_portfolios_evaluated**: {len(results_df)}\n")
        searched_survivor_count = (
            int(results_df["overall_survival"].astype(str).str.lower().eq("true").sum()) if not results_df.empty else 0
        )
        handle.write(f"- **searched_survivors_found**: {searched_survivor_count}\n")

        handle.write("\n## Search Config\n\n")
        handle.write(markdown_table(search_config_df))

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

        handle.write("\n## Top Search Results\n\n")
        search_display = results_df[
            [
                "portfolio_param_ids",
                "portfolio_size",
                "overall_survival",
                "penalized_expectancy",
                "expectancy",
                "max_dd_pct",
                "consistency_score",
                "diversity_penalty",
                "first_seen_stage",
            ]
        ].head(20)
        handle.write(markdown_table(search_display))


def main() -> None:
    """Run the targeted survival-first search around realistic near-miss portfolios."""
    args = parse_args()
    search_sizes = parse_search_sizes(args.search_sizes)

    candidate_pool_df = load_candidate_pool(candidates_path=args.candidates, ranking_path=args.ranking)
    realistic_ranking_df = pd.read_csv(args.ranking)
    portfolio_search_df = pd.read_csv(args.portfolio_search)

    realistic_pair_lookup = {str(row["param_id"]): row.to_dict() for _, row in realistic_ranking_df.iterrows()}
    candidate_lookup = build_candidate_lookup(candidate_pool_df)

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

    seed_memberships: List[List[str]] = []
    for search_size in search_sizes:
        seed_memberships.extend(
            extract_seed_memberships(
                portfolio_search_df=portfolio_search_df,
                search_size=search_size,
                seed_limit_per_size=args.seed_limit_per_size,
            )
        )
    if not seed_memberships:
        raise ValueError("No seed memberships were found in the realistic portfolio search results.")

    replacement_priority = build_seed_replacement_priority(
        portfolio_search_df=portfolio_search_df,
        realistic_ranking_df=realistic_ranking_df,
        seed_memberships=seed_memberships,
        old_ids=old_ids,
        new_ids=new_ids,
    )

    selected_row: Optional[Dict[str, object]] = None

    for search_size in search_sizes:
        size_seeds = [ids for ids in seed_memberships if len(ids) == search_size]
        for seed_index, seed_ids in enumerate(size_seeds, start=1):
            seed_label = f"size_{search_size}_seed_{seed_index:02d}"

            ordering_df = evaluate_orderings_for_seed(
                seed_ids=seed_ids,
                seed_label=seed_label,
                evaluator=evaluator,
                max_orderings_per_seed=args.max_orderings_per_seed,
            )
            survivor_row = first_survivor_record(ordering_df)
            if survivor_row is not None:
                selected_row = survivor_row
                if not args.continue_after_survivor:
                    break

            local_frames = [ordering_df]
            ordering_sources = ordering_df.head(max(1, int(args.ordering_beam_width)))
            for source_rank, (_, source_row) in enumerate(ordering_sources.iterrows(), start=1):
                source_ids = build_selected_ids(source_row.to_dict())
                source_label = f"ordering_{source_rank:02d}"

                one_swap_df = evaluate_one_swap_neighbors(
                    source_ids=source_ids,
                    seed_label=seed_label,
                    source_label=source_label,
                    replacement_priority=replacement_priority,
                    replacement_pool_size=args.replacement_pool_size,
                    evaluator=evaluator,
                    max_trials_per_source=args.max_one_swap_trials_per_source,
                )
                local_frames.append(one_swap_df)

                survivor_row = first_survivor_record(one_swap_df)
                if survivor_row is not None:
                    selected_row = survivor_row
                    if not args.continue_after_survivor:
                        break

                two_swap_sources = sort_portfolio_frame(pd.concat(local_frames, ignore_index=True)).head(
                    max(0, int(args.two_swap_source_limit))
                )
                for two_swap_rank, (_, two_swap_source_row) in enumerate(two_swap_sources.iterrows(), start=1):
                    two_swap_source_ids = build_selected_ids(two_swap_source_row.to_dict())
                    two_swap_label = f"{source_label}_best_{two_swap_rank:02d}"

                    two_swap_df = evaluate_two_swap_neighbors(
                        source_ids=two_swap_source_ids,
                        seed_label=seed_label,
                        source_label=two_swap_label,
                        replacement_priority=replacement_priority,
                        replacement_pool_size=args.two_swap_replacement_pool_size,
                        evaluator=evaluator,
                        max_trials_per_source=args.max_two_swap_trials_per_source,
                    )
                    local_frames.append(two_swap_df)

                    survivor_row = first_survivor_record(two_swap_df)
                    if survivor_row is not None:
                        selected_row = survivor_row
                        if not args.continue_after_survivor:
                            break

                if selected_row is not None and not args.continue_after_survivor:
                    break

            if selected_row is not None and not args.continue_after_survivor:
                break
        if selected_row is not None and not args.continue_after_survivor:
            break

    results_df = sort_portfolio_frame(evaluator.build_results_frame())
    results_df.to_csv(args.results_output, index=False)

    all_rows = results_df.to_dict(orient="records")
    if selected_row is None:
        selected_row = choose_closest_near_miss(all_rows)

    selected_ids = build_selected_ids(selected_row)
    selected_label = "survival_search_survivor" if as_bool(selected_row["overall_survival"]) else "survival_search_near_miss"

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
    selected_detail = evaluator.evaluate_with_details(selected_ids, stage_label=selected_label)

    shortlist_df = build_shortlist_output(
        ordered_ids=selected_ids,
        realistic_lookup=realistic_pair_lookup,
        best_portfolio_record=selected_detail["metrics"],
    )
    shortlist_df.to_csv(args.shortlist_output, index=False)

    comparison_df = pd.DataFrame(
        [
            build_portfolio_summary_row("old_shortlist", old_ids, old_detail["metrics"]),
            build_portfolio_summary_row("new_realistic_shortlist", new_ids, new_detail["metrics"]),
            build_portfolio_summary_row(selected_label, selected_ids, selected_detail["metrics"]),
        ]
    )
    comparison_df.to_csv(args.comparison_output, index=False)

    pair_comparison_df = pd.DataFrame(
        build_pair_comparison_rows("old_shortlist", old_detail, realistic_pair_lookup)
        + build_pair_comparison_rows("new_realistic_shortlist", new_detail, realistic_pair_lookup)
        + build_pair_comparison_rows(selected_label, selected_detail, realistic_pair_lookup)
    ).sort_values(["portfolio_label", "shortlist_priority"]).reset_index(drop=True)
    pair_comparison_df.to_csv(args.pair_comparison_output, index=False)

    search_config_df = build_search_config_rows(args=args, search_sizes=search_sizes)
    selected_summary_df = pd.DataFrame([build_portfolio_summary_row(selected_label, selected_ids, selected_detail["metrics"])])
    write_summary_markdown(
        summary_path=args.summary_output,
        search_config_df=search_config_df,
        selected_label=selected_label,
        selected_ids=selected_ids,
        survivor_found=bool(as_bool(selected_row["overall_survival"])),
        results_df=results_df,
        comparison_df=comparison_df,
        pair_comparison_df=pair_comparison_df,
        shortlist_df=shortlist_df,
        selected_summary_df=selected_summary_df,
    )

    print(f"Search results: {args.results_output}")
    print(f"Selected shortlist: {args.shortlist_output}")
    print(f"Comparison: {args.comparison_output}")
    print(f"Pair comparison: {args.pair_comparison_output}")
    print(f"Summary: {args.summary_output}")


if __name__ == "__main__":
    main()
