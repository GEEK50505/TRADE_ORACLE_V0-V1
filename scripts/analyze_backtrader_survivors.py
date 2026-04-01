"""
Detailed analysis and ranking for the surviving Backtrader candidates.

This script reads the finished Backtrader validation results, filters to the
survivors, ranks them using a multi-metric composite score, and writes a
developer-friendly markdown report plus CSV artifacts.

Outputs:
- results/backtrader_survivor_ranking.csv
- results/backtrader_survivor_asset_stats.csv
- results/backtrader_survivor_report.md

Recommended usage:
    python scripts/analyze_backtrader_survivors.py
"""

from __future__ import annotations

import argparse
import math
import os
from typing import Dict, List

import pandas as pd


# ==============================================================================
# PATHS
# ==============================================================================

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

DEFAULT_VALIDATION_RESULTS = os.path.join(RESULTS_DIR, "backtrader_validation_results.csv")
DEFAULT_SHORTLIST = os.path.join(RESULTS_DIR, "daily_wider_v2_backtrader_shortlist.csv")
DEFAULT_RANKING_CSV = os.path.join(RESULTS_DIR, "backtrader_survivor_ranking.csv")
DEFAULT_ASSET_STATS_CSV = os.path.join(RESULTS_DIR, "backtrader_survivor_asset_stats.csv")
DEFAULT_REPORT_MD = os.path.join(RESULTS_DIR, "backtrader_survivor_report.md")


# ==============================================================================
# WEIGHTS
# ==============================================================================

# These weights intentionally balance raw edge with prop-firm survivability.
WEIGHTS: Dict[str, float] = {
    "expectancy": 0.35,
    "win_rate": 0.25,
    "drawdown": 0.20,
    "consistency": 0.20,
}


def parse_args() -> argparse.Namespace:
    """Expose the few knobs we need for reuse."""
    parser = argparse.ArgumentParser(description="Analyze and rank Backtrader survivors.")
    parser.add_argument("--validation-results", default=DEFAULT_VALIDATION_RESULTS)
    parser.add_argument("--shortlist", default=DEFAULT_SHORTLIST)
    parser.add_argument("--ranking-csv", default=DEFAULT_RANKING_CSV)
    parser.add_argument("--asset-stats-csv", default=DEFAULT_ASSET_STATS_CSV)
    parser.add_argument("--report-md", default=DEFAULT_REPORT_MD)
    return parser.parse_args()


def normalize(series: pd.Series, invert: bool = False) -> pd.Series:
    """
    Min-max normalize a metric onto the 0..1 range.

    For inverse metrics such as drawdown and consistency score, `invert=True`
    converts lower raw values into higher normalized scores.
    """

    series = series.astype(float)
    min_value = float(series.min())
    max_value = float(series.max())

    # If all values are equal, treat the whole column as equally good.
    if math.isclose(min_value, max_value, rel_tol=0.0, abs_tol=1e-12):
        base = pd.Series([1.0] * len(series), index=series.index)
    else:
        base = (series - min_value) / (max_value - min_value)

    return 1.0 - base if invert else base


def has_confirmation_columns(frame: pd.DataFrame) -> bool:
    """Return True when the frame carries the optional 4H confirmation fields."""
    return "confirm_enabled" in frame.columns and frame["confirm_enabled"].fillna(False).astype(bool).any()


def infer_strategy_side(frame: pd.DataFrame) -> str:
    """Infer whether the analyzed validation set is long-only or short-only."""
    if "side" not in frame.columns:
        return "long"
    non_null = frame["side"].dropna().astype(str)
    if non_null.empty:
        return "long"
    return non_null.mode().iat[0].lower()


def summarize_count_dict(series: pd.Series, top_n: int = 3) -> str:
    """Convert a value-count series into a compact `key=count` summary."""
    if series.empty:
        return "none"
    items = []
    for key, value in series.head(top_n).items():
        items.append(f"{key}={int(value)}")
    return ", ".join(items)


def build_cluster_label(row: pd.Series) -> str:
    """
    Build a short cluster label that groups related survivor neighborhoods.

    This keeps the report easy to read without hard-coding only one exact family.
    """

    label = (
        f"{row['source_symbol']} | "
        f"fib={row['fib_band']:.3f} | "
        f"rw_lb={int(row['rw_lookback'])}"
    )
    if "confirm_enabled" in row.index and bool(row["confirm_enabled"]):
        label += (
            f" | 4h_ema={int(row['confirm_ema_period'])}"
            f" | 4h_dist={float(row['confirm_min_distance']):.3f}"
        )
    return label


def build_candidate_note(row: pd.Series, top_score: float) -> str:
    """
    Generate a short human-style note for each survivor.

    This is the "AI brain" layer: simple but useful heuristics that turn the raw
    metrics into plain-English guidance.
    """

    notes: List[str] = []

    if math.isclose(float(row["composite_score"]), top_score, abs_tol=1e-9):
        notes.append("Best overall balance in the survivor pool.")
    if bool(row["best_expectancy_flag"]):
        notes.append("Highest expectancy of all survivors.")
    if bool(row["best_win_rate_flag"]):
        notes.append("Highest win rate of all survivors.")
    if bool(row["best_drawdown_flag"]):
        notes.append("Tightest trailing drawdown control.")
    if bool(row["best_consistency_flag"]):
        notes.append("Safest consistency profile.")
    if float(row["consistency_headroom_pct_pts"]) < 1.0:
        notes.append("Very close to the 20% consistency ceiling.")
    if float(row["drawdown_headroom_pct_pts"]) < 0.5:
        notes.append("Limited drawdown headroom below the 3% trailing cap.")
    if int(row["metric_duplicate_count"]) > 1:
        notes.append("Shares identical outcome metrics with another survivor; treat as a threshold duplicate.")
    if "confirm_enabled" in row.index and bool(row["confirm_enabled"]):
        notes.append(
            f"Uses a 4H confirmation filter with EMA {int(row['confirm_ema_period'])} "
            f"and minimum distance {float(row['confirm_min_distance']):.3f}."
        )
    if not notes:
        notes.append("Balanced survivor with no obvious structural warning.")

    return " ".join(notes)


def build_markdown_table(frame: pd.DataFrame) -> str:
    """Render a markdown table without adding an extra dependency."""
    headers = list(frame.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in frame.iterrows():
        values = [str(row[column]) for column in headers]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def prepare_survivor_ranking(validation_path: str, shortlist_path: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Build the full analysis frames:
    - ranking_df: one row per survivor with composite scoring and notes
    - asset_stats: source-asset performance across the full evaluated set
    - validation_df: the original full validation table, reused for context
    """

    if not os.path.exists(validation_path):
        raise FileNotFoundError(f"Validation results not found: {validation_path}")
    if not os.path.exists(shortlist_path):
        raise FileNotFoundError(f"Shortlist file not found: {shortlist_path}")

    validation_df = pd.read_csv(validation_path)
    shortlist_df = pd.read_csv(shortlist_path)

    survivors = validation_df.loc[validation_df["overall_survival"] == True].copy()
    if survivors.empty:
        raise ValueError("No survivors found in the validation results.")

    # Merge with the candidate file so the exact original row is always available.
    if "param_id" in survivors.columns and "param_id" in shortlist_df.columns:
        survivors = survivors.merge(
            shortlist_df,
            on="param_id",
            how="left",
            suffixes=("", "_candidate"),
        )
    elif "rank" in survivors.columns and "backtrader_rank" in shortlist_df.columns:
        survivors = survivors.merge(
            shortlist_df,
            left_on="rank",
            right_on="backtrader_rank",
            how="left",
            suffixes=("", "_candidate"),
        )
    elif "rank" in survivors.columns and "combined_rank" in shortlist_df.columns:
        survivors = survivors.merge(
            shortlist_df,
            left_on="rank",
            right_on="combined_rank",
            how="left",
            suffixes=("", "_candidate"),
        )
    else:
        raise ValueError("Could not find compatible merge keys between validation results and candidate file.")

    # Normalize the four ranking dimensions.
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

    # These headroom columns make the prop-firm constraints easier to reason about.
    survivors["drawdown_headroom_pct_pts"] = 3.0 - survivors["max_dd_pct"]
    survivors["consistency_headroom_pct_pts"] = 20.0 - survivors["consistency_score"]

    # Detect exact-metric duplicates among the survivors.
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

    survivors["cluster_label"] = survivors.apply(build_cluster_label, axis=1)
    survivors["cluster_size"] = survivors.groupby("cluster_label")["rank"].transform("size")

    # Flags for quick report writing.
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

    # Asset-level context shows which source-asset parameter families held up best.
    asset_stats = (
        validation_df.groupby("source_symbol", dropna=False)
        .agg(
            candidates_tested=("rank", "size"),
            survivors=("overall_survival", "sum"),
            median_expectancy=("expectancy", "median"),
            best_expectancy=("expectancy", "max"),
            median_max_dd_pct=("max_dd_pct", "median"),
            best_win_rate=("win_rate", "max"),
        )
        .reset_index()
    )
    asset_stats["survival_rate_pct"] = 100.0 * asset_stats["survivors"] / asset_stats["candidates_tested"]
    asset_stats = asset_stats.sort_values(
        by=["survivors", "survival_rate_pct", "best_expectancy"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    return survivors, asset_stats, validation_df


def write_report(
    report_path: str,
    ranking_df: pd.DataFrame,
    asset_stats: pd.DataFrame,
    validation_df: pd.DataFrame,
) -> None:
    """Write the detailed survivor report in markdown."""

    survivors = ranking_df.copy()
    has_confirmation = has_confirmation_columns(survivors)
    strategy_side = infer_strategy_side(validation_df)
    source_distribution = survivors.groupby("source_symbol").size().sort_values(ascending=False)
    parameter_counts = {
        "sma": survivors["sma"].value_counts().to_dict(),
        "fib_band": survivors["fib_band"].round(3).value_counts().to_dict(),
        "rw_lookback": survivors["rw_lookback"].value_counts().to_dict(),
        "eb": survivors["eb"].round(3).value_counts().to_dict(),
    }
    if has_confirmation:
        parameter_counts["confirm_ema_period"] = survivors["confirm_ema_period"].value_counts().to_dict()
        parameter_counts["confirm_min_distance"] = survivors["confirm_min_distance"].round(3).value_counts().to_dict()

    top_table = survivors[
        [
            "analysis_rank",
            "param_id",
            "source_symbol",
            *(
                ["confirm_ema_period", "confirm_min_distance"]
                if has_confirmation
                else []
            ),
            "win_rate",
            "expectancy",
            "max_dd_pct",
            "consistency_score",
            "composite_score",
        ]
    ].copy()

    asset_table = asset_stats[
        [
            "source_symbol",
            "candidates_tested",
            "survivors",
            "survival_rate_pct",
            "best_expectancy",
            "median_max_dd_pct",
        ]
    ].copy()

    top_five_ids = survivors.head(5)["param_id"].tolist()
    top_five_source_counts = survivors.head(5)["source_symbol"].value_counts().to_dict()
    high_risk_survivors = survivors.loc[survivors["consistency_headroom_pct_pts"] < 2.0].copy()
    duplicate_survivors = survivors.loc[survivors["metric_duplicate_count"] > 1].copy()
    dominant_source = source_distribution.index[0]
    dominant_source_count = int(source_distribution.iloc[0])
    tested_winner = asset_stats.iloc[0]["source_symbol"]
    source_summary = summarize_count_dict(source_distribution)
    sma_summary = summarize_count_dict(survivors["sma"].value_counts())
    fib_summary = summarize_count_dict(survivors["fib_band"].round(3).value_counts())
    rw_summary = summarize_count_dict(survivors["rw_lookback"].value_counts())
    eb_summary = summarize_count_dict(survivors["eb"].round(3).value_counts())

    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write("# Backtrader Survivor Analysis Report\n\n")
        handle.write("## Overview\n\n")
        handle.write(f"- **strategy_side**: {strategy_side}-only\n")
        handle.write(f"- **survivors_found**: {len(survivors)}\n")
        handle.write(f"- **source_assets_with_survivors**: {', '.join(source_distribution.index.tolist())}\n")
        handle.write(f"- **best_overall_candidate**: {survivors.iloc[0]['param_id']}\n")
        handle.write(f"- **best_expectancy**: {survivors['expectancy'].max():.4f}\n")
        handle.write(f"- **best_win_rate**: {survivors['win_rate'].max():.4f}\n")
        handle.write(f"- **lowest_max_dd_pct**: {survivors['max_dd_pct'].min():.4f}\n")
        handle.write(f"- **best_consistency_score**: {survivors['consistency_score'].min():.4f}\n")
        if has_confirmation:
            handle.write("- **confirmation_layer**: 4H EMA-distance filter active in this run\n")

        handle.write("\n## Ranking Table\n\n")
        handle.write(build_markdown_table(top_table.round(4)))
        handle.write("\n")

        handle.write("\n## Source Asset Analysis\n\n")
        handle.write("These stats use the full validation set, not just the survivors, so they show which source-asset parameter families held up best under chronological testing.\n\n")
        handle.write(build_markdown_table(asset_table.round(4)))
        handle.write("\n")

        handle.write("\n## Parameter Pattern Analysis\n\n")
        handle.write(f"- **SMA distribution**: {parameter_counts['sma']}\n")
        handle.write(f"- **Fib band distribution**: {parameter_counts['fib_band']}\n")
        handle.write(f"- **RW lookback distribution**: {parameter_counts['rw_lookback']}\n")
        handle.write(f"- **EMA buffer distribution**: {parameter_counts['eb']}\n")
        if has_confirmation:
            handle.write(f"- **4H EMA period distribution**: {parameter_counts['confirm_ema_period']}\n")
            handle.write(f"- **4H minimum distance distribution**: {parameter_counts['confirm_min_distance']}\n")
        handle.write(
            f"- **Interpretation**: survivor concentration by source family is {source_summary}. "
            f"The dominant family is {dominant_source} with {dominant_source_count} survivors.\n"
        )
        handle.write(
            f"- **Interpretation**: the parameter surface that held up best in chronological testing stayed centered around "
            f"SMA ({sma_summary}), fib band ({fib_summary}), rw lookback ({rw_summary}), and EMA buffer ({eb_summary}).\n"
        )
        if not duplicate_survivors.empty:
            handle.write(
                f"- **Interpretation**: {len(duplicate_survivors)} survivors share an exact outcome signature with at least one neighbor, "
                "so they should be treated as threshold variants instead of independent strategies.\n"
            )
        if has_confirmation:
            handle.write("- **Interpretation**: the 4H layer should be read as a trade-quality gate, so lower trade counts are acceptable if expectancy, drawdown control, or consistency improve materially.\n")

        handle.write("\n## Survivor-by-Survivor Detail\n\n")
        for _, row in survivors.iterrows():
            parameter_line = (
                f"SMA={int(row['sma'])}, EMA={int(row['ema'])}, fib_floor={row['fib_floor']:.3f}, "
                f"fib_band={row['fib_band']:.3f}, rw={row['rw']:.3f}, eb={row['eb']:.3f}, "
                f"rw_lookback={int(row['rw_lookback'])}"
            )
            if has_confirmation and bool(row["confirm_enabled"]):
                parameter_line += (
                    f", confirm_mode={row['confirm_mode']}, "
                    f"confirm_ema_period={int(row['confirm_ema_period'])}, "
                    f"confirm_min_distance={float(row['confirm_min_distance']):.3f}"
                )

            handle.write(f"### {int(row['analysis_rank'])}. {row['param_id']}\n\n")
            handle.write(f"- **source_symbol**: {row['source_symbol']}\n")
            handle.write(f"- **exact_parameters**: {parameter_line}\n")
            handle.write(f"- **cluster_label**: {row['cluster_label']} (cluster size {int(row['cluster_size'])})\n")
            handle.write(f"- **backtrader_metrics**: total_trades={int(row['total_trades'])}, win_rate={row['win_rate']:.4f}, expectancy={row['expectancy']:.4f}, max_dd_pct={row['max_dd_pct']:.4f}, consistency_score={row['consistency_score']:.4f}\n")
            handle.write(f"- **headroom**: drawdown_headroom={row['drawdown_headroom_pct_pts']:.4f} pct points, consistency_headroom={row['consistency_headroom_pct_pts']:.4f} pct points\n")
            handle.write(f"- **composite_score**: {row['composite_score']:.2f}\n")
            handle.write(f"- **ai_note**: {row['ai_note']}\n")
            handle.write("\n")

        handle.write("## AI Conclusions\n\n")
        handle.write(f"- **Best source asset family**: {tested_winner} by survivor count / survival rate across the tested pool, while the strongest single candidate is {survivors.iloc[0]['param_id']}.\n")
        handle.write(f"- **Top deployment shortlist**: {', '.join(top_five_ids)}\n")
        handle.write(
            f"- **Practical view**: the top 5 is concentrated by source family as {top_five_source_counts}. "
            "That concentration is useful signal, but it also means we should watch for redundant parameter neighbors when promoting finalists.\n"
        )
        if not duplicate_survivors.empty:
            handle.write(
                f"- **Deduplication view**: {len(duplicate_survivors)} survivors share identical outcome signatures with at least one neighbor. "
                "Treat those as parameter-threshold variants rather than fully independent strategies when building the final shortlist.\n"
            )
        if not high_risk_survivors.empty:
            handle.write(
                f"- **Risk view**: {len(high_risk_survivors)} survivors sit within 2 percentage points of the 20% consistency ceiling. "
                "Those are usable reserve candidates, but they should rank behind the cleaner AVAX and early ETH variants.\n"
            )
        else:
            handle.write("- **Risk view**: none of the survivors are pressing tightly against the 20% consistency ceiling, which is a good sign for portfolio robustness.\n")


def main() -> None:
    """Run the full survivor analysis workflow."""
    args = parse_args()

    ranking_df, asset_stats, validation_df = prepare_survivor_ranking(
        validation_path=args.validation_results,
        shortlist_path=args.shortlist,
    )

    ranking_df.to_csv(args.ranking_csv, index=False)
    asset_stats.to_csv(args.asset_stats_csv, index=False)
    write_report(
        report_path=args.report_md,
        ranking_df=ranking_df,
        asset_stats=asset_stats,
        validation_df=validation_df,
    )

    print(f"Survivors analyzed: {len(ranking_df)}")
    print(f"Ranking CSV: {args.ranking_csv}")
    print(f"Asset stats CSV: {args.asset_stats_csv}")
    print(f"Report MD: {args.report_md}")


if __name__ == "__main__":
    main()
