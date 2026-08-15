"""
src/validation/validator.py

DataValidator: loads the ICSR dataset, runs deterministic quality checks,
normalises problematic fields, and returns a clean DataFrame alongside
a structured ValidationResult.

Design principles:
  - All checks use vectorised Pandas operations (fast, auditable).
  - Normalisation produces NEW columns (prefixed with norm_) so the
    original raw values are always preserved for traceability.
  - Errors block execution; warnings are logged and execution continues.
  - The LLM never touches this layer.

Normalised columns added to the DataFrame:
  norm_receivedate   : pd.Timestamp (parsed from int YYYYMMDD)
  norm_age_years     : float | NaN  (all ages converted to years)
  norm_age_group     : str          (bucket label, e.g. "45-64")
  norm_is_serious    : bool
  norm_is_expedited  : bool
  norm_outcomes      : list[str]    (split from comma-concatenated field)
  norm_country       : str          (occurcountry, falling back to reporter country)
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from src.config.settings import (
    AGE_BUCKETS,
    AGE_FIELD,
    AGE_UNIT_FIELD,
    AGE_UNIT_TO_YEARS,
    AGE_UNKNOWN_LABEL,
    CASE_ID_FIELD,
    COUNTRY_FALLBACK_FIELD,
    COUNTRY_FIELD,
    CRITERION_YES,
    DATE_FIELD,
    EXPEDITE_FIELD,
    EXPEDITE_YES,
    INVALID_AGE_UNIT_CODE,
    NOT_SERIOUS_VALUE,
    OUTCOME_FIELD,
    OUTCOME_SEPARATOR,
    REACTION_FIELD,
    RECEIVEDATE_FIELD,
    REQUIRED_COLUMNS,
    SERIOUS_FIELD,
    SERIOUS_VALUE,
    SERIOUSNESS_CRITERIA,
    VALID_AGE_UNITS,
)
from src.models.schemas import DataQualityIssue, DatasetMetadata, Severity, ValidationResult

logger = logging.getLogger(__name__)


class DataValidator:
    """
    Validates and normalises the ICSR dataset.

    Usage:
        validator = DataValidator("path/to/data.xlsx")
        result, clean_df = validator.validate()
        if not result.is_valid:
            sys.exit(result.summary())
    """

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)
        self._issues: list[DataQualityIssue] = []

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def validate(self) -> tuple[ValidationResult, pd.DataFrame]:
        """
        Run all validation checks and return (ValidationResult, clean_df).

        The returned DataFrame contains all original columns PLUS
        normalised columns (norm_*) for downstream use.
        Raises FileNotFoundError if the source file does not exist.
        """
        df = self._load(self.file_path)

        # Structural checks — if these fail, we cannot proceed
        self._check_required_columns(df)
        if any(i.severity == Severity.ERROR for i in self._issues):
            result = self._build_result(df, fatal=True)
            return result, df

        # Field-level quality checks
        self._check_case_ids(df)
        self._check_serious_field(df)
        self._check_seriousness_criteria(df)
        self._check_expedite_field(df)
        self._check_dates(df)
        self._check_age(df)
        self._check_sex(df)
        self._check_country(df)
        self._check_reactions(df)
        self._check_outcomes(df)
        self._check_duplicate_flag(df)

        # Normalisation — adds norm_* columns
        df = self._normalise(df)

        result = self._build_result(df, fatal=False)
        logger.info(result.summary())
        return result, df

    # ------------------------------------------------------------------
    # Loader
    # ------------------------------------------------------------------

    def _load(self, path: Path) -> pd.DataFrame:
        """Load XLSX or CSV depending on file extension."""
        if not path.exists():
            raise FileNotFoundError(f"Dataset not found: {path}")

        if path.suffix.lower() in (".xlsx", ".xls"):
            logger.info("Loading Excel file: %s", path)
            df = pd.read_excel(path, dtype_backend="numpy_nullable")
        elif path.suffix.lower() == ".csv":
            logger.info("Loading CSV file: %s", path)
            df = pd.read_csv(path, dtype_backend="numpy_nullable", low_memory=False)
        else:
            raise ValueError(f"Unsupported file type: {path.suffix}")

        logger.info("Loaded %d rows × %d columns", len(df), len(df.columns))
        return df

    # ------------------------------------------------------------------
    # Structural checks
    # ------------------------------------------------------------------

    def _check_required_columns(self, df: pd.DataFrame) -> None:
        """Fail hard if any required column is missing."""
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            self._issues.append(DataQualityIssue(
                field="schema",
                severity=Severity.ERROR,
                message=f"Required columns missing from dataset: {missing}",
                affected_rows=0,
            ))

    def _check_case_ids(self, df: pd.DataFrame) -> None:
        """safetyreportid must never be null."""
        null_count = df[CASE_ID_FIELD].isna().sum()
        if null_count > 0:
            self._issues.append(DataQualityIssue(
                field=CASE_ID_FIELD,
                severity=Severity.ERROR,
                message="safetyreportid is null — cannot identify cases",
                affected_rows=int(null_count),
            ))

    # ------------------------------------------------------------------
    # Seriousness checks
    # ------------------------------------------------------------------

    def _check_serious_field(self, df: pd.DataFrame) -> None:
        """serious must be 'serious' or 'not serious'."""
        valid = {SERIOUS_VALUE, NOT_SERIOUS_VALUE}
        cases = df.drop_duplicates(subset=CASE_ID_FIELD)
        unexpected = cases[~cases[SERIOUS_FIELD].isin(valid)][SERIOUS_FIELD]
        if not unexpected.empty:
            self._issues.append(DataQualityIssue(
                field=SERIOUS_FIELD,
                severity=Severity.WARNING,
                message=(
                    f"Unexpected values in '{SERIOUS_FIELD}': "
                    f"{unexpected.unique().tolist()}"
                ),
                affected_rows=int(unexpected.shape[0]),
            ))

    def _check_seriousness_criteria(self, df: pd.DataFrame) -> None:
        """Each seriousness criterion field must be 'yes' or 'no'."""
        valid = {CRITERION_YES, "no"}
        cases = df.drop_duplicates(subset=CASE_ID_FIELD)
        for col in SERIOUSNESS_CRITERIA:
            unexpected = cases[~cases[col].isin(valid)][col]
            if not unexpected.empty:
                self._issues.append(DataQualityIssue(
                    field=col,
                    severity=Severity.WARNING,
                    message=(
                        f"Unexpected values in '{col}': "
                        f"{unexpected.unique().tolist()}"
                    ),
                    affected_rows=int(unexpected.shape[0]),
                ))

    # ------------------------------------------------------------------
    # Expedite check
    # ------------------------------------------------------------------

    def _check_expedite_field(self, df: pd.DataFrame) -> None:
        """fulfillexpeditecriteria must be 'yes' or 'no'."""
        valid = {EXPEDITE_YES, "no"}
        cases = df.drop_duplicates(subset=CASE_ID_FIELD)
        unexpected = cases[~cases[EXPEDITE_FIELD].isin(valid)][EXPEDITE_FIELD]
        if not unexpected.empty:
            self._issues.append(DataQualityIssue(
                field=EXPEDITE_FIELD,
                severity=Severity.WARNING,
                message=f"Unexpected values: {unexpected.unique().tolist()}",
                affected_rows=int(unexpected.shape[0]),
            ))

    # ------------------------------------------------------------------
    # Date checks
    # ------------------------------------------------------------------

    def _check_dates(self, df: pd.DataFrame) -> None:
        """
        Validate receivedate (int YYYYMMDD) and report_date (datetime).
        Both must be present and parseable.
        """
        # receivedate — should be fully non-null and parseable as YYYYMMDD
        null_rd = df[RECEIVEDATE_FIELD].isna().sum()
        if null_rd > 0:
            self._issues.append(DataQualityIssue(
                field=RECEIVEDATE_FIELD,
                severity=Severity.ERROR,
                message="receivedate contains null values",
                affected_rows=int(null_rd),
            ))
        else:
            parsed = pd.to_datetime(
                df[RECEIVEDATE_FIELD].astype(str), format="%Y%m%d", errors="coerce"
            )
            unparseable = parsed.isna().sum()
            if unparseable > 0:
                self._issues.append(DataQualityIssue(
                    field=RECEIVEDATE_FIELD,
                    severity=Severity.ERROR,
                    message=f"{unparseable} values could not be parsed as YYYYMMDD",
                    affected_rows=int(unparseable),
                ))

        # report_date — must be datetime
        null_rpd = df[DATE_FIELD].isna().sum()
        if null_rpd > 0:
            self._issues.append(DataQualityIssue(
                field=DATE_FIELD,
                severity=Severity.WARNING,
                message="report_date contains null values — excluded from trend analysis",
                affected_rows=int(null_rpd),
            ))

    # ------------------------------------------------------------------
    # Age checks
    # ------------------------------------------------------------------

    def _check_age(self, df: pd.DataFrame) -> None:
        """
        Validate age field quality.
        Known issues from Stage 1:
          - 8.5% of rows have no age
          - Some rows use non-year units (month/day/week) — must convert
          - Unit code '800' is invalid
        """
        missing_age = df[AGE_FIELD].isna().sum()
        if missing_age > 0:
            self._issues.append(DataQualityIssue(
                field=AGE_FIELD,
                severity=Severity.WARNING,
                message=f"{missing_age} rows have no onset age — assigned to '{AGE_UNKNOWN_LABEL}' bucket",
                affected_rows=int(missing_age),
            ))

        # Invalid unit code
        bad_unit = (df[AGE_UNIT_FIELD] == INVALID_AGE_UNIT_CODE).sum()
        if bad_unit > 0:
            self._issues.append(DataQualityIssue(
                field=AGE_UNIT_FIELD,
                severity=Severity.WARNING,
                message=f"Unit code '{INVALID_AGE_UNIT_CODE}' is unrecognised — treated as Unknown",
                affected_rows=int(bad_unit),
            ))

        # Rows with age present but unit missing
        has_age = df[AGE_FIELD].notna()
        missing_unit = df[has_age & df[AGE_UNIT_FIELD].isna()].shape[0]
        if missing_unit > 0:
            self._issues.append(DataQualityIssue(
                field=AGE_UNIT_FIELD,
                severity=Severity.WARNING,
                message=(
                    f"{missing_unit} rows have age but no unit — "
                    "assuming 'year' (common ICSR default)"
                ),
                affected_rows=int(missing_unit),
            ))

    # ------------------------------------------------------------------
    # Sex check
    # ------------------------------------------------------------------

    def _check_sex(self, df: pd.DataFrame) -> None:
        missing = df["patient_patientsex"].isna().sum()
        if missing > 0:
            self._issues.append(DataQualityIssue(
                field="patient_patientsex",
                severity=Severity.WARNING,
                message=f"{missing} rows have no sex recorded",
                affected_rows=int(missing),
            ))

    # ------------------------------------------------------------------
    # Country checks
    # ------------------------------------------------------------------

    def _check_country(self, df: pd.DataFrame) -> None:
        """
        Warn about the 'eu' regional code and missing cases.
        Note: country is checked at row level since it repeats across
        multi-reaction rows for the same case.
        """
        eu_rows = (df[COUNTRY_FIELD].str.lower() == "eu").sum()
        if eu_rows > 0:
            self._issues.append(DataQualityIssue(
                field=COUNTRY_FIELD,
                severity=Severity.WARNING,
                message=(
                    f"{eu_rows} rows have occurcountry='eu' — "
                    "this is a regional code, not a specific country; "
                    "reported as-is in geographic analysis"
                ),
                affected_rows=int(eu_rows),
            ))

        missing = df[COUNTRY_FIELD].isna().sum()
        if missing > 0:
            self._issues.append(DataQualityIssue(
                field=COUNTRY_FIELD,
                severity=Severity.WARNING,
                message=(
                    f"{missing} rows missing occurcountry — "
                    f"primarysource_reportercountry used as fallback"
                ),
                affected_rows=int(missing),
            ))

    # ------------------------------------------------------------------
    # Reaction checks
    # ------------------------------------------------------------------

    def _check_reactions(self, df: pd.DataFrame) -> None:
        """patient_reaction_reactionmeddrapt should be 100% non-null."""
        missing = df[REACTION_FIELD].isna().sum()
        if missing > 0:
            self._issues.append(DataQualityIssue(
                field=REACTION_FIELD,
                severity=Severity.WARNING,
                message=f"{missing} reaction rows have no MedDRA PT",
                affected_rows=int(missing),
            ))

    # ------------------------------------------------------------------
    # Outcome checks
    # ------------------------------------------------------------------

    def _check_outcomes(self, df: pd.DataFrame) -> None:
        """
        The outcome field is a comma-concatenated string.
        This is expected; we warn so the reader knows it requires splitting.
        """
        multi = df[OUTCOME_FIELD].str.contains(",", na=False).sum()
        if multi > 0:
            self._issues.append(DataQualityIssue(
                field=OUTCOME_FIELD,
                severity=Severity.WARNING,
                message=(
                    f"{multi} rows contain comma-concatenated outcomes — "
                    "split by comma before counting (handled in normalisation)"
                ),
                affected_rows=int(multi),
            ))

    # ------------------------------------------------------------------
    # Duplicate flag check
    # ------------------------------------------------------------------

    def _check_duplicate_flag(self, df: pd.DataFrame) -> None:
        """Flag that the duplicate column is entirely null (known from Stage 1)."""
        if CASE_ID_FIELD in df.columns:
            null_count = df["duplicate"].isna().sum() if "duplicate" in df.columns else 0
            if null_count == len(df):
                self._issues.append(DataQualityIssue(
                    field="duplicate",
                    severity=Severity.WARNING,
                    message="'duplicate' field is 100% null — not usable for deduplication",
                    affected_rows=int(null_count),
                ))

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    def _normalise(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add normalised columns to the DataFrame.
        All new columns are prefixed with 'norm_' to distinguish from raw data.
        Original columns are never modified.
        """
        df = df.copy()

        # norm_receivedate: parse YYYYMMDD integer → datetime
        df["norm_receivedate"] = pd.to_datetime(
            df[RECEIVEDATE_FIELD].astype(str), format="%Y%m%d", errors="coerce"
        )

        # norm_is_serious: bool from 'serious' text field
        df["norm_is_serious"] = df[SERIOUS_FIELD] == SERIOUS_VALUE

        # norm_is_expedited: bool from fulfillexpeditecriteria
        df["norm_is_expedited"] = df[EXPEDITE_FIELD] == EXPEDITE_YES

        # norm_age_years: convert all age values to years
        df["norm_age_years"] = df.apply(self._row_age_to_years, axis=1)

        # norm_age_group: bucket label
        df["norm_age_group"] = df["norm_age_years"].apply(self._bucket_age)

        # norm_outcomes: list of outcome strings (split from comma-joined field)
        df["norm_outcomes"] = df[OUTCOME_FIELD].apply(self._parse_outcomes)

        # norm_country: occurcountry with fallback to reporter country
        df["norm_country"] = df[COUNTRY_FIELD].where(
            df[COUNTRY_FIELD].notna(),
            other=df[COUNTRY_FALLBACK_FIELD],
        )

        return df

    # ------------------------------------------------------------------
    # Normalisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_age_to_years(row: pd.Series) -> float | None:
        """
        Convert patient_patientonsetage to years using patient_patientonsetageunit.

        Rules:
          - If age is null → None (→ Unknown bucket)
          - If unit is 'year' or null → age as-is (assume years per ICSR convention)
          - If unit is 'month'/'week'/'day' → convert using AGE_UNIT_TO_YEARS
          - If unit is '800' or unrecognised → None (→ Unknown bucket)
        """
        age = row[AGE_FIELD]
        unit = row[AGE_UNIT_FIELD]

        if pd.isna(age):
            return None

        age = float(age)

        if pd.isna(unit) or str(unit).lower() == "year":
            return age

        unit_lower = str(unit).lower()

        if unit_lower == INVALID_AGE_UNIT_CODE:
            return None

        factor = AGE_UNIT_TO_YEARS.get(unit_lower)
        if factor is None:
            return None   # Unrecognised unit → Unknown

        return age * factor

    @staticmethod
    def _bucket_age(age_years: float | None) -> str:
        """
        Assign an age group label given age in years.
        If age_years is None or NaN → AGE_UNKNOWN_LABEL.
        """
        if age_years is None or pd.isna(age_years):
            return AGE_UNKNOWN_LABEL

        for label, low, high in AGE_BUCKETS:
            if low <= age_years < high:
                return label

        return AGE_UNKNOWN_LABEL  # Should not reach here given float("inf") upper bound

    @staticmethod
    def _parse_outcomes(raw: str | None) -> list[str]:
        """
        Split the comma-concatenated outcome field into a list of clean outcome tokens.
        e.g. "recovered/resolved,fatal" → ["recovered/resolved", "fatal"]
        """
        if pd.isna(raw) or not raw:
            return []
        return [o.strip() for o in str(raw).split(OUTCOME_SEPARATOR) if o.strip()]

    # ------------------------------------------------------------------
    # Build result
    # ------------------------------------------------------------------

    def _build_result(self, df: pd.DataFrame, fatal: bool) -> ValidationResult:
        """Construct a ValidationResult from accumulated issues and dataset stats."""
        if fatal or CASE_ID_FIELD not in df.columns:
            # Can't compute metadata safely — return minimal result
            return ValidationResult(
                is_valid=False,
                issues=self._issues,
                metadata=DatasetMetadata(
                    source_file=str(self.file_path),
                    total_rows=len(df),
                    unique_cases=0,
                    serious_cases=0,
                    non_serious_cases=0,
                    expedited_cases=0,
                    reporting_period_start=_today(),
                    reporting_period_end=_today(),
                    unique_reaction_pts=0,
                    cases_with_multiple_reactions=0,
                    missing_age_rows=0,
                    missing_sex_rows=0,
                    missing_country_rows=0,
                ),
            )

        cases = df.drop_duplicates(subset=CASE_ID_FIELD)
        rows_per_case = df.groupby(CASE_ID_FIELD).size()

        # Date range from report_date
        dates = pd.to_datetime(df[DATE_FIELD], errors="coerce").dropna()
        period_start = dates.min().date() if not dates.empty else _today()
        period_end = dates.max().date() if not dates.empty else _today()

        has_errors = any(i.severity == Severity.ERROR for i in self._issues)

        metadata = DatasetMetadata(
            source_file=str(self.file_path),
            total_rows=len(df),
            unique_cases=int(cases.shape[0]),
            serious_cases=int((cases[SERIOUS_FIELD] == SERIOUS_VALUE).sum()),
            non_serious_cases=int((cases[SERIOUS_FIELD] == NOT_SERIOUS_VALUE).sum()),
            expedited_cases=int((cases[EXPEDITE_FIELD] == EXPEDITE_YES).sum()),
            reporting_period_start=period_start,
            reporting_period_end=period_end,
            unique_reaction_pts=int(df[REACTION_FIELD].nunique()),
            cases_with_multiple_reactions=int((rows_per_case > 1).sum()),
            missing_age_rows=int(df[AGE_FIELD].isna().sum()),
            missing_sex_rows=int(df["patient_patientsex"].isna().sum()),
            missing_country_rows=int(df[COUNTRY_FIELD].isna().sum()),
        )

        return ValidationResult(
            is_valid=not has_errors,
            issues=self._issues,
            metadata=metadata,
        )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _today():
    """Return today's date — used as fallback when dates cannot be computed."""
    from datetime import date
    return date.today()
