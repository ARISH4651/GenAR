"""
src/analysis/case_table.py

Builds an explicit case-level table from the raw row-level dataset.
Resolves case-level metrics (seriousness, demographics, alerts) by aggregating across rows.
"""

import pandas as pd

from src.config.settings import (
    CASE_ID_FIELD,
    CRITERION_YES,
    DATE_FIELD,
    EXPEDITE_FIELD,
    EXPEDITE_YES,
    SERIOUSNESS_CRITERIA,
    COUNTRY_FIELD,
)

def build_case_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a case-level DataFrame.
    Each unique CASE_ID_FIELD gets exactly one row.
    Seriousness criteria are stored as booleans (True/False).
    """
    # Keep all fields by taking the first row of each case
    case_df = df.drop_duplicates(subset=CASE_ID_FIELD).copy()

    # Build boolean columns for seriousness criteria via groupby
    # This avoids assigning booleans into string-typed columns
    criteria_bools = {}
    for crit in SERIOUSNESS_CRITERIA:
        # For each case, True if ANY row has the criterion == "yes"
        crit_series = (
            df.groupby(CASE_ID_FIELD)[crit]
            .apply(lambda g: (g.astype(str).str.lower() == CRITERION_YES).any())
        )
        criteria_bools[crit] = crit_series

    # is_serious = True if ANY criterion is met for that case
    criteria_df = pd.DataFrame(criteria_bools)
    criteria_df["is_serious"] = criteria_df.any(axis=1)

    # is_alert via expedite field
    alert_series = (
        df.groupby(CASE_ID_FIELD)[EXPEDITE_FIELD]
        .apply(lambda g: (g.astype(str).str.lower() == EXPEDITE_YES).any())
    )
    criteria_df["is_alert"] = alert_series

    # Drop old string columns and merge boolean versions
    case_df = case_df.set_index(CASE_ID_FIELD)
    for crit in SERIOUSNESS_CRITERIA:
        if crit in case_df.columns:
            case_df.drop(columns=crit, inplace=True)

    case_df = case_df.join(criteria_df)
    return case_df.reset_index()

