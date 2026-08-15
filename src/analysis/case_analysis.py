"""
src/analysis/case_analysis.py

Deterministic case-level counts: total, serious, non-serious, expedited.

IMPORTANT: All metrics here are computed on UNIQUE safetyreportid values.
  - 1,068 rows != 1,068 cases.
  - A case with 3 reaction rows must be counted ONCE.
"""

from __future__ import annotations

import pandas as pd

from src.config.settings import (
    CASE_ID_FIELD,
    DATE_FIELD,
    EXPEDITE_FIELD,
    REACTION_FIELD,
    SERIOUS_FIELD,
    SERIOUS_VALUE,
    NOT_SERIOUS_VALUE,
    EXPEDITE_YES,
)


def compute_case_summary(df: pd.DataFrame, case_df: pd.DataFrame) -> dict:
    """
    Compute case-level summary statistics.

    Returns a dict keyed for case_summary.json.
    All counts use unique safetyreportid — not row count.
    """
    # Cases with more than one reaction row
    rows_per_case = df.groupby(CASE_ID_FIELD).size()
    multi_reaction_cases = int((rows_per_case > 1).sum())

    # Reporting period from the primary date field
    dates = pd.to_datetime(case_df[DATE_FIELD], errors="coerce").dropna()
    period_start = str(dates.min().date()) if not dates.empty else "unknown"
    period_end = str(dates.max().date()) if not dates.empty else "unknown"

    serious_cases = int(case_df["is_serious"].sum())
    non_serious_cases = int(len(case_df) - serious_cases)

    expedited = int(case_df["is_alert"].sum())
    non_expedited = int(len(case_df) - expedited)

    return {
        "total_rows": int(len(df)),
        "total_cases": int(len(case_df)),
        "serious_cases": serious_cases,
        "non_serious_cases": non_serious_cases,
        "expedited_cases": expedited,
        "non_expedited_cases": non_expedited,
        "cases_with_multiple_reactions": multi_reaction_cases,
        "unique_reaction_pts": int(df[REACTION_FIELD].nunique()),
        "reporting_period_start": period_start,
        "reporting_period_end": period_end,
        "analysis_note": (
            "Case-level metrics derived from unique safetyreportid. "
            f"The dataset contains {len(df)} rows representing {len(case_df)} unique cases. "
            "The difference arises from cases with multiple reaction rows."
        ),
    }
