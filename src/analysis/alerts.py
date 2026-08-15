"""
src/analysis/alerts.py

Deterministic 15-day alert and seriousness criteria analysis.

IMPORTANT design decisions documented here:

1. EXPEDITED FIELD
   fulfillexpeditecriteria == "yes" is used as the expedited/alert indicator.
   This field is taken at face value from the dataset.
   The analysis does NOT claim this field alone establishes every real-world
   regulatory requirement for a 15-day alert — a qualified reviewer must
   confirm regulatory obligations.

2. SERIOUSNESS CRITERIA
   The six criterion fields are INDEPENDENT yes/no flags:
     seriousnessdeath, seriousnesslifethreatening, seriousnesshospitalization,
     seriousnessdisabling, seriousnesscongenitalanomali, seriousnessother.
   A case may meet MULTIPLE criteria simultaneously.
   The sum of criterion counts will EXCEED the number of serious cases.
   These counts are NOT added together to derive the total serious case count.

3. CUMULATIVE COUNTS
   Prior-period data is not supplied. Cumulative counts are not computed.
"""

from __future__ import annotations

import pandas as pd

from src.config.settings import (
    CASE_ID_FIELD,
    CRITERION_YES,
    EXPEDITE_FIELD,
    EXPEDITE_YES,
    SERIOUSNESS_CRITERIA,
)

# Human-readable labels for the six criteria fields
CRITERIA_LABELS: dict[str, str] = {
    "seriousnessdeath": "Death",
    "seriousnesslifethreatening": "Life-threatening",
    "seriousnesshospitalization": "Hospitalisation",
    "seriousnessdisabling": "Disabling / incapacitating",
    "seriousnesscongenitalanomali": "Congenital anomaly",
    "seriousnessother": "Medically significant (other)",
}


def compute_alerts(df: pd.DataFrame, case_df: pd.DataFrame) -> dict:
    """
    Compute expedited case counts and seriousness criteria breakdown.

    Returns a dict keyed for alerts.json.
    All counts are at the case level (unique safetyreportid).
    """
    total_cases = int(len(case_df))

    expedited = int(case_df["is_alert"].sum())
    non_expedited = total_cases - expedited

    # Criteria breakdown — counts of cases meeting each criterion
    # Note: these counts are NOT mutually exclusive
    criteria_breakdown = []
    serious_cases = int(case_df["is_serious"].sum())
    
    for col in SERIOUSNESS_CRITERIA:
        count = int(case_df[col].sum())
        criteria_breakdown.append({
            "criterion_field": col,
            "criterion_label": CRITERIA_LABELS.get(col, col),
            "cases_meeting_criterion": count,
            "percent_of_serious_cases": round(
                float(count) / serious_cases * 100, 2
            ) if serious_cases > 0 else 0.0,
        })

    # Sort by count descending for readability
    criteria_breakdown.sort(key=lambda x: x["cases_meeting_criterion"], reverse=True)

    return {
        "total_cases": total_cases,
        "expedited_cases": expedited,
        "non_expedited_cases": non_expedited,
        "expedited_field_used": EXPEDITE_FIELD,
        "expedited_field_value": EXPEDITE_YES,
        "expedited_interpretation": "dataset_supplied_expedited_indicator",
        "seriousness_criteria_breakdown": criteria_breakdown,
        "criteria_overlap_note": (
            "Seriousness criteria are NOT mutually exclusive. "
            "A case may meet multiple criteria simultaneously. "
            "The sum of criterion counts will exceed the number of serious cases. "
            "Do not use criterion counts as the total serious case count."
        ),
        "cumulative_counts_note": (
            "Prior-period data not supplied. "
            "Cumulative counts are not available for this analysis."
        ),
    }
