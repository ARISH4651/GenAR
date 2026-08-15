"""
src/models/schemas.py

Pydantic models for structured data flowing through the pipeline.

Pydantic is used here for:
  - Validation results (structured output of the validator)
  - Evidence store schemas (what gets written to evidence/*.json)
  - Data quality issue records

It is NOT used for row-by-row validation of the 1,068 CSV rows —
that is handled by vectorised Pandas operations in the validator,
which is far more efficient for tabular data.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    """Severity of a data quality issue."""
    ERROR = "error"       # Blocks pipeline execution
    WARNING = "warning"   # Noted but execution continues


class ReviewStatus(str, Enum):
    """Human-review status for a generated report section."""
    PENDING = "pending"
    APPROVED = "approved"
    FLAGGED = "flagged"


# ---------------------------------------------------------------------------
# Data quality
# ---------------------------------------------------------------------------

class DataQualityIssue(BaseModel):
    """A single data quality finding from the validation layer."""
    field: str
    severity: Severity
    message: str
    affected_rows: int = 0

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.field}: {self.message} ({self.affected_rows} rows)"


class ValidationResult(BaseModel):
    """
    Output of the DataValidator.

    Contains the validation verdict, all issues found, high-level
    dataset metadata, and a reference to the clean normalised dataframe
    (stored as a plain dict for serialisability; the validator returns
    the actual DataFrame separately).
    """
    is_valid: bool
    issues: list[DataQualityIssue] = Field(default_factory=list)
    metadata: "DatasetMetadata"

    @property
    def errors(self) -> list[DataQualityIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[DataQualityIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    def summary(self) -> str:
        lines = [
            f"Validation {'PASSED' if self.is_valid else 'FAILED'}",
            f"  Errors:   {len(self.errors)}",
            f"  Warnings: {len(self.warnings)}",
        ]
        for issue in self.issues:
            lines.append(f"  {issue}")
        return "\n".join(lines)


class DatasetMetadata(BaseModel):
    """High-level facts about the loaded dataset, computed deterministically."""
    source_file: str
    total_rows: int
    unique_cases: int
    serious_cases: int
    non_serious_cases: int
    expedited_cases: int
    reporting_period_start: date
    reporting_period_end: date
    unique_reaction_pts: int
    cases_with_multiple_reactions: int
    missing_age_rows: int
    missing_sex_rows: int
    missing_country_rows: int


# ---------------------------------------------------------------------------
# Evidence store schemas
# These mirror the JSON files written to evidence/
# ---------------------------------------------------------------------------

class CaseSummaryEvidence(BaseModel):
    """evidence/case_summary.json"""
    total_rows: int
    total_cases: int
    serious_cases: int
    non_serious_cases: int
    expedited_cases: int
    non_expedited_cases: int
    reporting_period_start: str
    reporting_period_end: str
    cases_with_multiple_reactions: int
    unique_reaction_pts: int


class DemographicsEvidence(BaseModel):
    """evidence/demographics.json"""
    sex_breakdown: dict[str, int]
    sex_missing: int
    age_group_breakdown: dict[str, int]
    age_missing_rows: int
    age_derivation_method: str
    age_buckets: list[str]


class ReactionEntry(BaseModel):
    """One entry in the top-reactions list."""
    reaction_pt: str
    count: int
    percent_of_reactions: float


class ReactionsEvidence(BaseModel):
    """evidence/reactions.json"""
    total_reaction_rows: int
    unique_reaction_pts: int
    top_reactions: list[ReactionEntry]
    top_serious_reactions: list[ReactionEntry]
    soc_analysis_available: bool = False
    soc_analysis_note: str = "No System Organ Class field supplied in dataset"


class OutcomeEntry(BaseModel):
    outcome: str
    count: int
    percent_of_reactions: float


class OutcomesEvidence(BaseModel):
    """evidence/outcomes.json"""
    total_reaction_rows: int
    outcomes: list[OutcomeEntry]
    parsing_note: str


class SeriousnessCriterionCount(BaseModel):
    criterion: str
    cases_meeting_criterion: int
    note: str = "Criteria are not mutually exclusive; same case may meet multiple"


class AlertsEvidence(BaseModel):
    """evidence/alerts.json"""
    expedited_cases: int
    non_expedited_cases: int
    total_cases: int
    expedited_field_used: str
    expedited_interpretation: str
    seriousness_criteria_breakdown: list[SeriousnessCriterionCount]


class MonthlyCount(BaseModel):
    year_month: str   # e.g. "2025-01"
    count: int


class TrendsEvidence(BaseModel):
    """evidence/trends.json"""
    monthly_case_counts: list[MonthlyCount]
    reporting_period_start: str
    reporting_period_end: str
    trend_note: str = (
        "Numerical trends are observations only. "
        "Signal assessment requires qualified human review."
    )


class CaseListingEntry(BaseModel):
    """One row in evidence/case_listing.json"""
    safetyreportid: int
    receivedate: str
    country: str
    sex: str
    age_years: float | None
    age_group: str
    is_serious: bool
    is_expedited: bool
    reactions: list[str]
    outcomes: list[str]
    seriousness_criteria: list[str]


class LimitationsEvidence(BaseModel):
    """evidence/limitations.json"""
    expectedness: dict[str, Any]
    soc_analysis: dict[str, Any]
    history_of_actions: dict[str, Any]
    cumulative_counts: dict[str, Any]
    country_granularity: dict[str, Any]
    age_completeness: dict[str, Any]


# ---------------------------------------------------------------------------
# Report section
# ---------------------------------------------------------------------------

class ReportSection(BaseModel):
    """A single section of the generated PADER report."""
    section_name: str
    evidence_keys: list[str]      # which evidence files were used
    generated_text: str
    validation_notes: list[str] = Field(default_factory=list)
    review_status: ReviewStatus = ReviewStatus.PENDING
    generated_at: datetime | None = None


# ---------------------------------------------------------------------------
# LLM Response Model
# ---------------------------------------------------------------------------

class NarrativeResponse(BaseModel):
    """Structured response expected from the single Gemini API call."""
    narrative_summary: str
    case_analysis: str
    reaction_analysis: str
    trends: str


# ---------------------------------------------------------------------------
# Structured Evidence Facts & Validation
# ---------------------------------------------------------------------------

class EvidenceFact(BaseModel):
    """A single structured fact extracted from evidence for validation."""
    subject: str
    metric: str
    value: int | float
    unit: str


class ClaimState(str, Enum):
    """The result of mapping a generated numeric/factual claim to evidence."""
    VERIFIED     = "VERIFIED"      # Evidence explicitly supports the claim
    UNVERIFIED   = "UNVERIFIED"    # Claim is factual but evidence cannot confirm it
    CONTRADICTED = "CONTRADICTED"  # Claim conflicts with known deterministic evidence


class ValidationStatus(str, Enum):
    """Overall or per-section validation status."""
    PASS              = "PASS"               # All claims verified, no issues
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS" # UNVERIFIED claims present; no contradictions
    FLAGGED           = "FLAGGED"            # CONTRADICTED claims or capability violations


class OutputValidationIssue(BaseModel):
    """A single issue raised during output validation."""
    type: str                          # CONTRADICTED_NUMERIC_CLAIM, CAPABILITY_VIOLATION, etc.
    state: ClaimState = ClaimState.CONTRADICTED
    claim: str                         # Human-readable description of the problem
    sentence: str = ""                 # The exact generated sentence containing the claim
    expected: Any | None = None        # What evidence says the value should be
    observed: Any | None = None        # What the generated text claimed
    reason: str = ""                   # Explanation for the issue


class SectionValidationResult(BaseModel):
    """Validation result for a single narrative section."""
    section_name: str
    status: ValidationStatus = ValidationStatus.PASS
    issues: list[OutputValidationIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_claims: int = 0


class OutputValidationResult(BaseModel):
    """Aggregate validation result across all narrative sections."""
    status: ValidationStatus = ValidationStatus.PASS
    checked_claims: int = 0
    issues: list[OutputValidationIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # Per-section breakdown for report_builder to assign individual statuses
    per_section: dict[str, SectionValidationResult] = Field(default_factory=dict)
