"""
src/analysis/case_listing.py

Deterministic case index — one record per unique case with all
associated reactions and outcomes.

Purpose: enables a reviewer to trace any aggregate finding back to
individual cases. If a summary says "22 cases of Acute kidney injury",
the reviewer can look up those 22 cases in this listing.

For multi-reaction cases (where a case has > 1 reaction row),
all reaction PTs are collected into a list on the single case record.
"""

from __future__ import annotations

import pandas as pd

from src.config.settings import (
    CASE_ID_FIELD,
    CRITERION_YES,
    DATE_FIELD,
    REACTION_FIELD,
    SERIOUSNESS_CRITERIA,
)
from src.analysis.alerts import CRITERIA_LABELS


def build_case_listing(df: pd.DataFrame) -> list[dict]:
    """
    Build a case-level index with all reactions and outcomes per case.

    Returns a list of dicts — one per unique safetyreportid.
    Safe for JSON serialisation (all values are Python natives).
    """
    cases = []

    for case_id, group in df.groupby(CASE_ID_FIELD):
        # Case-level attributes come from the first row
        # (they repeat identically across multi-reaction rows for one case)
        first = group.iloc[0]

        # Collect all reaction PTs for this case
        reactions = group[REACTION_FIELD].dropna().tolist()
        reactions = [str(r) for r in reactions]

        # Flatten all outcome tokens for this case (already parsed as lists)
        outcomes_flat = []
        for outcome_list in group["norm_outcomes"]:
            if isinstance(outcome_list, list):
                outcomes_flat.extend(outcome_list)
        # Preserve unique outcomes in observed order
        seen = set()
        unique_outcomes = []
        for o in outcomes_flat:
            if o not in seen:
                seen.add(o)
                unique_outcomes.append(o)

        # Which seriousness criteria does this case meet?
        criteria_met = [
            CRITERIA_LABELS.get(col, col)
            for col in SERIOUSNESS_CRITERIA
            if first.get(col) == CRITERION_YES
        ]

        # Safe extraction of scalar values (handles pd.NA, NaN, NaT)
        age_years = _safe_float(first.get("norm_age_years"))
        receivedate = _safe_date(first.get("norm_receivedate"))
        country = _safe_str(first.get("norm_country"))
        sex = _safe_str(first.get("patient_patientsex"))
        age_group = _safe_str(first.get("norm_age_group"), default="Unknown")
        is_serious = bool(first.get("norm_is_serious", False))
        is_expedited = bool(first.get("norm_is_expedited", False))

        cases.append({
            "safetyreportid": int(case_id),
            "receivedate": receivedate,
            "country": country,
            "sex": sex,
            "age_years": age_years,
            "age_group": age_group,
            "is_serious": is_serious,
            "is_expedited": is_expedited,
            "reactions": reactions,
            "outcomes": unique_outcomes,
            "seriousness_criteria_met": criteria_met,
            "num_reaction_rows": int(len(group)),
        })

    return cases


# ---------------------------------------------------------------------------
# Safe extraction helpers — convert pandas NA types to JSON-safe Python types
# ---------------------------------------------------------------------------

def _safe_float(val) -> float | None:
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_str(val, default: str = "unknown") -> str:
    try:
        if pd.isna(val):
            return default
    except (TypeError, ValueError):
        pass
    return str(val) if val is not None else default


def _safe_date(val) -> str:
    try:
        if pd.isna(val):
            return "unknown"
    except (TypeError, ValueError):
        pass
    try:
        return str(pd.Timestamp(val).date())
    except Exception:
        return "unknown"
