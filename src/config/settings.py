"""
src/config/settings.py

Central configuration: field names, expected value encodings, and
validation rules derived from Stage 1 data inspection.

Nothing here is hardcoded business logic — it is a single source of truth
for the column names and value conventions the dataset uses.
If the dataset schema changes, this file is the only place to update.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Primary key
# ---------------------------------------------------------------------------
CASE_ID_FIELD = "safetyreportid"

# ---------------------------------------------------------------------------
# Date fields
# The dataset provides two representations of the receive date:
#   - receivedate  : int64, YYYYMMDD format, e.g. 20241227
#   - report_date  : datetime64, already parsed by openpyxl
# We use report_date as the primary datetime column for analysis.
# receivedate is validated for completeness but not used directly in analysis.
# ---------------------------------------------------------------------------
DATE_FIELD = "report_date"          # pre-parsed datetime column
RECEIVEDATE_FIELD = "receivedate"   # integer YYYYMMDD for validation

# ---------------------------------------------------------------------------
# Seriousness fields
# Top-level: series == "serious" | "not serious"
# Six criterion sub-fields: "yes" | "no"  (NOT "1"/"0")
# ---------------------------------------------------------------------------
SERIOUS_FIELD = "serious"
SERIOUS_VALUE = "serious"
NOT_SERIOUS_VALUE = "not serious"

SERIOUSNESS_CRITERIA = [
    "seriousnessdeath",
    "seriousnesslifethreatening",
    "seriousnesshospitalization",
    "seriousnessdisabling",
    "seriousnesscongenitalanomali",
    "seriousnessother",
]
CRITERION_YES = "yes"
CRITERION_NO = "no"

# ---------------------------------------------------------------------------
# Expedited / 15-day alert field
# Values: "yes" | "no"
# ---------------------------------------------------------------------------
EXPEDITE_FIELD = "fulfillexpeditecriteria"
EXPEDITE_YES = "yes"

# ---------------------------------------------------------------------------
# Patient demographics
# ---------------------------------------------------------------------------
SEX_FIELD = "patient_patientsex"
AGE_FIELD = "patient_patientonsetage"
AGE_UNIT_FIELD = "patient_patientonsetageunit"
AGE_GROUP_FIELD = "patient_patientagegroup"   # 97% blank — not used

# Age unit values found in Stage 1
VALID_AGE_UNITS = {"year", "month", "week", "day"}
INVALID_AGE_UNIT_CODE = "800"   # unknown/invalid code found in data

# Age unit conversion factors (to years)
AGE_UNIT_TO_YEARS: dict[str, float] = {
    "year": 1.0,
    "month": 1 / 12,
    "week": 1 / 52,
    "day": 1 / 365,
}

# Age buckets (label → (min_inclusive, max_exclusive))
# Applied in Python; LLM must never perform this bucketing.
AGE_BUCKETS: list[tuple[str, float, float]] = [
    ("0-17",  0,   18),
    ("18-44", 18,  45),
    ("45-64", 45,  65),
    ("65-74", 65,  75),
    ("75+",   75,  float("inf")),
]
AGE_UNKNOWN_LABEL = "Unknown"

# ---------------------------------------------------------------------------
# Geographic fields
# Decision: occurcountry is the primary field.
# primarysource_reportercountry is 100% complete (vs 99.3%) but nearly identical.
# The "eu" value is a regional code, not a country — flagged in limitations.
# ---------------------------------------------------------------------------
COUNTRY_FIELD = "occurcountry"
COUNTRY_FALLBACK_FIELD = "primarysource_reportercountry"
COUNTRY_REGIONAL_CODE = "eu"   # non-specific country value

# ---------------------------------------------------------------------------
# Reaction fields
# patient_reaction_reactionmeddrapt: one MedDRA PT per row (100% non-null)
# patient_reaction_reactionoutcome:  concatenated multi-outcome string, comma-separated
# ---------------------------------------------------------------------------
REACTION_FIELD = "patient_reaction_reactionmeddrapt"
OUTCOME_FIELD = "patient_reaction_reactionoutcome"
OUTCOME_SEPARATOR = ","

# Known outcome tokens (lowercase)
OUTCOME_RECOVERED = "recovered/resolved"
OUTCOME_RECOVERING = "recovering/resolving"
OUTCOME_NOT_RECOVERED = "not recovered/not resolved/ongoing"
OUTCOME_FATAL = "fatal"
OUTCOME_UNKNOWN = "unknown"

# ---------------------------------------------------------------------------
# Duplicate field (100% null in this dataset — not usable)
# ---------------------------------------------------------------------------
DUPLICATE_FIELD = "duplicate"

# ---------------------------------------------------------------------------
# Report type
# ---------------------------------------------------------------------------
REPORT_TYPE_FIELD = "reporttype"

# ---------------------------------------------------------------------------
# Minimum required columns
# These must exist in the dataset. If any are missing, validation fails hard.
# ---------------------------------------------------------------------------
REQUIRED_COLUMNS: list[str] = [
    CASE_ID_FIELD,
    SERIOUS_FIELD,
    *SERIOUSNESS_CRITERIA,
    EXPEDITE_FIELD,
    DATE_FIELD,
    RECEIVEDATE_FIELD,
    SEX_FIELD,
    AGE_FIELD,
    AGE_UNIT_FIELD,
    COUNTRY_FIELD,
    COUNTRY_FALLBACK_FIELD,
    REACTION_FIELD,
    OUTCOME_FIELD,
]
