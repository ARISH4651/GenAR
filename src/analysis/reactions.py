"""
src/analysis/reactions.py

Deterministic reaction frequency analysis.

Reaction analysis operates at the REACTION ROW level — not the case level.
Each row represents one adverse reaction for one case.
A case with 3 reaction rows contributes 3 reaction records.

Two analyses:
  1. All reactions — top N MedDRA PTs across all rows.
  2. Serious reactions — top N MedDRA PTs from serious-case rows only.

SOC-level analysis is NOT performed: no System Organ Class field exists
in the dataset. Only MedDRA Preferred Term (PT) is available.
"""

from __future__ import annotations

import pandas as pd

from src.config.settings import CASE_ID_FIELD, REACTION_FIELD


def compute_reactions(df: pd.DataFrame, case_df: pd.DataFrame, top_n: int = 20) -> dict:
    """
    Compute reaction frequency tables.

    Args:
        df:       Clean normalised DataFrame from the validator (row level).
        case_df:  Case-level aggregated DataFrame.
        top_n:    How many top reactions to include in each table.

    Returns a dict keyed for reactions.json.
    Percentages are computed over total reaction rows (not total cases),
    since one case may contribute multiple reaction rows.
    """
    total_reaction_rows = len(df)

    # --- All reactions ---
    all_counts = df[REACTION_FIELD].value_counts(dropna=True)
    top_reactions = _build_reaction_table(all_counts, total_reaction_rows, top_n)

    # --- Serious reactions only ---
    # Determine serious case IDs from case_df
    serious_case_ids = set(case_df[case_df["is_serious"] == True][CASE_ID_FIELD])
    
    # Filter reaction records belonging to those cases
    serious_df = df[df[CASE_ID_FIELD].isin(serious_case_ids)]
    serious_total = len(serious_df)
    serious_counts = serious_df[REACTION_FIELD].value_counts(dropna=True)
    top_serious_reactions = _build_reaction_table(
        serious_counts, serious_total, top_n
    )

    return {
        "aggregation_level": "reaction_record",
        "total_reaction_rows": total_reaction_rows,
        "unique_reaction_pts": int(df[REACTION_FIELD].nunique()),
        "top_reactions": top_reactions,
        "top_serious_reactions": top_serious_reactions,
        "serious_reaction_rows": serious_total,
        "soc_analysis_available": False,
        "soc_analysis_note": (
            "No System Organ Class (SOC) field is present in the dataset. "
            "Only MedDRA Preferred Term (PT) is available. "
            "SOC-level grouping is out of scope for this version."
        ),
        "analysis_note": (
            f"Reaction frequencies computed at row level (N={total_reaction_rows} rows). "
            "Each row = one reaction. A case with multiple reactions contributes "
            "one row per reaction. Percentages are of total reaction rows."
        ),
    }


def _build_reaction_table(
    counts: pd.Series,
    total: int,
    top_n: int,
) -> list[dict]:
    """Convert a value_counts Series into a list of dicts with percentages."""
    rows = []
    for pt, count in counts.head(top_n).items():
        rows.append({
            "reaction_pt": str(pt),
            "count": int(count),
            "percent_of_reactions": round(float(count) / total * 100, 2) if total > 0 else 0.0,
        })
    return rows
