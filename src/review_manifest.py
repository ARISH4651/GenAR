from __future__ import annotations
import json
from pathlib import Path

REQUIRED_SECTIONS = {"Reporting Period", "Narrative Summary and Analysis", "Summary Analysis of Cases", "Reaction/Adverse Event Analysis", "Serious Cases / 15-Day Alerts", "Trends and Important Observations", "History of Actions", "Case Index / Listing"}

def write_review_manifest(report_path, sections, generation_status):
    report_path = Path(report_path)
    per_section = {}
    issues = []
    warnings = []
    for section in sections:
        notes = list(getattr(section, "validation_notes", []) or [])
        status = getattr(getattr(section, "review_status", None), "value", "PENDING").upper()
        per_section[section.section_name] = {"status": status, "generated": bool((section.generated_text or "").strip()), "validation_notes": notes}
        issues.extend(n for n in notes if "[CONTRADICTED]" in n)
        warnings.extend(n for n in notes if "[UNVERIFIED]" in n)
    missing = sorted(REQUIRED_SECTIONS - set(per_section))
    generation = "INCOMPLETE" if generation_status == "INCOMPLETE" or missing else "COMPLETE"
    overall = "FLAGGED" if issues else ("PASS_WITH_WARNINGS" if warnings else "PASS")
    approval = "BLOCKED" if generation == "INCOMPLETE" or issues or missing else "PENDING_HUMAN_REVIEW"
    data = {"generation_status": generation, "overall_validation_status": overall, "per_section": per_section, "issues": issues, "warnings": warnings, "missing_required_sections": missing, "approval_status": approval}
    output = report_path.with_suffix(".review.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return output

