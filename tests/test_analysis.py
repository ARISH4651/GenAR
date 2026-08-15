"""
tests/test_analysis.py

Tests for the deterministic analysis engine (Stage 3).

Uses synthetic DataFrames — no real dataset required.
Tests intentionally catch:
  - Counting rows as cases
  - Double-counting serious cases with multiple reaction rows
  - Criteria overlap (not mutually exclusive)
  - Reaction analysis at row level
  - Outcome token explosion from comma-concatenated strings
  - Monthly trend deduplication (case level, not row level)
  - Case listing correctness for multi-reaction cases
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import (
    CASE_ID_FIELD, DATE_FIELD, EXPEDITE_FIELD, EXPEDITE_YES,
    NOT_SERIOUS_VALUE, REACTION_FIELD, OUTCOME_FIELD,
    SERIOUS_FIELD, SERIOUS_VALUE, AGE_FIELD, AGE_UNIT_FIELD,
    COUNTRY_FIELD, COUNTRY_FALLBACK_FIELD, SERIOUSNESS_CRITERIA,
)
from src.analysis.case_analysis import compute_case_summary
from src.analysis.demographics import compute_demographics
from src.analysis.reactions import compute_reactions
from src.analysis.outcomes import compute_outcomes
from src.analysis.alerts import compute_alerts
from src.analysis.trends import compute_trends
from src.analysis.case_listing import build_case_listing


from src.analysis.case_table import build_case_table

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _base_row(**overrides) -> dict:
    row = {
        CASE_ID_FIELD: 1001,
        SERIOUS_FIELD: SERIOUS_VALUE,
        EXPEDITE_FIELD: EXPEDITE_YES,
        DATE_FIELD: pd.Timestamp("2025-03-15"),
        "patient_patientsex": "female",
        AGE_FIELD: 60.0,
        AGE_UNIT_FIELD: "year",
        COUNTRY_FIELD: "united kingdom",
        COUNTRY_FALLBACK_FIELD: "united kingdom",
        REACTION_FIELD: "Hypertension",
        OUTCOME_FIELD: "recovered/resolved",
        # Normalised columns (added by validator)
        "norm_is_serious": True,
        "norm_is_expedited": True,
        "norm_age_years": 60.0,
        "norm_age_group": "45-64",
        "norm_outcomes": ["recovered/resolved"],
        "norm_country": "united kingdom",
        "norm_receivedate": pd.Timestamp("2025-03-15"),
        **{c: "no" for c in SERIOUSNESS_CRITERIA},
    }
    row.update(overrides)
    return row


def _df(*rows) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


# ---------------------------------------------------------------------------
# 1. Case summary
# ---------------------------------------------------------------------------

class TestCaseSummary:
    def test_total_rows_vs_unique_cases(self):
        """Two rows for same case = 1 case, 2 rows."""
        df = _df(
            _base_row(safetyreportid=1, patient_reaction_reactionmeddrapt="Fatigue"),
            _base_row(safetyreportid=1, patient_reaction_reactionmeddrapt="Nausea"),
            _base_row(safetyreportid=2, patient_reaction_reactionmeddrapt="Headache"),
        )
        case_df = build_case_table(df)
        result = compute_case_summary(df, case_df)
        assert result["total_rows"] == 3
        assert result["total_cases"] == 2

    def test_serious_cases_not_double_counted(self):
        """A serious case with 2 reaction rows counts as 1 serious case."""
        df = _df(
            _base_row(safetyreportid=1, norm_is_serious=True, seriousnessother="yes"),
            _base_row(safetyreportid=1, norm_is_serious=True, seriousnessother="yes"),  # same case
            _base_row(safetyreportid=2, norm_is_serious=False,
                      serious=NOT_SERIOUS_VALUE, norm_is_expedited=False,
                      fulfillexpeditecriteria="no"),
        )
        case_df = build_case_table(df)
        result = compute_case_summary(df, case_df)
        assert result["serious_cases"] == 1
        assert result["non_serious_cases"] == 1

    def test_cases_with_multiple_reactions_counted(self):
        df = _df(
            _base_row(safetyreportid=1, patient_reaction_reactionmeddrapt="A"),
            _base_row(safetyreportid=1, patient_reaction_reactionmeddrapt="B"),
            _base_row(safetyreportid=2, patient_reaction_reactionmeddrapt="C"),
        )
        case_df = build_case_table(df)
        result = compute_case_summary(df, case_df)
        assert result["cases_with_multiple_reactions"] == 1

    def test_reporting_period_derived_from_report_date(self):
        df = _df(
            _base_row(safetyreportid=1, report_date=pd.Timestamp("2025-01-01")),
            _base_row(safetyreportid=2, report_date=pd.Timestamp("2025-06-30")),
        )
        case_df = build_case_table(df)
        result = compute_case_summary(df, case_df)
        assert result["reporting_period_start"] == "2025-01-01"
        assert result["reporting_period_end"] == "2025-06-30"

    def test_unique_reaction_pts_counted_at_row_level(self):
        """Unique PTs = distinct PT values across ALL rows, not per case."""
        df = _df(
            _base_row(safetyreportid=1, patient_reaction_reactionmeddrapt="Fatigue"),
            _base_row(safetyreportid=1, patient_reaction_reactionmeddrapt="Nausea"),
            _base_row(safetyreportid=2, patient_reaction_reactionmeddrapt="Fatigue"),  # repeated
        )
        case_df = build_case_table(df)
        result = compute_case_summary(df, case_df)
        assert result["unique_reaction_pts"] == 2  # Fatigue + Nausea


# ---------------------------------------------------------------------------
# 2. Demographics
# ---------------------------------------------------------------------------

class TestDemographics:
    def test_sex_counted_at_case_level(self):
        """Multi-reaction case counts as ONE patient, not two."""
        df = _df(
            _base_row(safetyreportid=1, patient_patientsex="female"),
            _base_row(safetyreportid=1, patient_patientsex="female"),  # same patient
            _base_row(safetyreportid=2, patient_patientsex="male"),
        )
        case_df = build_case_table(df)
        result = compute_demographics(df, case_df)
        assert result["sex_breakdown"]["female"] == 1
        assert result["sex_breakdown"]["male"] == 1

    def test_age_group_counted_at_case_level(self):
        df = _df(
            _base_row(safetyreportid=1, norm_age_group="65-74"),
            _base_row(safetyreportid=1, norm_age_group="65-74"),  # same case
            _base_row(safetyreportid=2, norm_age_group="75+"),
        )
        case_df = build_case_table(df)
        result = compute_demographics(df, case_df)
        assert result["age_group_breakdown"]["65-74"] == 1
        assert result["age_group_breakdown"]["75+"] == 1

    def test_all_age_buckets_present_in_result(self):
        df = _df(_base_row(norm_age_group="45-64"))
        case_df = build_case_table(df)
        result = compute_demographics(df, case_df)
        for bucket in ["0-17", "18-44", "45-64", "65-74", "75+", "Unknown"]:
            assert bucket in result["age_group_breakdown"]


# ---------------------------------------------------------------------------
# 3. Reactions
# ---------------------------------------------------------------------------

class TestReactions:
    def test_reaction_counts_at_row_level(self):
        """Two reaction rows = two reaction counts (not one)."""
        df = _df(
            _base_row(safetyreportid=1, patient_reaction_reactionmeddrapt="Fatigue"),
            _base_row(safetyreportid=1, patient_reaction_reactionmeddrapt="Fatigue"),
        )
        case_df = build_case_table(df)
        result = compute_reactions(df, case_df, top_n=5)
        fatigue = next(r for r in result["top_reactions"] if r["reaction_pt"] == "Fatigue")
        assert fatigue["count"] == 2

    def test_serious_reactions_filtered_to_serious_cases(self):
        """Serious reaction list must exclude non-serious case reactions."""
        df = _df(
            _base_row(safetyreportid=1, patient_reaction_reactionmeddrapt="Fatal_PT",
                      norm_is_serious=True, seriousnessdeath="yes"),
            _base_row(safetyreportid=2, patient_reaction_reactionmeddrapt="Mild_PT",
                      norm_is_serious=False, serious=NOT_SERIOUS_VALUE),
        )
        case_df = build_case_table(df)
        result = compute_reactions(df, case_df, top_n=10)
        serious_pts = [r["reaction_pt"] for r in result["top_serious_reactions"]]
        assert "Fatal_PT" in serious_pts
        assert "Mild_PT" not in serious_pts

    def test_percent_calculated_over_total_rows(self):
        """Percent of reactions = count / total_reaction_rows × 100."""
        df = _df(
            _base_row(safetyreportid=1, patient_reaction_reactionmeddrapt="A"),
            _base_row(safetyreportid=2, patient_reaction_reactionmeddrapt="A"),
            _base_row(safetyreportid=3, patient_reaction_reactionmeddrapt="B"),
            _base_row(safetyreportid=4, patient_reaction_reactionmeddrapt="B"),
        )
        case_df = build_case_table(df)
        result = compute_reactions(df, case_df, top_n=5)
        assert result["total_reaction_rows"] == 4
        for r in result["top_reactions"]:
            assert r["percent_of_reactions"] == pytest.approx(50.0)

    def test_soc_analysis_flagged_unavailable(self):
        df = _df(_base_row())
        case_df = build_case_table(df)
        result = compute_reactions(df, case_df)
        assert result["soc_analysis_available"] is False


# ---------------------------------------------------------------------------
# 4. Outcomes
# ---------------------------------------------------------------------------

class TestOutcomes:
    def test_comma_outcomes_exploded_and_counted(self):
        """'recovered/resolved,fatal' must contribute two separate outcome counts."""
        df = _df(
            _base_row(norm_outcomes=["recovered/resolved", "fatal"]),
            _base_row(norm_outcomes=["recovered/resolved"]),
        )
        result = compute_outcomes(df)
        counts = {o["outcome"]: o["count"] for o in result["outcomes"]}
        assert counts["recovered/resolved"] == 2
        assert counts["fatal"] == 1
        assert result["total_outcome_entries"] == 3

    def test_empty_outcomes_excluded(self):
        df = _df(
            _base_row(norm_outcomes=[]),
            _base_row(norm_outcomes=["unknown"]),
        )
        result = compute_outcomes(df)
        counts = {o["outcome"]: o["count"] for o in result["outcomes"]}
        assert counts.get("unknown") == 1

    def test_percent_of_outcome_tokens(self):
        df = _df(
            _base_row(norm_outcomes=["fatal", "fatal"]),
            _base_row(norm_outcomes=["fatal"]),
        )
        result = compute_outcomes(df)
        fatal = next(o for o in result["outcomes"] if o["outcome"] == "fatal")
        assert fatal["percent_of_outcome_tokens"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# 5. Alerts & seriousness criteria
# ---------------------------------------------------------------------------

class TestAlerts:
    def test_expedited_count_at_case_level(self):
        """Multi-reaction expedited case counts as 1 expedited case."""
        df = _df(
            _base_row(safetyreportid=1, norm_is_expedited=True),
            _base_row(safetyreportid=1, norm_is_expedited=True),  # same case
            _base_row(safetyreportid=2, norm_is_expedited=False,
                      fulfillexpeditecriteria="no"),
        )
        case_df = build_case_table(df)
        result = compute_alerts(df, case_df)
        assert result["expedited_cases"] == 1
        assert result["non_expedited_cases"] == 1

    def test_criteria_are_not_mutually_exclusive(self):
        """
        A case meeting both hospitalisation AND seriousnessother contributes
        to BOTH counts. Total criteria counts > number of serious cases is expected.
        """
        df = _df(_base_row(
            safetyreportid=1,
            seriousnesshospitalization="yes",
            seriousnessother="yes",
            norm_is_serious=True,
        ))
        case_df = build_case_table(df)
        result = compute_alerts(df, case_df)
        # One serious case
        assert result["total_cases"] == 1
        # Two criteria met
        breakdown = {r["criterion_field"]: r["cases_meeting_criterion"]
                     for r in result["seriousness_criteria_breakdown"]}
        assert breakdown["seriousnesshospitalization"] == 1
        assert breakdown["seriousnessother"] == 1
        # Sum of criteria counts (2) > serious cases (1) — expected
        total_criteria = sum(breakdown.values())
        assert total_criteria >= result["total_cases"]

    def test_criteria_use_yes_string_not_1(self):
        """The dataset uses 'yes' strings, not integer 1."""
        df = _df(_base_row(seriousnessdeath="yes"))
        case_df = build_case_table(df)
        result = compute_alerts(df, case_df)
        breakdown = {r["criterion_field"]: r["cases_meeting_criterion"]
                     for r in result["seriousness_criteria_breakdown"]}
        assert breakdown["seriousnessdeath"] == 1

    def test_cumulative_counts_note_present(self):
        df = _df(_base_row())
        case_df = build_case_table(df)
        result = compute_alerts(df, case_df)
        assert "cumulative_counts_note" in result
        assert "not available" in result["cumulative_counts_note"].lower()


# ---------------------------------------------------------------------------
# 6. Trends
# ---------------------------------------------------------------------------

class TestTrends:
    def test_monthly_counts_at_case_level(self):
        """Two rows for same case in same month = 1 case for that month."""
        df = _df(
            _base_row(safetyreportid=1, report_date=pd.Timestamp("2025-03-10")),
            _base_row(safetyreportid=1, report_date=pd.Timestamp("2025-03-10")),  # same case
            _base_row(safetyreportid=2, report_date=pd.Timestamp("2025-03-20")),
            _base_row(safetyreportid=3, report_date=pd.Timestamp("2025-04-05")),
        )
        result = compute_trends(df)
        monthly = {m["year_month"]: m["count"] for m in result["monthly_case_counts"]}
        assert monthly["2025-03"] == 2
        assert monthly["2025-04"] == 1

    def test_trend_note_warns_against_signal_inference(self):
        df = _df(_base_row())
        result = compute_trends(df)
        assert "signal" in result["trend_note"].lower() or "observation" in result["trend_note"].lower()

    def test_period_start_end_from_data(self):
        df = _df(
            _base_row(safetyreportid=1, report_date=pd.Timestamp("2025-01-01")),
            _base_row(safetyreportid=2, report_date=pd.Timestamp("2025-12-31")),
        )
        result = compute_trends(df)
        assert result["reporting_period_start"] == "2025-01-01"
        assert result["reporting_period_end"] == "2025-12-31"


# ---------------------------------------------------------------------------
# 7. Case listing
# ---------------------------------------------------------------------------

class TestCaseListing:
    def test_one_record_per_case(self):
        """Multi-reaction case produces ONE listing entry."""
        df = _df(
            _base_row(safetyreportid=1, patient_reaction_reactionmeddrapt="Fatigue"),
            _base_row(safetyreportid=1, patient_reaction_reactionmeddrapt="Nausea"),
            _base_row(safetyreportid=2, patient_reaction_reactionmeddrapt="Headache"),
        )
        listing = build_case_listing(df)
        assert len(listing) == 2

    def test_all_reactions_collected_for_multi_reaction_case(self):
        df = _df(
            _base_row(safetyreportid=5, patient_reaction_reactionmeddrapt="Fatigue"),
            _base_row(safetyreportid=5, patient_reaction_reactionmeddrapt="Nausea"),
        )
        listing = build_case_listing(df)
        case = listing[0]
        assert "Fatigue" in case["reactions"]
        assert "Nausea" in case["reactions"]
        assert case["num_reaction_rows"] == 2

    def test_seriousness_criteria_collected(self):
        df = _df(_base_row(
            safetyreportid=7,
            seriousnesshospitalization="yes",
            seriousnessother="yes",
        ))
        listing = build_case_listing(df)
        case = listing[0]
        assert any("Hospitalisation" in c for c in case["seriousness_criteria_met"])
        assert any("significant" in c.lower() for c in case["seriousness_criteria_met"])

    def test_outcomes_deduplicated_per_case(self):
        """If two reaction rows have the same outcome, list it once."""
        df = _df(
            _base_row(safetyreportid=8, norm_outcomes=["recovered/resolved"]),
            _base_row(safetyreportid=8, norm_outcomes=["recovered/resolved"]),
        )
        listing = build_case_listing(df)
        assert listing[0]["outcomes"].count("recovered/resolved") == 1

    def test_case_listing_json_serialisable(self):
        """All values must be Python natives — no pandas/numpy types."""
        import json
        df = _df(
            _base_row(safetyreportid=9, norm_age_years=72.5),
            _base_row(safetyreportid=9, norm_age_years=72.5),
        )
        listing = build_case_listing(df)
        # Should not raise
        serialised = json.dumps(listing)
        assert "safetyreportid" in serialised
