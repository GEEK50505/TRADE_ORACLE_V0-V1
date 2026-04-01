"""
Build the combined long + short candidate matrix for the final portfolio study.

This script reads the presentation-friendly long and short shortlist files,
resolves their full parameter rows from the richer survivor-ranking CSVs, and
emits one combined candidate row per long/short pair.

Recommended usage:
    python scripts/build_combined_candidates.py
"""

from __future__ import annotations

import argparse
import os
from itertools import product
from typing import Dict, List

import pandas as pd


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

DEFAULT_LONG_SHORTLIST = os.path.join(RESULTS_DIR, "backtrader_4h_final_shortlist.csv")
DEFAULT_SHORT_SHORTLIST = os.path.join(RESULTS_DIR, "backtrader_short_4h_final_shortlist.csv")
DEFAULT_LONG_RANKING = os.path.join(RESULTS_DIR, "backtrader_4h_survivor_ranking.csv")
DEFAULT_SHORT_RANKING = os.path.join(RESULTS_DIR, "backtrader_short_4h_survivor_ranking.csv")
DEFAULT_OUTPUT_CSV = os.path.join(RESULTS_DIR, "backtrader_combined_candidates.csv")


def parse_args() -> argparse.Namespace:
    """Expose the shortlist/ranking paths for the combined build step."""
    parser = argparse.ArgumentParser(description="Build the combined long + short candidate matrix.")
    parser.add_argument("--long-shortlist", default=DEFAULT_LONG_SHORTLIST)
    parser.add_argument("--short-shortlist", default=DEFAULT_SHORT_SHORTLIST)
    parser.add_argument("--long-ranking", default=DEFAULT_LONG_RANKING)
    parser.add_argument("--short-ranking", default=DEFAULT_SHORT_RANKING)
    parser.add_argument("--output-csv", default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--long-top-n", type=int, default=5)
    parser.add_argument("--short-top-n", type=int, default=5)
    return parser.parse_args()


def load_csv(path: str) -> pd.DataFrame:
    """Read a CSV and fail loudly if it is missing or empty."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required file not found: {path}")
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f"Required file is empty: {path}")
    return frame


def top_n_shortlist(frame: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """Keep the shortlist order stable and trim to the requested top-N rows."""
    ordered = frame.copy().reset_index(drop=True)
    if "shortlist_priority" not in ordered.columns:
        ordered.insert(0, "shortlist_priority", range(1, len(ordered) + 1))
    return ordered.head(max(1, int(top_n))).copy().reset_index(drop=True)


def ensure_param_lookup(frame: pd.DataFrame, name: str) -> Dict[str, pd.Series]:
    """Build a one-row-per-param_id lookup and reject duplicates early."""
    if "param_id" not in frame.columns:
        raise ValueError(f"{name} is missing the required `param_id` column.")

    duplicated = frame["param_id"].duplicated(keep=False)
    if duplicated.any():
        duplicate_ids = sorted(frame.loc[duplicated, "param_id"].astype(str).unique().tolist())
        raise ValueError(f"{name} contains duplicate param_id values: {duplicate_ids}")

    return {str(row["param_id"]): row for _, row in frame.iterrows()}


def resolve_full_rows(
    shortlist: pd.DataFrame,
    ranking_lookup: Dict[str, pd.Series],
    side_label: str,
) -> List[Dict[str, object]]:
    """
    Resolve each shortlist row into the full ranking row we need for validation.

    The shortlist CSVs are intentionally compact, so we use the ranking tables as
    the source of truth for the full parameter block.
    """

    resolved_rows: List[Dict[str, object]] = []
    for _, short_row in shortlist.iterrows():
        param_id = str(short_row["param_id"])
        if param_id not in ranking_lookup:
            raise KeyError(f"{side_label} shortlist param_id not found in ranking file: {param_id}")

        full_row = ranking_lookup[param_id]
        resolved = full_row.to_dict()
        resolved["shortlist_priority"] = int(short_row["shortlist_priority"])
        resolved["shortlist_role"] = str(short_row.get("shortlist_role", "unspecified"))
        resolved["shortlist_rationale"] = str(short_row.get("shortlist_rationale", ""))
        resolved_rows.append(resolved)

    return resolved_rows


def build_pair_row(
    pair_rank: int,
    long_row: Dict[str, object],
    short_row: Dict[str, object],
) -> Dict[str, object]:
    """Flatten one long/short pair into a combined candidate row."""

    long_param_id = str(long_row["param_id"])
    short_param_id = str(short_row["param_id"])
    pair_id = f"combined__{long_param_id}__{short_param_id}"

    row: Dict[str, object] = {
        "combined_rank": int(pair_rank),
        "param_id": pair_id,
        "long_param_id": long_param_id,
        "short_param_id": short_param_id,
        "long_analysis_rank": int(long_row.get("analysis_rank", long_row.get("rank", 0))),
        "short_analysis_rank": int(short_row.get("analysis_rank", short_row.get("rank", 0))),
        "long_shortlist_priority": int(long_row["shortlist_priority"]),
        "short_shortlist_priority": int(short_row["shortlist_priority"]),
        "long_shortlist_role": str(long_row.get("shortlist_role", "unspecified")),
        "short_shortlist_role": str(short_row.get("shortlist_role", "unspecified")),
        "pair_family": f"{long_row['source_symbol']} + {short_row['source_symbol']}",
    }

    for prefix, source in [("long", long_row), ("short", short_row)]:
        row[f"{prefix}_source_symbol"] = str(source["source_symbol"])
        row[f"{prefix}_side"] = str(source.get("side", prefix))
        row[f"{prefix}_sma"] = int(source["sma"])
        row[f"{prefix}_ema"] = int(source["ema"])
        row[f"{prefix}_fib_floor"] = float(source["fib_floor"])
        row[f"{prefix}_fib_band"] = float(source["fib_band"])
        row[f"{prefix}_rw"] = float(source["rw"])
        row[f"{prefix}_eb"] = float(source["eb"])
        row[f"{prefix}_rw_lookback"] = int(source["rw_lookback"])
        row[f"{prefix}_confirm_enabled"] = bool(source.get("confirm_enabled", False))
        row[f"{prefix}_confirm_mode"] = str(source.get("confirm_mode", "disabled"))
        row[f"{prefix}_confirm_ema_period"] = int(source.get("confirm_ema_period", 20))
        row[f"{prefix}_confirm_min_distance"] = float(source.get("confirm_min_distance", 0.0))
        row[f"{prefix}_shortlist_rationale"] = str(source.get("shortlist_rationale", ""))

    return row


def main() -> None:
    """Resolve the long/short finalists and export the 25-pair combined matrix."""
    args = parse_args()

    long_shortlist = top_n_shortlist(load_csv(args.long_shortlist), args.long_top_n)
    short_shortlist = top_n_shortlist(load_csv(args.short_shortlist), args.short_top_n)

    long_lookup = ensure_param_lookup(load_csv(args.long_ranking), "long ranking")
    short_lookup = ensure_param_lookup(load_csv(args.short_ranking), "short ranking")

    resolved_longs = resolve_full_rows(long_shortlist, long_lookup, side_label="long")
    resolved_shorts = resolve_full_rows(short_shortlist, short_lookup, side_label="short")

    pair_rows: List[Dict[str, object]] = []
    pair_rank = 0
    for long_row, short_row in product(resolved_longs, resolved_shorts):
        pair_rank += 1
        pair_rows.append(build_pair_row(pair_rank=pair_rank, long_row=long_row, short_row=short_row))

    output_df = pd.DataFrame(pair_rows)
    output_df.to_csv(args.output_csv, index=False)

    print(f"Combined candidate CSV: {args.output_csv}")
    print(f"Long finalists used: {len(resolved_longs)}")
    print(f"Short finalists used: {len(resolved_shorts)}")
    print(f"Pair portfolios generated: {len(output_df)}")


if __name__ == "__main__":
    main()
