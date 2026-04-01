"""
Chronological Backtrader validation for the short Daily + 4H confirmation set.

This script intentionally reuses the validated short-side Backtrader engine from
`backtrader_evaluate_short.py`. The underlying engine already supports:
- short-side signal logic,
- short-side 4H confirmation fields,
- Maven risk sizing and portfolio rules,
- mixed Daily + 4H feeds, and
- short-side stop / scale-out accounting.

Why this wrapper exists:
- It gives the short 4H phase its own clean entrypoint and default output names.
- It keeps the run order symmetric with the long 4H phase.
- It avoids duplicating a large, already-working validator implementation.

Recommended full run:
    python scripts/backtrader_evaluate_short_4h.py

Helpful smoke test:
    python scripts/backtrader_evaluate_short_4h.py --limit 3 --output-prefix results/backtrader_short_4h_smoke
"""

from __future__ import annotations

import argparse
import os

from backtrader_evaluate_short import (
    DEFAULT_DAILY_PATH,
    DEFAULT_INTRADAY_PATH,
    MarketDataCatalog,
    evaluate_candidates,
    load_candidates,
    select_candidates,
)


# ==============================================================================
# PATHS
# ==============================================================================

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

DEFAULT_CANDIDATES_PATH = os.path.join(RESULTS_DIR, "short_plus_4h_candidates.csv")
DEFAULT_OUTPUT_PREFIX = os.path.join(RESULTS_DIR, "backtrader_short_4h")


def retitle_summary(summary_path: str) -> None:
    """
    Rewrite the generic short summary title into a phase-specific 4H title.

    The shared evaluator already writes the correct metrics and confirmation info.
    This tiny post-processing step keeps the output filename and title aligned.
    """

    if not os.path.exists(summary_path):
        return

    with open(summary_path, "r", encoding="utf-8") as handle:
        text = handle.read()

    if text.startswith("# Backtrader short validation summary"):
        text = text.replace(
            "# Backtrader short validation summary",
            "# Backtrader short + 4H validation summary",
            1,
        )

    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write(text)


def parse_args() -> argparse.Namespace:
    """Define the CLI surface for the short + 4H validation phase."""
    parser = argparse.ArgumentParser(description="Chronological Backtrader validation for short Daily + 4H candidates.")
    parser.add_argument("--candidates", default=DEFAULT_CANDIDATES_PATH, help="Path to the short + 4H candidate CSV.")
    parser.add_argument("--daily-data", default=DEFAULT_DAILY_PATH, help="Path to the daily parquet file.")
    parser.add_argument(
        "--intraday-data",
        default=DEFAULT_INTRADAY_PATH,
        help="Path to the 4H parquet file used when intraday execution is available.",
    )
    parser.add_argument(
        "--output-prefix",
        default=DEFAULT_OUTPUT_PREFIX,
        help="Prefix for output files. Example: results/backtrader_short_4h",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional cap for smoke tests.")
    parser.add_argument("--start-rank", type=int, default=None, help="Optional inclusive candidate-rank lower bound.")
    parser.add_argument("--end-rank", type=int, default=None, help="Optional inclusive candidate-rank upper bound.")
    parser.add_argument(
        "--no-intraday",
        action="store_true",
        help="Force Daily-only validation even if 4H data exists.",
    )
    parser.add_argument(
        "--flush-every",
        type=int,
        default=10,
        help="Write partial CSV progress every N candidates.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the shared short evaluator with short + 4H defaults."""
    args = parse_args()

    candidates = load_candidates(args.candidates)
    candidates = select_candidates(candidates, args)

    catalog = MarketDataCatalog(daily_path=args.daily_data, intraday_path=args.intraday_data)

    output_csv = f"{args.output_prefix}_results.csv"
    summary_md = f"{args.output_prefix}_summary.md"

    results_df = evaluate_candidates(
        candidates=candidates,
        catalog=catalog,
        output_csv=output_csv,
        summary_md=summary_md,
        candidates_path=args.candidates,
        prefer_intraday=not args.no_intraday,
        flush_every=max(1, int(args.flush_every)),
    )

    # The shared engine writes the correct metrics already; this just gives the
    # markdown file the short + 4H phase label the user expects.
    retitle_summary(summary_md)

    survivors = int(results_df["overall_survival"].sum())
    print(f"Validation complete. Results: {output_csv}")
    print(f"Summary: {summary_md}")
    print(f"Candidates evaluated: {len(results_df)}")
    print(f"Survivors: {survivors}")


if __name__ == "__main__":
    main()
