"""Machine-readable generation, validation, and human-review state."""
import json
from pathlib import Path

REQUIRED_SECTIONS = {"Reporting Period", "Narrative Summary and Analysis", "Summary Analysis of Cases", "Reaction/Adverse Event Analysis", "Serious Cases / 15-Day Alerts", "Trends and Important Observations", "History of Actions", "Case Index / Listing"}

def _validation_status(section):
    """Return automated validation state without changing human review state."""
    notes = list(getattr(section, "validation_notes", []) or [])
    if any("[CONTRADICTED]" in note for note in notes):
        return "FLAGGED"
    if "[GENERATION ERROR]" in (getattr(section, "generated_text", "") or ""):
        return "INCOMPLETE"
    if any("[UNVERIFIED]" in note for note in notes):
        return "PASS_WITH_WARNINGS"
    return "PASS"

def write_review_manifest(report_path, sections, generation_status):
    report_path = Path(report_path)
    per_section = {}
    issues = []
    warnings = []
    for section in sections:
        notes = list(getattr(section, "validation_notes", []) or [])
        human_status = getattr(getattr(section, "review_status", None), "value", "PENDING").upper()
        per_section[section.section_name] = {
            "status": human_status,
            "review_status": human_status,
            "validation_status": _validation_status(section),
            "generated": bool((section.generated_text or "").strip()),
            "validation_notes": notes,
        }
        issues.extend(note for note in notes if "[CONTRADICTED]" in note)
        warnings.extend(note for note in notes if "[UNVERIFIED]" in note)
    missing = sorted(REQUIRED_SECTIONS - set(per_section))
    generation = "INCOMPLETE" if generation_status == "INCOMPLETE" or missing else "COMPLETE"
    overall = "FLAGGED" if issues else ("PASS_WITH_WARNINGS" if warnings else "PASS")
    approval = "BLOCKED" if generation == "INCOMPLETE" or issues or missing else "PENDING_HUMAN_REVIEW"
    data = {"generation_status": generation, "overall_validation_status": overall, "per_section": per_section, "issues": issues, "warnings": warnings, "missing_required_sections": missing, "approval_status": approval}
    output = report_path.with_suffix(".review.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return output
