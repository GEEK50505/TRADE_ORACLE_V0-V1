"""
Deterministic re-optimization of the final combined shortlist under the
corrected full realistic portfolio objective.

This script:
1. reranks every combined candidate as a standalone realistic portfolio,
2. searches for a new ordered 5-pair shortlist with deterministic forward
   selection plus swap refinement, and
3. compares the old shortlist against the new realistic shortlist under the
   same corrected baseline rules.
"""

from __future__ import annotations

import argparse
import gc
import math
import os
from typing import Dict, List, Optional, Tuple

import pandas as pd
from tqdm import tqdm

from backtrader_evaluate import (
    DEFAULT_DAILY_PATH,
    DEFAULT_INTRADAY_PATH,
    MarketDataCatalog,
)
from backtrader_evaluate_combined import CombinedCandidateConfig
from backtrader_evaluate_final_portfolio import (
    build_pair_stats,
    build_symbol_stats,
    load_csv,
    markdown_table,
)
from backtrader_evaluate_final_portfolio_full import (
    BASELINE_PRESET_NAME,
    DEFAULT_PRIOR_NETTED_RESULTS,
    FRICTION_PRESETS,
    build_symbol_activation_coverage,
    enrich_metrics,
    load_prior_netted_results,
    run_final_portfolio_full,
    safe_timestamp,
)


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

DEFAULT_CANDIDATES_PATH = os.path.join(RESULTS_DIR, "backtrader_combined_candidates.csv")
DEFAULT_PRIOR_RANKING_PATH = os.path.join(RESULTS_DIR, "backtrader_combined_survivor_ranking.csv")
DEFAULT_OLD_SHORTLIST_PATH = os.path.join(RESULTS_DIR, "backtrader_combined_final_shortlist.csv")

DEFAULT_REALISTIC_RANKING_PATH = os.path.join(RESULTS_DIR, "backtrader_combined_survivor_ranking_realistic.csv")
DEFAULT_REALISTIC_SHORTLIST_PATH = os.path.join(RESULTS_DIR, "backtrader_combined_final_shortlist_realistic.csv")
DEFAULT_PORTFOLIO_SEARCH_PATH = os.path.join(RESULTS_DIR, "backtrader_combined_portfolio_search_realistic.csv")
DEFAULT_COMPARISON_PATH = os.path.join(RESULTS_DIR, "backtrader_combined_realistic_comparison.csv")
DEFAULT_SUMMARY_PATH = os.path.join(RESULTS_DIR, "backtrader_reoptimize_full_realistic_summary.md")


def parse_args() -> argparse.Namespace:
    """Define the CLI surface for the realistic re-optimization pass."""
    parser = argparse.ArgumentParser(
        description="Re-optimize the final combined shortlist under the corrected full realistic Backtrader objective."
    )
    parser.add_argument("--candidates", default=DEFAULT_CANDIDATES_PATH, help="Path to the combined candidate CSV.")
    parser.add_argument(
        "--ranking",
        default=DEFAULT_PRIOR_RANKING_PATH,
        help="Path to the prior combined survivor ranking CSV used as metadata seed.",
    )
    parser.add_argument("--old-shortlist", default=DEFAULT_OLD_SHORTLIST_PATH, help="Path to the prior 5-pair shortlist CSV.")
    parser.add_argument("--daily-data", default=DEFAULT_DAILY_PATH, help="Path to the daily parquet file.")
    parser.add_argument("--intraday-data", default=DEFAULT_INTRADAY_PATH, help="Path to the 4H parquet file.")
    parser.add_argument("--top-n", type=int, default=5, help="How many pairs the final realistic shortlist should contain.")
    parser.add_argument(
        "--swap-rounds",
        type=int,
        default=1,
        help="How many deterministic swap-refinement rounds to run after forward selection.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=None,
        help="Optional cap used only for smoke tests or local iteration.",
    )
    parser.add_argument("--realistic-ranking-output", default=DEFAULT_REALISTIC_RANKING_PATH)
    parser.add_argument("--shortlist-output", default=DEFAULT_REALISTIC_SHORTLIST_PATH)
    parser.add_argument("--portfolio-search-output", default=DEFAULT_PORTFOLIO_SEARCH_PATH)
    parser.add_argument("--comparison-output", default=DEFAULT_COMPARISON_PATH)
    parser.add_argument("--summary-output", default=DEFAULT_SUMMARY_PATH)
    return parser.parse_args()


def default_role_for_priority(priority: int) -> str:
    """Map final shortlist priority onto a short role label."""
    if priority == 1:
        return "primary"
    if priority == 2:
        return "secondary"
    if priority == 3:
        return "throughput_variant"
    if priority == 4:
        return "pair_diversifier"
    return "reserve"


def clip01(value: float) -> float:
    """Clamp any scalar onto the closed 0..1 interval."""
    return max(0.0, min(1.0, float(value)))


def portfolio_key(ordered_ids: List[str]) -> Tuple[str, ...]:
    """Create the immutable cache key for one ordered shortlist."""
    return tuple(str(item) for item in ordered_ids)


def portfolio_id_string(ordered_ids: List[str]) -> str:
    """Render the ordered shortlist into one stable printable key."""
    return "|".join(str(item) for item in ordered_ids)


def duplicate_excess(values: List[str]) -> int:
    """Count duplicate membership beyond the first unique occurrence."""
    counts: Dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return int(sum(max(0, count - 1) for count in counts.values()))


def compute_diversity_features(
    ordered_ids: List[str],
    pair_lookup: Dict[str, Dict[str, object]],
) -> Dict[str, float]:
    """Apply a small deterministic penalty to portfolios concentrated in near-clones."""
    pair_families = [str(pair_lookup[param_id].get("pair_family", "")) for param_id in ordered_ids]
    long_symbols = [str(pair_lookup[param_id]["long_source_symbol"]) for param_id in ordered_ids]
    short_symbols = [str(pair_lookup[param_id]["short_source_symbol"]) for param_id in ordered_ids]
    long_params = [str(pair_lookup[param_id]["long_param_id"]) for param_id in ordered_ids]
    short_params = [str(pair_lookup[param_id]["short_param_id"]) for param_id in ordered_ids]

    duplicate_pair_family_count = duplicate_excess(pair_families)
    duplicate_long_symbol_count = duplicate_excess(long_symbols)
    duplicate_short_symbol_count = duplicate_excess(short_symbols)
    duplicate_long_param_count = duplicate_excess(long_params)
    duplicate_short_param_count = duplicate_excess(short_params)

    diversity_penalty = (
        (0.20 * duplicate_pair_family_count)
        + (0.10 * duplicate_long_symbol_count)
        + (0.10 * duplicate_short_symbol_count)
        + (0.05 * duplicate_long_param_count)
        + (0.05 * duplicate_short_param_count)
    )
    return {
        "duplicate_pair_family_count": float(duplicate_pair_family_count),
        "duplicate_long_symbol_count": float(duplicate_long_symbol_count),
        "duplicate_short_symbol_count": float(duplicate_short_symbol_count),
        "duplicate_long_param_count": float(duplicate_long_param_count),
        "duplicate_short_param_count": float(duplicate_short_param_count),
        "diversity_penalty": float(diversity_penalty),
    }


def objective_sort_key(row: Dict[str, object]) -> Tuple[object, ...]:
    """Sort higher-quality portfolio outcomes first under the new objective."""
    priority_ids = [str(row.get(f"priority_{index}_param_id", "")) for index in range(1, 6)]
    return (
        int(bool(row.get("overall_survival", False))),
        int(not bool(row.get("breached", True))),
        float(row.get("penalized_expectancy", row.get("expectancy", 0.0))),
        float(row.get("expectancy", 0.0)),
        float(row.get("total_profit", 0.0)),
        -float(row.get("max_dd_pct", 999.0)),
        -float(row.get("consistency_score", 999.0)),
        -float(row.get("diversity_penalty", 999.0)),
        -float(row.get("same_symbol_opposite_conflicts", 999999.0)),
        portfolio_id_string(priority_ids),
    )


def sort_portfolio_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Sort portfolio states exactly the same way the search objective compares them."""
    if frame.empty:
        return frame
    return frame.sort_values(
        by=[
            "portfolio_size",
            "overall_survival",
            "breached",
            "penalized_expectancy",
            "expectancy",
            "total_profit",
            "max_dd_pct",
            "consistency_score",
            "diversity_penalty",
            "same_symbol_opposite_conflicts",
            "portfolio_param_ids",
        ],
        ascending=[False, False, True, False, False, False, True, True, True, True, True],
    ).reset_index(drop=True)


def load_candidate_pool(candidates_path: str, ranking_path: str) -> pd.DataFrame:
    """Merge the wide candidate pool with prior ranking metadata."""
    candidates_df = load_csv(candidates_path).copy()
    ranking_df = load_csv(ranking_path).copy()

    rename_map = {
        "analysis_rank": "prior_analysis_rank",
        "rank": "prior_validation_rank",
        "expectancy": "prior_expectancy",
        "win_rate": "prior_win_rate",
        "total_profit": "prior_total_profit",
        "max_dd_pct": "prior_max_dd_pct",
        "consistency_score": "prior_consistency_score",
        "overall_survival": "prior_overall_survival",
        "composite_score": "prior_composite_score",
    }
    meta_columns = ["param_id"] + [name for name in rename_map if name in ranking_df.columns]
    meta_df = ranking_df[meta_columns].rename(columns={name: rename_map[name] for name in rename_map if name in meta_columns})

    merged = candidates_df.merge(meta_df, on="param_id", how="left")
    merged["expectancy"] = merged["prior_expectancy"].fillna(0.0) if "prior_expectancy" in merged.columns else 0.0
    merged["composite_score"] = merged["prior_composite_score"].fillna(0.0) if "prior_composite_score" in merged.columns else 0.0
    merged = merged.sort_values(["combined_rank", "param_id"], ascending=[True, True]).reset_index(drop=True)
    return merged


def build_candidate_lookup(candidate_pool_df: pd.DataFrame) -> Dict[str, CombinedCandidateConfig]:
    """Convert every row into the typed combined-candidate object used by Backtrader."""
    lookup: Dict[str, CombinedCandidateConfig] = {}
    for _, row in candidate_pool_df.iterrows():
        candidate = CombinedCandidateConfig.from_row(row)
        lookup[candidate.param_id] = candidate
    return lookup


def build_pair_rows_df(
    ordered_ids: List[str],
    pair_lookup: Dict[str, Dict[str, object]],
    role_lookup: Optional[Dict[str, str]] = None,
    rationale_lookup: Optional[Dict[str, str]] = None,
    stage_label: str = "search",
) -> pd.DataFrame:
    """Build the flat pair metadata frame consumed by the full portfolio evaluator."""
    role_lookup = role_lookup or {}
    rationale_lookup = rationale_lookup or {}
    rows: List[Dict[str, object]] = []

    for priority, param_id in enumerate(ordered_ids, start=1):
        row = dict(pair_lookup[param_id])
        row["shortlist_priority"] = int(priority)
        row["shortlist_role"] = str(role_lookup.get(param_id, default_role_for_priority(priority)))
        row["shortlist_rationale"] = str(
            rationale_lookup.get(param_id, f"Selected under the corrected realistic {stage_label} objective at priority {priority}.")
        )
        rows.append(row)

    return pd.DataFrame(rows)


def build_realistic_pair_ranking(candidate_pool_df: pd.DataFrame, singleton_rows: List[Dict[str, object]]) -> pd.DataFrame:
    """Attach realistic standalone metrics to the combined candidate pool."""
    metrics_df = pd.DataFrame(singleton_rows).copy()
    if metrics_df.empty:
        raise ValueError("Standalone realistic reranking produced no rows.")

    metrics_df = metrics_df.rename(columns={"priority_1_param_id": "param_id"})
    metrics_df = metrics_df.drop(
        columns=[
            "portfolio_size",
            "portfolio_param_ids",
            "first_seen_stage",
            "evaluation_index",
            "priority_2_param_id",
            "priority_3_param_id",
            "priority_4_param_id",
            "priority_5_param_id",
            "duplicate_pair_family_count",
            "duplicate_long_symbol_count",
            "duplicate_short_symbol_count",
            "duplicate_long_param_count",
            "duplicate_short_param_count",
            "diversity_penalty",
            "penalized_expectancy",
        ],
        errors="ignore",
    )
    metrics_df = metrics_df.drop_duplicates(subset=["param_id"], keep="first")

    ranked = candidate_pool_df.copy()
    drop_merge_cols = [name for name in metrics_df.columns if name != "param_id" and name in ranked.columns]
    ranked = ranked.drop(columns=drop_merge_cols, errors="ignore")
    ranked = ranked.merge(metrics_df, on="param_id", how="left")

    ranked["expectancy_score"] = ranked["expectancy"].rank(method="average", pct=True)
    ranked["drawdown_rule_score"] = ranked["max_dd_pct"].apply(lambda value: clip01((3.0 - float(value)) / 3.0))
    ranked["consistency_penalty_score"] = ranked["consistency_score"].apply(
        lambda value: clip01((20.0 - float(value)) / 20.0)
    )
    ranked["survival_probability_proxy"] = (
        (0.35 * (~ranked["breached"]).astype(float))
        + (0.35 * (ranked["total_profit"] > 0.0).astype(float))
        + (0.15 * ranked["drawdown_rule_score"])
        + (0.15 * ranked["consistency_penalty_score"])
    )
    ranked["composite_score"] = 100.0 * (
        (0.50 * ranked["expectancy_score"])
        + (0.30 * ranked["survival_probability_proxy"])
        + (0.15 * ranked["drawdown_rule_score"])
        + (0.05 * ranked["consistency_penalty_score"])
    )
    ranked["drawdown_headroom_pct_pts"] = 3.0 - ranked["max_dd_pct"]
    ranked["consistency_headroom_pct_pts"] = 20.0 - ranked["consistency_score"]

    ranked = ranked.sort_values(
        by=[
            "composite_score",
            "overall_survival",
            "expectancy",
            "survival_probability_proxy",
            "max_dd_pct",
            "consistency_score",
            "combined_rank",
            "param_id",
        ],
        ascending=[False, False, False, False, True, True, True, True],
    ).reset_index(drop=True)
    ranked.insert(0, "analysis_rank", range(1, len(ranked) + 1))
    return ranked


def read_shortlist_priority_maps(shortlist_path: str, top_n: int) -> Tuple[List[str], Dict[str, str], Dict[str, str]]:
    """Resolve the existing shortlist order plus role/rationale metadata."""
    shortlist_df = load_csv(shortlist_path).copy()
    shortlist_df = shortlist_df.sort_values("shortlist_priority").head(max(1, int(top_n))).reset_index(drop=True)

    ordered_ids = [str(value) for value in shortlist_df["param_id"].tolist()]
    role_lookup = {
        str(row["param_id"]): str(row.get("shortlist_role", default_role_for_priority(int(row["shortlist_priority"]))))
        for _, row in shortlist_df.iterrows()
    }
    rationale_lookup = {str(row["param_id"]): str(row.get("shortlist_rationale", "")) for _, row in shortlist_df.iterrows()}
    return ordered_ids, role_lookup, rationale_lookup


class RealisticPortfolioEvaluator:
    """Run and cache ordered portfolio states under the baseline realistic engine."""

    def __init__(
        self,
        candidate_lookup: Dict[str, CombinedCandidateConfig],
        pair_lookup: Dict[str, Dict[str, object]],
        catalog: MarketDataCatalog,
        raw_coverage_df: pd.DataFrame,
        prior_netted_results: Optional[pd.Series],
    ) -> None:
        self.candidate_lookup = candidate_lookup
        self.pair_lookup = pair_lookup
        self.catalog = catalog
        self.raw_coverage_df = raw_coverage_df.copy()
        self.prior_netted_results = prior_netted_results
        self.cache: Dict[Tuple[str, ...], Dict[str, object]] = {}
        self.evaluation_counter = 0

    def set_pair_lookup(self, pair_lookup: Dict[str, Dict[str, object]]) -> None:
        """Swap the pair-metadata lookup used for future evaluations."""
        self.pair_lookup = pair_lookup

    def _build_record(self, ordered_ids: List[str], stage_label: str, metrics: Dict[str, object]) -> Dict[str, object]:
        self.evaluation_counter += 1
        diversity = compute_diversity_features(ordered_ids=ordered_ids, pair_lookup=self.pair_lookup)

        record: Dict[str, object] = {
            "evaluation_index": int(self.evaluation_counter),
            "first_seen_stage": str(stage_label),
            "portfolio_size": int(len(ordered_ids)),
            "portfolio_param_ids": portfolio_id_string(ordered_ids),
        }
        for priority in range(1, 6):
            record[f"priority_{priority}_param_id"] = str(ordered_ids[priority - 1]) if priority <= len(ordered_ids) else ""

        record.update(metrics)
        record.update(diversity)
        record["penalized_expectancy"] = float(record["expectancy"]) - float(record["diversity_penalty"])
        return record

    def evaluate(
        self,
        ordered_ids: List[str],
        stage_label: str,
        role_lookup: Optional[Dict[str, str]] = None,
        rationale_lookup: Optional[Dict[str, str]] = None,
    ) -> Dict[str, object]:
        """Return cached enriched metrics for one ordered shortlist."""
        key = portfolio_key(ordered_ids)
        if key in self.cache:
            return dict(self.cache[key])

        pair_rows_df = build_pair_rows_df(
            ordered_ids=ordered_ids,
            pair_lookup=self.pair_lookup,
            role_lookup=role_lookup,
            rationale_lookup=rationale_lookup,
            stage_label=stage_label,
        )
        final_pairs = [self.candidate_lookup[param_id] for param_id in ordered_ids]
        metrics, trades_df, positions_df, equity_df, activation_df = run_final_portfolio_full(
            final_pairs=final_pairs,
            pair_rows_df=pair_rows_df,
            catalog=self.catalog,
            friction_preset=FRICTION_PRESETS[BASELINE_PRESET_NAME],
        )

        coverage_df = build_symbol_activation_coverage(
            coverage_df=self.raw_coverage_df,
            activation_df=activation_df,
            portfolio_start_ts=safe_timestamp(equity_df["timestamp"].min() if not equity_df.empty else pd.NaT),
        )
        enriched_metrics, _ = enrich_metrics(
            metrics=metrics,
            positions_df=positions_df,
            equity_df=equity_df,
            coverage_df=coverage_df,
            prior_netted_results=self.prior_netted_results,
            frictionless_metrics=None,
        )

        record = self._build_record(ordered_ids=ordered_ids, stage_label=stage_label, metrics=enriched_metrics)
        self.cache[key] = dict(record)

        del trades_df
        del positions_df
        del equity_df
        del activation_df
        del coverage_df
        gc.collect()
        return dict(record)

    def evaluate_with_details(
        self,
        ordered_ids: List[str],
        stage_label: str,
        role_lookup: Optional[Dict[str, str]] = None,
        rationale_lookup: Optional[Dict[str, str]] = None,
    ) -> Dict[str, object]:
        """Run one ordered shortlist and keep the full detail payload."""
        pair_rows_df = build_pair_rows_df(
            ordered_ids=ordered_ids,
            pair_lookup=self.pair_lookup,
            role_lookup=role_lookup,
            rationale_lookup=rationale_lookup,
            stage_label=stage_label,
        )
        final_pairs = [self.candidate_lookup[param_id] for param_id in ordered_ids]
        metrics, trades_df, positions_df, equity_df, activation_df = run_final_portfolio_full(
            final_pairs=final_pairs,
            pair_rows_df=pair_rows_df,
            catalog=self.catalog,
            friction_preset=FRICTION_PRESETS[BASELINE_PRESET_NAME],
        )
        coverage_df = build_symbol_activation_coverage(
            coverage_df=self.raw_coverage_df,
            activation_df=activation_df,
            portfolio_start_ts=safe_timestamp(equity_df["timestamp"].min() if not equity_df.empty else pd.NaT),
        )
        enriched_metrics, monthly_returns_df = enrich_metrics(
            metrics=metrics,
            positions_df=positions_df,
            equity_df=equity_df,
            coverage_df=coverage_df,
            prior_netted_results=self.prior_netted_results,
            frictionless_metrics=None,
        )
        diversity = compute_diversity_features(ordered_ids=ordered_ids, pair_lookup=self.pair_lookup)
        enriched_metrics.update(diversity)
        enriched_metrics["penalized_expectancy"] = float(enriched_metrics["expectancy"]) - float(diversity["diversity_penalty"])

        return {
            "metrics": enriched_metrics,
            "pair_rows_df": pair_rows_df,
            "pair_stats_df": build_pair_stats(positions_df=positions_df, pair_rows_df=pair_rows_df),
            "symbol_stats_df": build_symbol_stats(positions_df=positions_df),
            "positions_df": positions_df,
            "trades_df": trades_df,
            "equity_df": equity_df,
            "coverage_df": coverage_df,
            "monthly_returns_df": monthly_returns_df,
        }

    def build_results_frame(self) -> pd.DataFrame:
        """Return every unique evaluated portfolio state as one DataFrame."""
        if not self.cache:
            return pd.DataFrame()
        return pd.DataFrame(list(self.cache.values())).copy()


def choose_best_record(rows: List[Dict[str, object]]) -> Dict[str, object]:
    """Pick the best row under the corrected realistic objective."""
    if not rows:
        raise ValueError("No candidate rows were provided to choose_best_record.")
    return max(rows, key=objective_sort_key)


def evaluate_standalone_candidates(candidate_ids: List[str], evaluator: RealisticPortfolioEvaluator) -> List[Dict[str, object]]:
    """Score every combined candidate as a standalone realistic portfolio."""
    rows: List[Dict[str, object]] = []
    progress = tqdm(candidate_ids, desc="Standalone realistic rerank", unit="pair")
    for param_id in progress:
        record = evaluator.evaluate([param_id], stage_label="standalone")
        rows.append(record)
        progress.set_postfix(
            composite=f"{float(record.get('penalized_expectancy', 0.0)):.3f}",
            survive=int(bool(record["overall_survival"])),
            dd=f"{float(record['max_dd_pct']):.2f}",
        )
    return rows


def forward_select_portfolio(
    candidate_ids: List[str],
    top_n: int,
    evaluator: RealisticPortfolioEvaluator,
) -> Tuple[List[str], Dict[str, object]]:
    """Build one ordered shortlist greedily under the realistic objective."""
    selected_ids: List[str] = []
    best_record: Optional[Dict[str, object]] = None

    for step in range(1, top_n + 1):
        remaining_ids = [param_id for param_id in candidate_ids if param_id not in selected_ids]
        if not remaining_ids:
            raise ValueError("No remaining candidates were available during forward selection.")

        step_rows: List[Dict[str, object]] = []
        progress = tqdm(remaining_ids, desc=f"Forward selection {step}/{top_n}", unit="portfolio")
        for param_id in progress:
            ordered_ids = selected_ids + [param_id]
            record = evaluator.evaluate(ordered_ids, stage_label=f"forward_step_{step}")
            step_rows.append(record)
            progress.set_postfix(
                survive=int(bool(record["overall_survival"])),
                penalized=f"{float(record['penalized_expectancy']):.3f}",
                div=f"{float(record['diversity_penalty']):.2f}",
            )

        best_record = choose_best_record(step_rows)
        selected_ids = [str(best_record[f"priority_{priority}_param_id"]) for priority in range(1, int(best_record["portfolio_size"]) + 1)]

    if best_record is None:
        raise ValueError("Forward selection did not produce a portfolio.")
    return selected_ids, best_record


def refine_with_swaps(
    current_ids: List[str],
    candidate_ids: List[str],
    evaluator: RealisticPortfolioEvaluator,
    swap_rounds: int,
) -> Tuple[List[str], Dict[str, object]]:
    """Try deterministic one-for-one replacement moves after forward selection."""
    current_record = evaluator.evaluate(current_ids, stage_label="forward_selected")
    if swap_rounds <= 0:
        return current_ids, current_record

    for round_index in range(1, swap_rounds + 1):
        remaining_ids = [param_id for param_id in candidate_ids if param_id not in current_ids]
        best_round_record = current_record
        best_round_ids = list(current_ids)

        progress = tqdm(
            total=len(current_ids) * len(remaining_ids),
            desc=f"Swap refinement {round_index}/{swap_rounds}",
            unit="portfolio",
        )
        for slot_index in range(len(current_ids)):
            for replacement_id in remaining_ids:
                trial_ids = list(current_ids)
                trial_ids[slot_index] = replacement_id
                record = evaluator.evaluate(trial_ids, stage_label=f"swap_round_{round_index}")
                if objective_sort_key(record) > objective_sort_key(best_round_record):
                    best_round_record = record
                    best_round_ids = list(trial_ids)
                    progress.set_postfix(
                        survive=int(bool(record["overall_survival"])),
                        penalized=f"{float(record['penalized_expectancy']):.3f}",
                        div=f"{float(record['diversity_penalty']):.2f}",
                    )
                progress.update(1)
        progress.close()

        if best_round_ids == current_ids:
            break
        current_ids = best_round_ids
        current_record = best_round_record

    return current_ids, current_record


def build_shortlist_output(
    ordered_ids: List[str],
    realistic_lookup: Dict[str, Dict[str, object]],
    best_portfolio_record: Dict[str, object],
) -> pd.DataFrame:
    """Render the new final shortlist CSV in the same broad schema as the old shortlist."""
    rows: List[Dict[str, object]] = []
    for priority, param_id in enumerate(ordered_ids, start=1):
        pair_row = realistic_lookup[param_id]
        rows.append(
            {
                "shortlist_priority": int(priority),
                "param_id": str(param_id),
                "long_param_id": str(pair_row["long_param_id"]),
                "short_param_id": str(pair_row["short_param_id"]),
                "long_source_symbol": str(pair_row["long_source_symbol"]),
                "short_source_symbol": str(pair_row["short_source_symbol"]),
                "long_confirm_ema_period": int(pair_row["long_confirm_ema_period"]),
                "long_confirm_min_distance": float(pair_row["long_confirm_min_distance"]),
                "short_confirm_ema_period": int(pair_row["short_confirm_ema_period"]),
                "short_confirm_min_distance": float(pair_row["short_confirm_min_distance"]),
                "total_trades": int(pair_row["total_trades"]),
                "long_total_trades": int(pair_row["long_total_trades"]),
                "short_total_trades": int(pair_row["short_total_trades"]),
                "win_rate": float(pair_row["win_rate"]),
                "expectancy": float(pair_row["expectancy"]),
                "max_dd_pct": float(pair_row["max_dd_pct"]),
                "consistency_score": float(pair_row["consistency_score"]),
                "overall_survival": bool(pair_row["overall_survival"]),
                "survival_probability_proxy": float(pair_row["survival_probability_proxy"]),
                "composite_score": float(pair_row["composite_score"]),
                "signal_conflicts": int(pair_row.get("same_symbol_opposite_conflicts", 0)),
                "shortlist_role": default_role_for_priority(priority),
                "shortlist_rationale": (
                    f"Selected under the corrected 34-month realistic baseline objective at priority {priority}. "
                    f"Portfolio penalized_expectancy={float(best_portfolio_record['penalized_expectancy']):.4f}, "
                    f"diversity_penalty={float(best_portfolio_record['diversity_penalty']):.4f}."
                ),
                "portfolio_expectancy": float(best_portfolio_record["expectancy"]),
                "portfolio_penalized_expectancy": float(best_portfolio_record["penalized_expectancy"]),
                "portfolio_max_dd_pct": float(best_portfolio_record["max_dd_pct"]),
                "portfolio_consistency_score": float(best_portfolio_record["consistency_score"]),
                "portfolio_overall_survival": bool(best_portfolio_record["overall_survival"]),
                "portfolio_diversity_penalty": float(best_portfolio_record["diversity_penalty"]),
                "portfolio_stacked_same_side_entries": int(best_portfolio_record["stacked_same_side_entries"]),
                "portfolio_stacking_profit_delta_vs_netted": float(best_portfolio_record["stacking_profit_delta_vs_netted"]),
            }
        )
    return pd.DataFrame(rows)


def build_portfolio_summary_row(label: str, ordered_ids: List[str], metrics: Dict[str, object]) -> Dict[str, object]:
    """Flatten one portfolio outcome for summary tables."""
    return {
        "portfolio_label": str(label),
        "portfolio_param_ids": portfolio_id_string(ordered_ids),
        "expectancy": float(metrics["expectancy"]),
        "penalized_expectancy": float(metrics["penalized_expectancy"]),
        "total_profit": float(metrics["total_profit"]),
        "max_dd_pct": float(metrics["max_dd_pct"]),
        "consistency_score": float(metrics["consistency_score"]),
        "overall_survival": bool(metrics["overall_survival"]),
        "stacked_same_side_entries": int(metrics["stacked_same_side_entries"]),
        "diversity_penalty": float(metrics["diversity_penalty"]),
        "stacking_profit_delta_vs_netted": float(metrics["stacking_profit_delta_vs_netted"]),
    }


def build_pair_comparison_rows(
    portfolio_label: str,
    detail_payload: Dict[str, object],
    realistic_lookup: Dict[str, Dict[str, object]],
) -> List[Dict[str, object]]:
    """Create the pair-level old-vs-new comparison table requested by the user."""
    metrics = detail_payload["metrics"]
    pair_rows_df = detail_payload["pair_rows_df"].sort_values("shortlist_priority").reset_index(drop=True)
    pair_stats_df = detail_payload["pair_stats_df"].copy()
    pair_stats_lookup = {str(row["source_pair_id"]): row for _, row in pair_stats_df.iterrows()}

    rows: List[Dict[str, object]] = []
    for _, shortlist_row in pair_rows_df.iterrows():
        param_id = str(shortlist_row["param_id"])
        realistic_row = realistic_lookup[param_id]
        realized_row = pair_stats_lookup.get(param_id, {})

        rows.append(
            {
                "portfolio_label": str(portfolio_label),
                "portfolio_expectancy": float(metrics["expectancy"]),
                "portfolio_penalized_expectancy": float(metrics["penalized_expectancy"]),
                "portfolio_max_dd_pct": float(metrics["max_dd_pct"]),
                "portfolio_overall_survival": bool(metrics["overall_survival"]),
                "portfolio_stacked_same_side_entries": int(metrics["stacked_same_side_entries"]),
                "portfolio_diversity_penalty": float(metrics["diversity_penalty"]),
                "portfolio_stacking_profit_delta_vs_netted": float(metrics["stacking_profit_delta_vs_netted"]),
                "shortlist_priority": int(shortlist_row["shortlist_priority"]),
                "param_id": str(param_id),
                "long_param_id": str(shortlist_row["long_param_id"]),
                "short_param_id": str(shortlist_row["short_param_id"]),
                "standalone_expectancy": float(realistic_row["expectancy"]),
                "standalone_max_dd_pct": float(realistic_row["max_dd_pct"]),
                "standalone_overall_survival": bool(realistic_row["overall_survival"]),
                "standalone_composite_score": float(realistic_row["composite_score"]),
                "standalone_survival_probability_proxy": float(realistic_row["survival_probability_proxy"]),
                "realized_pair_positions": int(realized_row.get("positions", 0)),
                "realized_pair_total_profit": float(realized_row.get("total_profit", 0.0)),
                "realized_pair_position_win_rate": float(realized_row.get("position_win_rate", 0.0)),
                "stacking_impact_proxy_avg_support_pair_count": float(realized_row.get("avg_support_pair_count", 0.0)),
            }
        )
    return rows


def write_summary_markdown(
    summary_path: str,
    candidate_pool_df: pd.DataFrame,
    realistic_ranking_df: pd.DataFrame,
    portfolio_search_df: pd.DataFrame,
    old_summary_df: pd.DataFrame,
    new_summary_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    shortlist_df: pd.DataFrame,
    old_ids: List[str],
    new_ids: List[str],
    swap_rounds: int,
) -> None:
    """Write the high-level markdown summary for the realistic re-optimization run."""
    size_target_df = sort_portfolio_frame(portfolio_search_df.loc[portfolio_search_df["portfolio_size"] == len(new_ids)].copy())

    old_set = set(old_ids)
    new_set = set(new_ids)
    kept_ids = [param_id for param_id in new_ids if param_id in old_set]
    added_ids = [param_id for param_id in new_ids if param_id not in old_set]
    removed_ids = [param_id for param_id in old_ids if param_id not in new_set]

    portfolio_summary_df = pd.concat([old_summary_df, new_summary_df], ignore_index=True)
    pair_compare_display = comparison_df[
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
    winners_display = size_target_df[
        [
            "portfolio_param_ids",
            "overall_survival",
            "penalized_expectancy",
            "expectancy",
            "max_dd_pct",
            "consistency_score",
            "diversity_penalty",
            "stacked_same_side_entries",
            "first_seen_stage",
        ]
    ].head(10).copy()

    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write("# Backtrader realistic shortlist re-optimization summary\n\n")
        handle.write("- **objective**: maximize expectancy under the corrected 34-month realistic baseline portfolio engine\n")
        handle.write(f"- **baseline_friction_preset**: {BASELINE_PRESET_NAME}\n")
        handle.write(f"- **candidate_pairs_in_pool**: {len(candidate_pool_df)}\n")
        handle.write(f"- **standalone_realistic_survivors**: {int(realistic_ranking_df['overall_survival'].sum())}\n")
        handle.write(f"- **unique_portfolios_evaluated**: {len(portfolio_search_df)}\n")
        handle.write(f"- **target_shortlist_size**: {len(new_ids)}\n")
        handle.write("- **search_method**: deterministic forward selection plus bounded swap refinement\n")
        handle.write("- **note**: the portfolio objective includes a small diversity penalty to avoid near-clone concentration.\n")
        handle.write(f"- **swap_rounds**: {int(swap_rounds)}\n")

        handle.write("\n## Portfolio Comparison\n\n")
        handle.write(markdown_table(portfolio_summary_df))

        handle.write("\n## New Final Shortlist\n\n")
        handle.write(markdown_table(shortlist_display))

        handle.write("\n## Old vs New Pair Table\n\n")
        handle.write(markdown_table(pair_compare_display))

        handle.write("\n## Top Evaluated Target-Size Portfolios\n\n")
        handle.write(markdown_table(winners_display))

        handle.write("\n## Membership Change\n\n")
        handle.write(f"- **kept_pairs**: {', '.join(kept_ids) if kept_ids else 'none'}\n")
        handle.write(f"- **added_pairs**: {', '.join(added_ids) if added_ids else 'none'}\n")
        handle.write(f"- **removed_pairs**: {', '.join(removed_ids) if removed_ids else 'none'}\n")


def main() -> None:
    """Re-optimize the final shortlist under the corrected realistic objective."""
    args = parse_args()
    if int(args.top_n) <= 0:
        raise ValueError("--top-n must be at least 1.")

    candidate_pool_df = load_candidate_pool(candidates_path=args.candidates, ranking_path=args.ranking)
    if args.candidate_limit is not None:
        candidate_pool_df = candidate_pool_df.head(max(1, int(args.candidate_limit))).reset_index(drop=True)
    if len(candidate_pool_df) < int(args.top_n):
        raise ValueError(f"Candidate pool has only {len(candidate_pool_df)} rows, which is less than top-n={int(args.top_n)}.")

    catalog = MarketDataCatalog(daily_path=args.daily_data, intraday_path=args.intraday_data)
    raw_coverage_df = catalog.describe_symbol_coverage(prefer_intraday=True)
    prior_netted_results = load_prior_netted_results(DEFAULT_PRIOR_NETTED_RESULTS)

    candidate_lookup = build_candidate_lookup(candidate_pool_df)
    initial_pair_lookup = {str(row["param_id"]): row.to_dict() for _, row in candidate_pool_df.iterrows()}
    evaluator = RealisticPortfolioEvaluator(
        candidate_lookup=candidate_lookup,
        pair_lookup=initial_pair_lookup,
        catalog=catalog,
        raw_coverage_df=raw_coverage_df,
        prior_netted_results=prior_netted_results,
    )

    candidate_ids = [str(value) for value in candidate_pool_df["param_id"].tolist()]
    singleton_rows = evaluate_standalone_candidates(candidate_ids=candidate_ids, evaluator=evaluator)
    realistic_ranking_df = build_realistic_pair_ranking(candidate_pool_df=candidate_pool_df, singleton_rows=singleton_rows)
    realistic_ranking_df.to_csv(args.realistic_ranking_output, index=False)

    realistic_pair_lookup = {str(row["param_id"]): row.to_dict() for _, row in realistic_ranking_df.iterrows()}
    evaluator.set_pair_lookup(realistic_pair_lookup)

    ranked_candidate_ids = [str(value) for value in realistic_ranking_df["param_id"].tolist()]
    selected_ids, selected_record = forward_select_portfolio(
        candidate_ids=ranked_candidate_ids,
        top_n=int(args.top_n),
        evaluator=evaluator,
    )
    selected_ids, selected_record = refine_with_swaps(
        current_ids=selected_ids,
        candidate_ids=ranked_candidate_ids,
        evaluator=evaluator,
        swap_rounds=int(args.swap_rounds),
    )

    shortlist_df = build_shortlist_output(
        ordered_ids=selected_ids,
        realistic_lookup=realistic_pair_lookup,
        best_portfolio_record=selected_record,
    )
    shortlist_df.to_csv(args.shortlist_output, index=False)

    portfolio_search_df = sort_portfolio_frame(evaluator.build_results_frame())
    portfolio_search_df.to_csv(args.portfolio_search_output, index=False)

    old_ids, old_role_lookup, old_rationale_lookup = read_shortlist_priority_maps(
        shortlist_path=args.old_shortlist,
        top_n=int(args.top_n),
    )
    old_detail = evaluator.evaluate_with_details(
        ordered_ids=old_ids,
        stage_label="old_shortlist_comparison",
        role_lookup=old_role_lookup,
        rationale_lookup=old_rationale_lookup,
    )
    new_detail = evaluator.evaluate_with_details(
        ordered_ids=selected_ids,
        stage_label="realistic_final_shortlist",
    )

    old_summary_df = pd.DataFrame([build_portfolio_summary_row("old_shortlist", old_ids, old_detail["metrics"])])
    new_summary_df = pd.DataFrame([build_portfolio_summary_row("new_shortlist", selected_ids, new_detail["metrics"])])

    comparison_rows = build_pair_comparison_rows(
        portfolio_label="old_shortlist",
        detail_payload=old_detail,
        realistic_lookup=realistic_pair_lookup,
    ) + build_pair_comparison_rows(
        portfolio_label="new_shortlist",
        detail_payload=new_detail,
        realistic_lookup=realistic_pair_lookup,
    )
    comparison_df = pd.DataFrame(comparison_rows).sort_values(["portfolio_label", "shortlist_priority"], ascending=[True, True]).reset_index(drop=True)
    comparison_df.to_csv(args.comparison_output, index=False)

    write_summary_markdown(
        summary_path=args.summary_output,
        candidate_pool_df=candidate_pool_df,
        realistic_ranking_df=realistic_ranking_df,
        portfolio_search_df=portfolio_search_df,
        old_summary_df=old_summary_df,
        new_summary_df=new_summary_df,
        comparison_df=comparison_df,
        shortlist_df=shortlist_df,
        old_ids=old_ids,
        new_ids=selected_ids,
        swap_rounds=int(args.swap_rounds),
    )

    print(f"Realistic ranking: {args.realistic_ranking_output}")
    print(f"New shortlist: {args.shortlist_output}")
    print(f"Portfolio search audit: {args.portfolio_search_output}")
    print(f"Old vs new comparison: {args.comparison_output}")
    print(f"Summary: {args.summary_output}")


if __name__ == "__main__":
    main()
