"""
run_analysis.py — Stage 3 + 4 smoke test

Runs the full deterministic pipeline:
  1. Load and validate the dataset
  2. Run the analysis engine
  3. Write evidence JSON files
  4. Print key numbers for verification

Usage:
    python -X utf8 run_analysis.py
"""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
sys.path.insert(0, ".")

from src.validation.validator import DataValidator
from src.analysis.engine import AnalysisEngine
from src.evidence.writer import EvidenceWriter
from src.evidence.reader import EvidenceReader

FILE = "Bisoprolol_icsr_sample_1068rows.xlsx"
EVIDENCE_DIR = "evidence"

print("=" * 60)
print("Stage 3+4 — Analysis Engine + Evidence Store Smoke Test")
print("=" * 60)

# Step 1: Validate
print("\n[Step 1] Validating dataset ...")
validator = DataValidator(FILE)
result, clean_df = validator.validate()
if not result.is_valid:
    print(result.summary())
    sys.exit(1)
print(f"  OK — {result.metadata.total_rows} rows, {result.metadata.unique_cases} cases")

# Step 2: Analyse
print("\n[Step 2] Running deterministic analysis ...")
engine = AnalysisEngine(source_file=FILE)
evidence = engine.run(clean_df)
print(f"  OK — {len(evidence)} evidence sections computed")

# Step 3: Write evidence store
print("\n[Step 3] Writing evidence JSON files ...")
writer = EvidenceWriter(EVIDENCE_DIR)
written = writer.write(evidence)
for section, path in written.items():
    size_kb = path.stat().st_size / 1024
    print(f"  {section:20s} -> {path.name} ({size_kb:.1f} KB)")

# Step 4: Verify via reader
print("\n[Step 4] Verifying evidence via reader ...")
reader = EvidenceReader(EVIDENCE_DIR)
cs = reader.get("case_summary")
dm = reader.get("demographics")
rx = reader.get("reactions")
tr = reader.get("trends")
lt = reader.get("capabilities")

print(f"\n{'='*60}")
print("VERIFIED EVIDENCE — KEY NUMBERS")
print(f"{'='*60}")
print(f"  Total rows:            {cs['total_rows']}")
print(f"  Total cases:           {cs['total_cases']}")
print(f"  Serious cases:         {cs['serious_cases']}")
print(f"  Non-serious cases:     {cs['non_serious_cases']}")
print(f"  Expedited cases:       {cs['expedited_cases']}")
print(f"  Multi-reaction cases:  {cs['cases_with_multiple_reactions']}")
print(f"  Reporting period:      {cs['reporting_period_start']} to {cs['reporting_period_end']}")
print(f"  Unique reaction PTs:   {cs['unique_reaction_pts']}")

print(f"\n  Age groups:")
for group, count in dm["age_group_breakdown"].items():
    print(f"    {group:10s}: {count}")

print(f"\n  Sex breakdown:")
for sex, count in dm["sex_breakdown"].items():
    print(f"    {sex:10s}: {count}")

print(f"\n  Top 5 reactions (all cases):")
for r in rx["top_reactions"][:5]:
    print(f"    {r['reaction_pt']:40s} n={r['count']:3d} ({r['percent_of_reactions']:.1f}%)")

print(f"\n  Top 5 serious reactions:")
for r in rx["top_serious_reactions"][:5]:
    print(f"    {r['reaction_pt']:40s} n={r['count']:3d} ({r['percent_of_reactions']:.1f}%)")

print(f"\n  Monthly trend (first 6 months):")
for m in tr["monthly_case_counts"][:6]:
    print(f"    {m['year_month']}: {m['count']} cases")

print(f"\n  Capabilities:") 
for key, val in lt.items():
    avail = val.get("available", "n/a")
    print(f"    {key:30s}: available={avail}")

print(f"\n{'='*60}")
print("All stages complete. Evidence store is ready.")
print("Next: Stage 5 — Evidence retrieval + Context builder")
print(f"{'='*60}")
