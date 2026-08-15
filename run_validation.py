"""
Quick smoke test for Stage 2 — runs the validator against the real dataset
and prints the result. Not a pytest test; run directly with:

    python run_validation.py

This script is for development verification only.
"""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Run from project root so 'src' is on sys.path
sys.path.insert(0, ".")

from src.validation.validator import DataValidator

FILE = "Bisoprolol_icsr_sample_1068rows.xlsx"

print("=" * 60)
print("Stage 2 — Validation Smoke Test")
print("=" * 60)

validator = DataValidator(FILE)
result, clean_df = validator.validate()

print(result.summary())
print()

print("=== DATASET METADATA ===")
m = result.metadata
print(f"  Source file:              {m.source_file}")
print(f"  Total rows:               {m.total_rows}")
print(f"  Unique cases:             {m.unique_cases}")
print(f"  Serious cases:            {m.serious_cases}")
print(f"  Non-serious cases:        {m.non_serious_cases}")
print(f"  Expedited cases:          {m.expedited_cases}")
print(f"  Reporting period:         {m.reporting_period_start} to {m.reporting_period_end}")
print(f"  Unique reaction PTs:      {m.unique_reaction_pts}")
print(f"  Multi-reaction cases:     {m.cases_with_multiple_reactions}")
print(f"  Missing age rows:         {m.missing_age_rows}")
print(f"  Missing sex rows:         {m.missing_sex_rows}")
print(f"  Missing country rows:     {m.missing_country_rows}")
print()

print("=== NORMALISED COLUMNS ADDED ===")
norm_cols = [c for c in clean_df.columns if c.startswith("norm_")]
for col in norm_cols:
    print(f"  {col}: {clean_df[col].dtype}")
print()

print("=== SAMPLE norm_age_group DISTRIBUTION ===")
print(clean_df["norm_age_group"].value_counts(dropna=False).to_string())
print()

print("=== SAMPLE norm_outcomes (first 5 rows) ===")
for i, outcomes in enumerate(clean_df["norm_outcomes"].head(5)):
    print(f"  row {i}: {outcomes}")
print()

print("=== norm_is_serious distribution ===")
print(clean_df.drop_duplicates(subset="safetyreportid")["norm_is_serious"].value_counts().to_string())
print()

print("=== norm_is_expedited distribution ===")
print(clean_df.drop_duplicates(subset="safetyreportid")["norm_is_expedited"].value_counts().to_string())
print()

if result.is_valid:
    print("✅ Validation PASSED — data is ready for Stage 3 (analysis engine)")
else:
    print("❌ Validation FAILED — fix errors above before proceeding")
    sys.exit(1)
