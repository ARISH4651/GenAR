"""
src/analysis/trends.py

Deterministic temporal trend analysis: case counts by month.

CASE GRAIN: Monthly counts are of UNIQUE CASES — not reaction rows.
A case received in March contributes 1 to March's count regardless of
how many reaction rows it has.

Date field: report_date (datetime64, already parsed by Excel/openpyxl).
If report_date is null for a row, that row is excluded from trend analysis.

OBSERVATION vs INTERPRETATION:
The numbers produced here are observations — "N cases were received in
month X." Interpretation of whether any pattern constitutes a safety
signal requires qualified human review. The LLM must not automatically
label a numerical trend as a safety signal.
"""

from __future__ import annotations

import pandas as pd

from src.config.settings import CASE_ID_FIELD, DATE_FIELD


def compute_trends(df: pd.DataFrame) -> dict:
    """
    Compute monthly case counts over the reporting period.

    Returns a dict keyed for trends.json.
    """
    # Deduplicate to case level — one row per case
    # Use the first occurrence of each case (all rows for a case share the same date)
    case_dates = (
        df[[CASE_ID_FIELD, DATE_FIELD]]
        .drop_duplicates(subset=CASE_ID_FIELD)
        .copy()
    )

    # Parse to datetime, drop any invalid
    case_dates[DATE_FIELD] = pd.to_datetime(case_dates[DATE_FIELD], errors="coerce")
    valid = case_dates[case_dates[DATE_FIELD].notna()].copy()
    excluded = len(case_dates) - len(valid)

    # Build year-month period string
    valid["year_month"] = valid[DATE_FIELD].dt.to_period("M").astype(str)

    # Count cases per month
    monthly = (
        valid.groupby("year_month")[CASE_ID_FIELD]
        .count()
        .reset_index()
        .rename(columns={CASE_ID_FIELD: "count"})
        .sort_values("year_month")
    )

    monthly_list = [
        {"year_month": str(row["year_month"]), "count": int(row["count"])}
        for _, row in monthly.iterrows()
    ]

    period_start = str(valid[DATE_FIELD].min().date()) if not valid.empty else "unknown"
    period_end = str(valid[DATE_FIELD].max().date()) if not valid.empty else "unknown"

    return {
        "reporting_period_start": period_start,
        "reporting_period_end": period_end,
        "total_cases_in_trend": int(len(valid)),
        "cases_excluded_missing_date": excluded,
        "monthly_case_counts": monthly_list,
        "date_field_used": DATE_FIELD,
        "trend_note": (
            "Monthly counts are of unique cases (unique safetyreportid). "
            "Reaction rows for the same case do not inflate monthly counts. "
            "Numerical trends are observations only. "
            "Signal assessment requires qualified human review."
        ),
    }
