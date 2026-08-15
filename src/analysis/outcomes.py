"""
src/analysis/outcomes.py

Deterministic reaction outcome distribution.

The raw outcome field (patient_reaction_reactionoutcome) is a
comma-concatenated string — e.g. "recovered/resolved,fatal" for a case
with two reactions that had different outcomes.

The validator's normalisation layer has already split this into a
list-per-row column: norm_outcomes.

This module explodes that list column so each outcome token becomes
its own row, then counts frequencies.

Outcome tokens observed in this dataset:
  - recovered/resolved
  - recovering/resolving
  - not recovered/not resolved/ongoing
  - fatal
  - unknown
"""

from __future__ import annotations

import pandas as pd


def compute_outcomes(df: pd.DataFrame) -> dict:
    """
    Compute outcome distribution across all reaction rows.

    Returns a dict keyed for outcomes.json.
    """
    total_reaction_rows = len(df)

    # Explode the norm_outcomes list column: one outcome token per row
    exploded = df["norm_outcomes"].explode()
    exploded = exploded.dropna()
    exploded = exploded[exploded != ""]

    total_outcome_tokens = len(exploded)
    outcome_counts = exploded.value_counts(dropna=True)

    outcomes_list = []
    for outcome, count in outcome_counts.items():
        outcomes_list.append({
            "outcome": str(outcome),
            "count": int(count),
            "percent_of_outcome_tokens": round(
                float(count) / total_outcome_tokens * 100, 2
            ) if total_outcome_tokens > 0 else 0.0,
        })

    # Sort by count descending
    outcomes_list.sort(key=lambda x: x["count"], reverse=True)

    return {
        "aggregation_level": "reaction_outcome_entry",
        "total_reaction_rows": total_reaction_rows,
        "total_outcome_entries": total_outcome_tokens,
        "outcomes": outcomes_list,
        "parsing_note": (
            "The raw outcome field contains comma-concatenated values "
            "(e.g. 'recovered/resolved,fatal' for a multi-reaction row). "
            "Each comma-separated token is counted individually. "
            "Total outcome tokens may exceed total reaction rows."
        ),
        "analysis_note": (
            "Outcome analysis is at the reaction-outcome token level. "
            "Percentages are of total outcome tokens, not of total cases."
        ),
    }
