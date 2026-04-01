"""
Detailed analysis and ranking for surviving combined long + short portfolios.

This script mirrors the existing survivor-analysis workflow, but it is pair-
aware: each row represents one long finalist paired with one short finalist.

Outputs:
- results/backtrader_combined_survivor_ranking.csv
- results/backtrader_combined_survivor_report.md
"""

from __future__ import annotations

import argparse
import math
import os
from typing import Dict, List, Tuple

import pandas as pd


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

DEFAULT_VALIDATION_RESULTS = os.path.join(RESULTS_DIR, "backtrader_combined_results.csv")
DEFAULT_CANDIDATES = os.path.join(RESULTS_DIR, "backtrader_combined_candidates.csv")
DEFAULT_RANKING_CSV = os.path.join(RESULTS_DIR, "backtrader_combined_survivor_ranking.csv")
DEFAULT_REPORT_MD = os.path.join(RESULTS_DIR, "backtrader_combined_survivor_report.md")

WEIGHTS: Dict[str, float] = {
    "expectancy": 0.35,
    "win_rate": 0.25,
    "drawdown": 0.20,
    "consistency": 0.20,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze and rank combined Backtrader survivors.")
    parser.add_argument("--validation-results", default=DEFAULT_VALIDATION_RESULTS)
    parser.add_argument("--candidates", default=DEFAULT_CANDIDATES)
    parser.add_argument("--ranking-csv", default=DEFAULT_RANKING_CSV)
    parser.add_argument("--report-md", default=DEFAULT_REPORT_MD)
    return parser.parse_args()


def normalize(series: pd.Series, invert: bool = False) -> pd.Series:
    """Min-max normalize one metric onto the 0..1 range."""
    series = series.astype(float)
    min_value = float(series.min())
    max_value = float(series.max())

    if math.isclose(min_value, max_value, rel_tol=0.0, abs_tol=1e-12):
        base = pd.Series([1.0] * len(series), index=series.index)
    else:
        base = (series - min_value) / (max_value - min_value)

    return 1.0 - base if invert else base


def summarize_count_dict(series: pd.Series, top_n: int = 4) -> str:
    """Convert a value-count series into a compact summary string."""
    if series.empty:
        return "none"
    return ", ".join(f"{key}={int(value)}" for key, value in series.head(top_n).items())


def build_markdown_table(frame: pd.DataFrame) -> str:
    """Render a markdown table without adding extra dependencies."""
    headers = list(frame.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(str(row[column]) for column in headers) + " |")
    return "\n".join(lines)


def build_pair_label(row: pd.Series) -> str:
    """Group related pair families into a short human-readable label."""
    return f"{row['long_source_symbol']} + {row['short_source_symbol']}"


def build_candidate_note(row: pd.Series, top_score: float) -> str:
    """Generate a short pair-aware guidance note."""
    notes: List[str] = []

    if math.isclose(float(row["composite_score"]), top_score, abs_tol=1e-9):
        notes.append("Best overall balance in the combined survivor pool.")
    if bool(row["best_expectancy_flag"]):
        notes.append("Highest expectancy among the combined survivors.")
    if bool(row["best_win_rate_flag"]):
        notes.append("Highest win rate among the combined survivors.")
    if bool(row["best_drawdown_flag"]):
        notes.append("Tightest trailing-drawdown control in the pair set.")
    if bool(row["best_consistency_flag"]):
        notes.append("Safest consistency profile in the pair set.")
    if float(row["drawdown_headroom_pct_pts"]) < 0.5:
        notes.append("Limited drawdown headroom below the 3% trailing cap.")
    if float(row["consistency_headroom_pct_pts"]) < 1.0:
        notes.append("Very close to the 20% consistency ceiling.")
    if int(row["metric_duplicate_count"]) > 1:
        notes.append("Shares identical outcome metrics with another pair; treat as a threshold duplicate.")
    if abs(float(row["long_profit_share_pct"])) >= 80.0:
        notes.append("Portfolio profit is heavily long-dominated.")
    if abs(float(row["short_profit_share_pct"])) >= 80.0:
        notes.append("Portfolio profit is heavily short-dominated.")
    if int(row["signal_conflicts"]) > 0:
        notes.append(f"Skipped {int(row['signal_conflicts'])} same-symbol dual-signal conflicts.")
    if not notes:
        notes.append("Balanced pair survivor with no obvious structural warning.")

    return " ".join(notes)


def prepare_survivor_ranking(validation_path: str, candidates_path: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build the ranking table, pair-family stats, and full validation frame."""
    if not os.path.exists(validation_path):
        raise FileNotFoundError(f"Validation results not found: {validation_path}")
    if not os.path.exists(candidates_path):
        raise FileNotFoundError(f"Candidate file not found: {candidates_path}")

    validation_df = pd.read_csv(validation_path)
    candidates_df = pd.read_csv(candidates_path)
    survivors = validation_df.loc[validation_df["overall_survival"] == True].copy()
    if survivors.empty:
        raise ValueError("No combined survivors found in the validation results.")

    extra_columns = ["param_id"] + [column for column in candidates_df.columns if column not in validation_df.columns]
    candidate_extra = candidates_df[extra_columns].copy()
    survivors = survivors.merge(candidate_extra, on="param_id", how="left", suffixes=("", "_candidate"))

    survivors["score_expectancy"] = normalize(survivors["expectancy"], invert=False)
    survivors["score_win_rate"] = normalize(survivors["win_rate"], invert=False)
    survivors["score_drawdown"] = normalize(survivors["max_dd_pct"], invert=True)
    survivors["score_consistency"] = normalize(survivors["consistency_score"], invert=True)
    survivors["composite_score"] = 100.0 * (
        WEIGHTS["expectancy"] * survivors["score_expectancy"]
        + WEIGHTS["win_rate"] * survivors["score_win_rate"]
        + WEIGHTS["drawdown"] * survivors["score_drawdown"]
        + WEIGHTS["consistency"] * survivors["score_consistency"]
    )

    survivors["drawdown_headroom_pct_pts"] = 3.0 - survivors["max_dd_pct"]
    survivors["consistency_headroom_pct_pts"] = 20.0 - survivors["consistency_score"]

    survivors["win_rate_sig"] = survivors["win_rate"].round(6)
    survivors["expectancy_sig"] = survivors["expectancy"].round(6)
    survivors["max_dd_pct_sig"] = survivors["max_dd_pct"].round(6)
    survivors["consistency_sig"] = survivors["consistency_score"].round(6)
    metric_signature_cols = ["total_trades", "win_rate_sig", "expectancy_sig", "max_dd_pct_sig", "consistency_sig"]
    signature_counts = (
        survivors.groupby(metric_signature_cols)
        .size()
        .rename("metric_duplicate_count")
        .reset_index()
    )
    survivors = survivors.merge(signature_counts, on=metric_signature_cols, how="left")

    survivors["pair_label"] = survivors.apply(build_pair_label, axis=1)
    survivors["pair_cluster_size"] = survivors.groupby("pair_label")["rank"].transform("size")
    survivors["long_profit_share_pct"] = survivors.apply(
        lambda row: 100.0 * float(row["long_total_profit"]) / float(row["total_profit"]) if float(row["total_profit"]) != 0.0 else 0.0,
        axis=1,
    )
    survivors["short_profit_share_pct"] = survivors.apply(
        lambda row: 100.0 * float(row["short_total_profit"]) / float(row["total_profit"]) if float(row["total_profit"]) != 0.0 else 0.0,
        axis=1,
    )

    survivors["best_expectancy_flag"] = survivors["expectancy"] == survivors["expectancy"].max()
    survivors["best_win_rate_flag"] = survivors["win_rate"] == survivors["win_rate"].max()
    survivors["best_drawdown_flag"] = survivors["max_dd_pct"] == survivors["max_dd_pct"].min()
    survivors["best_consistency_flag"] = survivors["consistency_score"] == survivors["consistency_score"].min()

    top_score = float(survivors["composite_score"].max())
    survivors["ai_note"] = survivors.apply(lambda row: build_candidate_note(row, top_score), axis=1)

    survivors = survivors.sort_values(
        by=["composite_score", "expectancy", "win_rate", "max_dd_pct", "consistency_score"],
        ascending=[False, False, False, True, True],
    ).reset_index(drop=True)
    survivors.insert(0, "analysis_rank", range(1, len(survivors) + 1))

    pair_stats = (
        validation_df.groupby(["long_source_symbol", "short_source_symbol", "pair_family"], dropna=False)
        .agg(
            candidates_tested=("rank", "size"),
            survivors=("overall_survival", "sum"),
            best_expectancy=("expectancy", "max"),
            median_max_dd_pct=("max_dd_pct", "median"),
            median_signal_conflicts=("signal_conflicts", "median"),
        )
        .reset_index()
    )
    pair_stats["survival_rate_pct"] = 100.0 * pair_stats["survivors"] / pair_stats["candidates_tested"]
    pair_stats = pair_stats.sort_values(
        by=["survivors", "survival_rate_pct", "best_expectancy"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    return survivors, pair_stats, validation_df


def write_report(report_path: str, ranking_df: pd.DataFrame, pair_stats: pd.DataFrame, validation_df: pd.DataFrame) -> None:
    """Write the detailed pair-aware combined survivor report."""
    survivors = ranking_df.copy()
    pair_distribution = survivors.groupby("pair_family").size().sort_values(ascending=False)
    long_distribution = survivors.groupby("long_source_symbol").size().sort_values(ascending=False)
    short_distribution = survivors.groupby("short_source_symbol").size().sort_values(ascending=False)
    duplicate_survivors = survivors.loc[survivors["metric_duplicate_count"] > 1].copy()
    high_risk_survivors = survivors.loc[survivors["consistency_headroom_pct_pts"] < 2.0].copy()

    top_table = survivors[
        [
            "analysis_rank",
            "long_param_id",
            "short_param_id",
            "pair_family",
            "win_rate",
            "expectancy",
            "max_dd_pct",
            "consistency_score",
            "signal_conflicts",
            "composite_score",
        ]
    ].copy()

    pair_table = pair_stats[
        [
            "pair_family",
            "candidates_tested",
            "survivors",
            "survival_rate_pct",
            "best_expectancy",
            "median_max_dd_pct",
            "median_signal_conflicts",
        ]
    ].copy()

    top_ids = survivors.head(5)["param_id"].tolist()
    pair_summary = summarize_count_dict(pair_distribution)
    long_summary = summarize_count_dict(long_distribution)
    short_summary = summarize_count_dict(short_distribution)

    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write("# Backtrader Combined Survivor Analysis Report\n\n")
        handle.write("## Overview\n\n")
        handle.write(f"- **survivors_found**: {len(survivors)}\n")
        handle.write(f"- **best_overall_pair**: {survivors.iloc[0]['param_id']}\n")
        handle.write(f"- **best_expectancy**: {survivors['expectancy'].max():.4f}\n")
        handle.write(f"- **best_win_rate**: {survivors['win_rate'].max():.4f}\n")
        handle.write(f"- **lowest_max_dd_pct**: {survivors['max_dd_pct'].min():.4f}\n")
        handle.write(f"- **best_consistency_score**: {survivors['consistency_score'].min():.4f}\n")
        handle.write(f"- **pair_family_distribution**: {pair_summary}\n")
        handle.write(f"- **long_side_distribution**: {long_summary}\n")
        handle.write(f"- **short_side_distribution**: {short_summary}\n")

        handle.write("\n## Ranking Table\n\n")
        handle.write(build_markdown_table(top_table.round(4)))
        handle.write("\n")

        handle.write("\n## Pair Family Analysis\n\n")
        handle.write(build_markdown_table(pair_table.round(4)))
        handle.write("\n")
        handle.write(
            f"\n- **Interpretation**: the combined survivor pool is concentrated by pair family as {pair_summary}.\n"
        )
        handle.write(
            f"- **Interpretation**: long-side contribution among survivors is {long_summary}, while short-side contribution is {short_summary}.\n"
        )
        if not duplicate_survivors.empty:
            handle.write(
                f"- **Interpretation**: {len(duplicate_survivors)} combined survivors share an exact outcome signature with at least one neighbor, "
                "so they should be treated as threshold variants instead of independent deployment slots.\n"
            )

        handle.write("\n## Survivor-by-Survivor Detail\n\n")
        for _, row in survivors.iterrows():
            handle.write(f"### {int(row['analysis_rank'])}. {row['param_id']}\n\n")
            handle.write(f"- **pair_family**: {row['pair_family']} (cluster size {int(row['pair_cluster_size'])})\n")
            handle.write(
                f"- **long_leg**: {row['long_param_id']} | {row['long_source_symbol']} | "
                f"SMA={int(row['long_sma'])}, fib_band={float(row['long_fib_band']):.3f}, "
                f"rw={float(row['long_rw']):.3f}, eb={float(row['long_eb']):.3f}, "
                f"rw_lookback={int(row['long_rw_lookback'])}, "
                f"confirm_ema_period={int(row['long_confirm_ema_period'])}, "
                f"confirm_min_distance={float(row['long_confirm_min_distance']):.3f}\n"
            )
            handle.write(
                f"- **short_leg**: {row['short_param_id']} | {row['short_source_symbol']} | "
                f"SMA={int(row['short_sma'])}, fib_band={float(row['short_fib_band']):.3f}, "
                f"rw={float(row['short_rw']):.3f}, eb={float(row['short_eb']):.3f}, "
                f"rw_lookback={int(row['short_rw_lookback'])}, "
                f"confirm_ema_period={int(row['short_confirm_ema_period'])}, "
                f"confirm_min_distance={float(row['short_confirm_min_distance']):.3f}\n"
            )
            handle.write(
                f"- **portfolio_metrics**: total_trades={int(row['total_trades'])}, "
                f"long_trades={int(row['long_total_trades'])}, short_trades={int(row['short_total_trades'])}, "
                f"win_rate={float(row['win_rate']):.4f}, expectancy={float(row['expectancy']):.4f}, "
                f"max_dd_pct={float(row['max_dd_pct']):.4f}, consistency_score={float(row['consistency_score']):.4f}\n"
            )
            handle.write(
                f"- **profit_split**: long_total_profit={float(row['long_total_profit']):.4f} "
                f"({float(row['long_profit_share_pct']):.2f}%), short_total_profit={float(row['short_total_profit']):.4f} "
                f"({float(row['short_profit_share_pct']):.2f}%)\n"
            )
            handle.write(
                f"- **operational_detail**: signal_conflicts={int(row['signal_conflicts'])}, "
                f"max_concurrent_observed={int(row['max_concurrent_observed'])}\n"
            )
            handle.write(
                f"- **headroom**: drawdown_headroom={float(row['drawdown_headroom_pct_pts']):.4f} pct points, "
                f"consistency_headroom={float(row['consistency_headroom_pct_pts']):.4f} pct points\n"
            )
            handle.write(f"- **composite_score**: {float(row['composite_score']):.2f}\n")
            handle.write(f"- **ai_note**: {row['ai_note']}\n\n")

        handle.write("## AI Conclusions\n\n")
        handle.write(f"- **Top deployment shortlist**: {', '.join(top_ids)}\n")
        handle.write(
            f"- **Practical view**: the strongest combined pairs currently cluster around {pair_summary}. "
            "That concentration is useful signal, but it also means we should trim exact metric clones before promoting live candidates.\n"
        )
        if not high_risk_survivors.empty:
            handle.write(
                f"- **Risk view**: {len(high_risk_survivors)} combined survivors sit within 2 percentage points of the 20% consistency ceiling. "
                "Those should rank behind the cleaner headroom pairs.\n"
            )
        else:
            handle.write("- **Risk view**: none of the combined survivors are pressing tightly against the 20% consistency ceiling, which is a good sign for portfolio robustness.\n")


def main() -> None:
    """Run the full combined-survivor analysis workflow."""
    args = parse_args()
    ranking_df, pair_stats, validation_df = prepare_survivor_ranking(
        validation_path=args.validation_results,
        candidates_path=args.candidates,
    )

    ranking_df.to_csv(args.ranking_csv, index=False)
    write_report(
        report_path=args.report_md,
        ranking_df=ranking_df,
        pair_stats=pair_stats,
        validation_df=validation_df,
    )

    print(f"Combined survivors analyzed: {len(ranking_df)}")
    print(f"Ranking CSV: {args.ranking_csv}")
    print(f"Report MD: {args.report_md}")


if __name__ == "__main__":
    main()
