"""
tests/test_validator.py

Tests for the DataValidator (Stage 2).

These tests use synthetic DataFrames — they do NOT depend on the
actual dataset CSV/XLSX being present. The design intent is that
unit tests can run in CI without the dataset.

Tests intentionally catch the common failure modes specified in the challenge:
  - Counting rows as cases (instead of unique safetyreportid)
  - Missing required columns triggering an error
  - Age normalisation for all unit types
  - Invalid age unit '800' → Unknown bucket
  - Comma-concatenated outcome field splitting
  - Seriousness field encoding (yes/no strings, not 1/0)
  - Country fallback logic
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import (
    AGE_BUCKETS,
    AGE_UNKNOWN_LABEL,
    CASE_ID_FIELD,
    COUNTRY_FALLBACK_FIELD,
    COUNTRY_FIELD,
    CRITERION_YES,
    DATE_FIELD,
    EXPEDITE_FIELD,
    EXPEDITE_YES,
    NOT_SERIOUS_VALUE,
    OUTCOME_FIELD,
    REACTION_FIELD,
    RECEIVEDATE_FIELD,
    SERIOUS_FIELD,
    SERIOUS_VALUE,
    SERIOUSNESS_CRITERIA,
    AGE_FIELD,
    AGE_UNIT_FIELD,
)
from src.models.schemas import Severity
from src.validation.validator import DataValidator


# ---------------------------------------------------------------------------
# Helpers to build minimal valid test DataFrames
# ---------------------------------------------------------------------------

def _base_row(**overrides) -> dict:
    """Return a minimal valid row. Override any field as needed."""
    row = {
        CASE_ID_FIELD: 1001,
        SERIOUS_FIELD: SERIOUS_VALUE,
        EXPEDITE_FIELD: EXPEDITE_YES,
        DATE_FIELD: pd.Timestamp("2025-03-15"),
        RECEIVEDATE_FIELD: 20250315,
        "patient_patientsex": "female",
        AGE_FIELD: 60.0,
        AGE_UNIT_FIELD: "year",
        COUNTRY_FIELD: "united kingdom",
        COUNTRY_FALLBACK_FIELD: "united kingdom",
        REACTION_FIELD: "Hypertension",
        OUTCOME_FIELD: "recovered/resolved",
        "duplicate": None,
        **{c: "no" for c in SERIOUSNESS_CRITERIA},
    }
    row.update(overrides)
    return row


def _make_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _run(df: pd.DataFrame):
    """Run validation without touching the filesystem."""
    v = DataValidator.__new__(DataValidator)
    v.file_path = Path("synthetic.xlsx")
    v._issues = []
    v._check_required_columns(df)
    v._check_case_ids(df)
    v._check_serious_field(df)
    v._check_seriousness_criteria(df)
    v._check_expedite_field(df)
    v._check_dates(df)
    v._check_age(df)
    v._check_sex(df)
    v._check_country(df)
    v._check_reactions(df)
    v._check_outcomes(df)
    df = v._normalise(df)
    result = v._build_result(df, fatal=False)
    return result, df


# ---------------------------------------------------------------------------
# 1. Schema checks
# ---------------------------------------------------------------------------

class TestRequiredColumns:
    def test_all_columns_present_passes(self):
        df = _make_df([_base_row()])
        result, _ = _run(df)
        assert result.is_valid

    def test_missing_column_is_error(self):
        df = _make_df([_base_row()])
        df = df.drop(columns=[REACTION_FIELD])
        v = DataValidator.__new__(DataValidator)
        v.file_path = Path("x.xlsx")
        v._issues = []
        v._check_required_columns(df)
        errors = [i for i in v._issues if i.severity == Severity.ERROR]
        assert len(errors) == 1
        assert REACTION_FIELD in errors[0].message


# ---------------------------------------------------------------------------
# 2. Case counting — the fundamental requirement
# ---------------------------------------------------------------------------

class TestCaseCounting:
    def test_unique_case_count_not_row_count(self):
        """
        Key requirement: two rows with the same safetyreportid = ONE case.
        A naïve row count would give 2; correct answer is 1.
        """
        rows = [
            _base_row(safetyreportid=5001, patient_reaction_reactionmeddrapt="Fatigue"),
            _base_row(safetyreportid=5001, patient_reaction_reactionmeddrapt="Nausea"),
        ]
        result, _ = _run(_make_df(rows))
        # 2 rows, 1 unique case
        assert result.metadata.total_rows == 2
        assert result.metadata.unique_cases == 1

    def test_two_distinct_cases(self):
        rows = [_base_row(safetyreportid=1001), _base_row(safetyreportid=1002)]
        result, _ = _run(_make_df(rows))
        assert result.metadata.unique_cases == 2

    def test_multi_reaction_case_counted_once_for_seriousness(self):
        """
        A case with 2 reaction rows should count as 1 serious case,
        not 2 serious cases.
        """
        rows = [
            _base_row(safetyreportid=9001, serious=SERIOUS_VALUE),
            _base_row(safetyreportid=9001, serious=SERIOUS_VALUE),
        ]
        result, _ = _run(_make_df(rows))
        assert result.metadata.serious_cases == 1


# ---------------------------------------------------------------------------
# 3. Seriousness
# ---------------------------------------------------------------------------

class TestSeriousness:
    def test_serious_count(self):
        rows = [
            _base_row(safetyreportid=1, serious=SERIOUS_VALUE),
            _base_row(safetyreportid=2, serious=NOT_SERIOUS_VALUE),
        ]
        result, _ = _run(_make_df(rows))
        assert result.metadata.serious_cases == 1
        assert result.metadata.non_serious_cases == 1

    def test_seriousness_criteria_are_not_mutually_exclusive(self):
        """
        A case can meet multiple criteria simultaneously.
        Total criteria counts may exceed serious case count.
        The validator must not conflate criteria counts with case counts.
        """
        row = _base_row(
            seriousnessdeath="no",
            seriousnesslifethreatening="yes",   # criterion A met
            seriousnesshospitalization="yes",   # criterion B also met
            seriousnessother="no",
            seriousnessdisabling="no",
            seriousnesscongenitalanomali="no",
        )
        result, df = _run(_make_df([row]))
        # One serious case
        assert result.metadata.serious_cases == 1
        # Both criteria flags are present on that one case
        assert df["seriousnesslifethreatening"].iloc[0] == CRITERION_YES
        assert df["seriousnesshospitalization"].iloc[0] == CRITERION_YES

    def test_seriousness_criteria_use_yes_not_1(self):
        """
        The dataset uses 'yes'/'no' strings, NOT '1'/'0'.
        Checking for value '1' would give 0 matches — this test
        catches that mistake.
        """
        row = _base_row(seriousnessother="yes")
        _, df = _run(_make_df([row]))
        # Correct check: string 'yes'
        assert (df["seriousnessother"] == "yes").sum() == 1
        # Wrong check: integer 1 — should find nothing
        assert (df["seriousnessother"] == 1).sum() == 0

    def test_norm_is_serious_bool(self):
        rows = [
            _base_row(safetyreportid=1, serious=SERIOUS_VALUE),
            _base_row(safetyreportid=2, serious=NOT_SERIOUS_VALUE),
        ]
        _, df = _run(_make_df(rows))
        assert df[df[CASE_ID_FIELD] == 1]["norm_is_serious"].iloc[0] is True or \
               bool(df[df[CASE_ID_FIELD] == 1]["norm_is_serious"].iloc[0]) is True
        assert df[df[CASE_ID_FIELD] == 2]["norm_is_serious"].iloc[0] is False or \
               bool(df[df[CASE_ID_FIELD] == 2]["norm_is_serious"].iloc[0]) is False


# ---------------------------------------------------------------------------
# 4. Age normalisation
# ---------------------------------------------------------------------------

class TestAgeNormalisation:
    def _age_group_for(self, age, unit):
        row = _base_row(patient_patientonsetage=age, patient_patientonsetageunit=unit)
        _, df = _run(_make_df([row]))
        return df["norm_age_group"].iloc[0]

    def _age_years_for(self, age, unit):
        row = _base_row(patient_patientonsetage=age, patient_patientonsetageunit=unit)
        _, df = _run(_make_df([row]))
        return df["norm_age_years"].iloc[0]

    def test_year_unit_unchanged(self):
        assert self._age_years_for(65, "year") == pytest.approx(65.0)

    def test_month_unit_converted(self):
        # 6 months = 0.5 years -> bucket 0-17
        assert self._age_years_for(6, "month") == pytest.approx(6 / 12)

    def test_day_unit_converted(self):
        # 30 days ~ 0.082 years -> bucket 0-17
        years = self._age_years_for(30, "day")
        assert years == pytest.approx(30 / 365)

    def test_week_unit_converted(self):
        years = self._age_years_for(52, "week")
        assert years == pytest.approx(52 / 52)  # 1 year

    def test_invalid_unit_800_is_unknown(self):
        group = self._age_group_for(50, "800")
        assert group == AGE_UNKNOWN_LABEL

    def test_null_age_is_unknown(self):
        row = _base_row(patient_patientonsetage=None, patient_patientonsetageunit=None)
        _, df = _run(_make_df([row]))
        assert df["norm_age_group"].iloc[0] == AGE_UNKNOWN_LABEL

    def test_age_bucket_0_to_17(self):
        assert self._age_group_for(10, "year") == "0-17"

    def test_age_bucket_18_to_44(self):
        assert self._age_group_for(30, "year") == "18-44"

    def test_age_bucket_45_to_64(self):
        assert self._age_group_for(55, "year") == "45-64"

    def test_age_bucket_65_to_74(self):
        assert self._age_group_for(70, "year") == "65-74"

    def test_age_bucket_75_plus(self):
        assert self._age_group_for(80, "year") == "75+"

    def test_boundary_age_18_goes_to_18_44(self):
        assert self._age_group_for(18, "year") == "18-44"

    def test_boundary_age_75_goes_to_75_plus(self):
        assert self._age_group_for(75, "year") == "75+"


# ---------------------------------------------------------------------------
# 5. Outcome parsing
# ---------------------------------------------------------------------------

class TestOutcomeParsing:
    def test_single_outcome_parsed(self):
        row = _base_row(patient_reaction_reactionoutcome="recovered/resolved")
        _, df = _run(_make_df([row]))
        assert df["norm_outcomes"].iloc[0] == ["recovered/resolved"]

    def test_comma_concatenated_outcomes_split(self):
        """
        'recovered/resolved,fatal' must be split into TWO tokens,
        not treated as one unknown outcome string.
        """
        row = _base_row(patient_reaction_reactionoutcome="recovered/resolved,fatal")
        _, df = _run(_make_df([row]))
        outcomes = df["norm_outcomes"].iloc[0]
        assert "recovered/resolved" in outcomes
        assert "fatal" in outcomes
        assert len(outcomes) == 2

    def test_three_outcomes_split(self):
        row = _base_row(
            patient_reaction_reactionoutcome="unknown,recovering/resolving,not recovered/not resolved/ongoing"
        )
        _, df = _run(_make_df([row]))
        assert len(df["norm_outcomes"].iloc[0]) == 3

    def test_null_outcome_returns_empty_list(self):
        row = _base_row(patient_reaction_reactionoutcome=None)
        _, df = _run(_make_df([row]))
        assert df["norm_outcomes"].iloc[0] == []


# ---------------------------------------------------------------------------
# 6. Country fallback
# ---------------------------------------------------------------------------

class TestCountryFallback:
    def test_occurcountry_used_when_present(self):
        row = _base_row(**{COUNTRY_FIELD: "france", COUNTRY_FALLBACK_FIELD: "eu"})
        _, df = _run(_make_df([row]))
        assert df["norm_country"].iloc[0] == "france"

    def test_reporter_country_used_as_fallback(self):
        row = _base_row(**{COUNTRY_FIELD: None, COUNTRY_FALLBACK_FIELD: "germany"})
        _, df = _run(_make_df([row]))
        assert df["norm_country"].iloc[0] == "germany"


# ---------------------------------------------------------------------------
# 7. Alert / expedited
# ---------------------------------------------------------------------------

class TestAlertsExpedited:
    def test_expedited_count(self):
        rows = [
            _base_row(safetyreportid=1, fulfillexpeditecriteria="yes"),
            _base_row(safetyreportid=2, fulfillexpeditecriteria="yes"),
            _base_row(safetyreportid=3, fulfillexpeditecriteria="no"),
        ]
        result, _ = _run(_make_df(rows))
        assert result.metadata.expedited_cases == 2

    def test_norm_is_expedited_bool(self):
        rows = [
            _base_row(safetyreportid=1, fulfillexpeditecriteria="yes"),
            _base_row(safetyreportid=2, fulfillexpeditecriteria="no"),
        ]
        _, df = _run(_make_df(rows))
        expedited = df[df[CASE_ID_FIELD] == 1]["norm_is_expedited"].iloc[0]
        not_expedited = df[df[CASE_ID_FIELD] == 2]["norm_is_expedited"].iloc[0]
        assert bool(expedited) is True
        assert bool(not_expedited) is False


# ---------------------------------------------------------------------------
# 8. Date parsing
# ---------------------------------------------------------------------------

class TestDateNormalisation:
    def test_receivedate_int_parsed_to_datetime(self):
        row = _base_row(receivedate=20250315)
        _, df = _run(_make_df([row]))
        assert df["norm_receivedate"].iloc[0] == pd.Timestamp("2025-03-15")

    def test_reporting_period_derived_from_report_date(self):
        rows = [
            _base_row(safetyreportid=1, report_date=pd.Timestamp("2025-01-01")),
            _base_row(safetyreportid=2, report_date=pd.Timestamp("2025-06-30")),
        ]
        result, _ = _run(_make_df(rows))
        assert result.metadata.reporting_period_start == date(2025, 1, 1)
        assert result.metadata.reporting_period_end == date(2025, 6, 30)
