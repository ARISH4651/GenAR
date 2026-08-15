"""
src/analysis/demographics.py

Deterministic patient demographics: sex and age-group breakdown.

Both sex and age are PATIENT-LEVEL attributes. They repeat across
multi-reaction rows for the same case. We deduplicate by safetyreportid
before counting so each patient is counted exactly once.

Age derivation method:
  1. Use patient_patientonsetage (numeric).
  2. Convert to years using patient_patientonsetageunit
     (year=as-is, month÷12, week÷52, day÷365).
  3. Unit code '800' and missing units-without-age → Unknown bucket.
  4. patient_patientagegroup is 97% blank — not used.
  All bucketing is done by the validator's normalisation layer (norm_age_group).
"""

from __future__ import annotations

import pandas as pd

from src.config.settings import AGE_BUCKETS, AGE_UNKNOWN_LABEL, CASE_ID_FIELD


def compute_demographics(df: pd.DataFrame, case_df: pd.DataFrame) -> dict:
    """
    Compute sex and age-group distributions at the case/patient level.

    Returns a dict keyed for demographics.json.
    """
    total_cases = len(case_df)

    # --- Sex breakdown ---
    sex_raw = case_df["patient_patientsex"].fillna("unknown")
    sex_counts = sex_raw.value_counts(dropna=False)
    sex_breakdown = {
        str(k): int(v) for k, v in sex_counts.items()
    }
    sex_missing = int(case_df["patient_patientsex"].isna().sum())

    # --- Age group breakdown ---
    # norm_age_group was computed by the validator from patient_patientonsetage
    age_group_counts = case_df["norm_age_group"].value_counts(dropna=False)
    age_group_breakdown = {
        str(k): int(v) for k, v in age_group_counts.items()
    }
    # Ensure all buckets appear (even zero-count ones)
    for label, _, _ in AGE_BUCKETS:
        if label not in age_group_breakdown:
            age_group_breakdown[label] = 0
    if AGE_UNKNOWN_LABEL not in age_group_breakdown:
        age_group_breakdown[AGE_UNKNOWN_LABEL] = 0

    age_missing = int(case_df["norm_age_years"].isna().sum())

    # --- Country breakdown (using norm_country with fallback applied) ---
    country_raw = case_df["norm_country"].fillna("unknown")
    country_counts = country_raw.value_counts(dropna=False)
    country_breakdown = {str(k): int(v) for k, v in country_counts.items()}
    country_missing = int(case_df["norm_country"].isna().sum())

    return {
        "total_cases_analysed": total_cases,
        "sex_breakdown": sex_breakdown,
        "sex_missing_cases": sex_missing,
        "age_group_breakdown": age_group_breakdown,
        "age_missing_cases": age_missing,
        "age_derivation_method": (
            "patient_patientonsetage converted to years using "
            "patient_patientonsetageunit (year/month/week/day). "
            "Unit code '800' and unrecognised units treated as Unknown. "
            "patient_patientagegroup not used (97.1% missing)."
        ),
        "age_buckets": [label for label, _, _ in AGE_BUCKETS] + [AGE_UNKNOWN_LABEL],
        "country_breakdown": country_breakdown,
        "country_missing_cases": country_missing,
        "country_field_used": "occurcountry (with primarysource_reportercountry fallback for 7 missing cases)",
        "country_note": "Value 'eu' is a regional code, not a specific country. See limitations.json.",
        "analysis_note": (
            "Sex and age counted at case level (unique safetyreportid). "
            "Multi-reaction cases counted once per patient."
        ),
    }
