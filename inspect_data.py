"""
Stage 1: Data Inspection Script
Inspects the Bisoprolol ICSR Excel file to understand schema,
data quality, missingness, and key field distributions.
Run: python inspect_data.py
"""

import pandas as pd
import numpy as np

FILE = "Bisoprolol_icsr_sample_1068rows.xlsx"
df = pd.read_excel(FILE)

SEP = "=" * 60

print(SEP)
print("BASIC SHAPE")
print(SEP)
total_rows = len(df)
unique_cases = df["safetyreportid"].nunique()
print(f"Total rows:    {total_rows}")
print(f"Unique cases (unique safetyreportid): {unique_cases}")
rows_per_case = df.groupby("safetyreportid").size()
print(f"Max rows per case: {rows_per_case.max()}")
print(f"Cases with > 1 row: {(rows_per_case > 1).sum()}")
print(f"Rows minus cases (multi-reaction surplus): {total_rows - unique_cases}")
print()

# Case-level dedup for case-level stats
cases = df.drop_duplicates(subset="safetyreportid")

print(SEP)
print("SERIOUSNESS (case-level)")
print(SEP)
print(f"Cases checked: {len(cases)}")
print("serious value_counts:")
print(cases["serious"].value_counts(dropna=False).to_string())
print()
seriousness_cols = [
    "seriousnessdeath",
    "seriousnesslifethreatening",
    "seriousnesshospitalization",
    "seriousnessdisabling",
    "seriousnesscongenitalanomali",
    "seriousnessother",
]
print("Seriousness criteria (case-level, value=1 means criterion met):")
for col in seriousness_cols:
    yes = (cases[col] == "1").sum()
    print(f"  {col}: {yes}")
print()

print(SEP)
print("EXPEDITED / 15-DAY ALERTS (case-level)")
print(SEP)
print("fulfillexpeditecriteria value_counts:")
print(cases["fulfillexpeditecriteria"].value_counts(dropna=False).to_string())
print()

print(SEP)
print("DATE FIELDS")
print(SEP)
print(f"receivedate dtype:  {df['receivedate'].dtype}")
print(f"receivedate sample: {df['receivedate'].head(5).tolist()}")
print(f"report_date dtype:  {df['report_date'].dtype}")
print(f"report_date min:    {df['report_date'].min()}")
print(f"report_date max:    {df['report_date'].max()}")

# Try parsing receivedate as YYYYMMDD integer
try:
    rd_str = df["receivedate"].astype(str)
    rd_parsed = pd.to_datetime(rd_str, format="%Y%m%d", errors="coerce")
    valid = rd_parsed.notna().sum()
    print(f"receivedate parsed as YYYYMMDD: {valid}/{total_rows} valid")
    print(f"  min: {rd_parsed.min()}")
    print(f"  max: {rd_parsed.max()}")
except Exception as e:
    print(f"Could not parse receivedate: {e}")
print()

print(SEP)
print("AGE FIELDS")
print(SEP)
print(f"patient_patientonsetage non-null:  {df['patient_patientonsetage'].notna().sum()} / {total_rows}")
print(f"patient_patientonsetage range:     {df['patient_patientonsetage'].min()} - {df['patient_patientonsetage'].max()}")
print("patient_patientonsetageunit value_counts:")
print(df["patient_patientonsetageunit"].value_counts(dropna=False).to_string())
print("patient_patientagegroup value_counts:")
print(df["patient_patientagegroup"].value_counts(dropna=False).to_string())
print()

print(SEP)
print("SEX (row-level)")
print(SEP)
print(df["patient_patientsex"].value_counts(dropna=False).to_string())
print()

print(SEP)
print("COUNTRY FIELDS (case-level)")
print(SEP)
print(f"occurcountry non-null: {cases['occurcountry'].notna().sum()} / {len(cases)}")
print("Top 15 occurcountry:")
print(cases["occurcountry"].value_counts(dropna=False).head(15).to_string())
print()
print(f"primarysource_reportercountry non-null: {cases['primarysource_reportercountry'].notna().sum()} / {len(cases)}")
print("Top 15 primarysource_reportercountry:")
print(cases["primarysource_reportercountry"].value_counts(dropna=False).head(15).to_string())
print()

print(SEP)
print("REACTIONS (row-level)")
print(SEP)
print(f"patient_reaction_reactionmeddrapt non-null: {df['patient_reaction_reactionmeddrapt'].notna().sum()} / {total_rows}")
print(f"Unique reaction PTs: {df['patient_reaction_reactionmeddrapt'].nunique()}")
print("Top 20 reactions:")
print(df["patient_reaction_reactionmeddrapt"].value_counts(dropna=False).head(20).to_string())
print()

print(SEP)
print("REACTION OUTCOMES (row-level)")
print(SEP)
print(df["patient_reaction_reactionoutcome"].value_counts(dropna=False).to_string())
print()

print(SEP)
print("MISSINGNESS — KEY FIELDS")
print(SEP)
key_fields = [
    "safetyreportid", "serious", "receivedate", "report_date",
    "occurcountry", "primarysource_reportercountry",
    "patient_patientonsetage", "patient_patientsex",
    "patient_reaction_reactionmeddrapt", "patient_reaction_reactionoutcome",
    "fulfillexpeditecriteria", "seriousnessdeath", "seriousnesslifethreatening",
    "seriousnesshospitalization", "seriousnessdisabling",
    "seriousnesscongenitalanomali", "seriousnessother",
    "patient_patientagegroup", "duplicate",
]
for f in key_fields:
    if f in df.columns:
        null_count = df[f].isna().sum()
        pct = null_count / total_rows * 100
        print(f"  {f}: {null_count} null ({pct:.1f}%)")
    else:
        print(f"  {f}: COLUMN NOT FOUND")
print()

print(SEP)
print("DUPLICATE FLAG")
print(SEP)
print(df["duplicate"].value_counts(dropna=False).to_string())
print()

print(SEP)
print("REPORTER QUALIFICATION")
print(SEP)
print(df["primarysource_qualification"].value_counts(dropna=False).to_string())
print()

print(SEP)
print("DRUG CHARACTERIZATION (suspect vs co-suspect vs interacting)")
print(SEP)
print(df["patient_drug_drugcharacterization"].value_counts(dropna=False).to_string())
print()

print(SEP)
print("REPORT TYPE")
print(SEP)
print(cases["reporttype"].value_counts(dropna=False).to_string())
print()

print(SEP)
print("MEDICINAL PRODUCT (spot check)")
print(SEP)
print(df["patient_drug_medicinalproduct"].value_counts(dropna=False).head(10).to_string())
print()

print(SEP)
print("DONE")
print(SEP)
