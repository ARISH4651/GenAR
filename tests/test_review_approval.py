import json
import subprocess
import sys
from pathlib import Path

REQUIRED = [
    "Reporting Period",
    "Narrative Summary and Analysis",
    "Summary Analysis of Cases",
    "Reaction/Adverse Event Analysis",
    "Serious Cases / 15-Day Alerts",
    "Trends and Important Observations",
    "History of Actions",
    "Case Index / Listing",
]

def _write_draft(tmp_path: Path, generation="COMPLETE", issues=None):
    draft = tmp_path / "draft_report.md"
    sections = []
    for i, name in enumerate(REQUIRED, 1):
        sections.extend([f"## {i}. {name}", "", "*Review Status: **PENDING***  ", "", f"Content for {name}.", ""])
    sections.extend(["## Validation Summary", "", "| # | Section | Status | Contradicted | Unverified |", "|---|---------|--------|-------------|------------|"])
    for i, name in enumerate(REQUIRED, 1):
        sections.append(f"| {i} | {name} | PASS | 0 | 0 |")
    sections.extend(["", "**Generation Status:** COMPLETE", ""])
    draft.write_text("\n".join(sections), encoding="utf-8")
    manifest = {
        "generation_status": generation,
        "overall_validation_status": "FLAGGED" if issues else "PASS",
        "per_section": {name: {"status": "PENDING", "review_status": "PENDING", "validation_status": "PASS", "generated": True, "validation_notes": []} for name in REQUIRED},
        "issues": issues or [],
        "warnings": [],
        "missing_required_sections": [],
        "approval_status": "BLOCKED" if generation == "INCOMPLETE" or issues else "PENDING_HUMAN_REVIEW",
    }
    draft.with_suffix(".review.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return draft

def _run_review(draft: Path, answer: str):
    return subprocess.run([sys.executable, "-X", "utf8", "src/review.py", str(draft)], input=answer + "\n", text=True, capture_output=True, cwd=Path(__file__).parents[1])

def test_approval_propagates_to_all_sections_and_preserves_validation(tmp_path):
    draft = _write_draft(tmp_path)
    result = _run_review(draft, "y")
    assert result.returncode == 0, result.stdout + result.stderr
    final = tmp_path / "final_report.md"
    assert final.exists()
    content = final.read_text(encoding="utf-8")
    assert "<!-- Human Review: APPROVED -->" in content
    assert content.count("*Review Status: **APPROVED***") == 8
    assert content.count("| PASS | 0 | 0 |") == 8
    manifest = json.loads(draft.with_suffix(".review.json").read_text(encoding="utf-8"))
    assert manifest["approval_status"] == "APPROVED"
    assert all(data["review_status"] == "APPROVED" for data in manifest["per_section"].values())
    assert all(data["validation_status"] == "PASS" for data in manifest["per_section"].values())

def test_rejection_does_not_create_or_modify_final(tmp_path):
    draft = _write_draft(tmp_path)
    final = tmp_path / "final_report.md"
    final.write_text("sentinel", encoding="utf-8")
    result = _run_review(draft, "n")
    assert result.returncode == 0
    assert final.read_text(encoding="utf-8") == "sentinel"
    assert "*Review Status: **PENDING***" in draft.read_text(encoding="utf-8")
    manifest = json.loads(draft.with_suffix(".review.json").read_text(encoding="utf-8"))
    assert manifest["approval_status"] == "REJECTED"

def test_incomplete_generation_is_not_approvable(tmp_path):
    draft = _write_draft(tmp_path, generation="INCOMPLETE")
    result = _run_review(draft, "y")
    assert result.returncode == 1
    assert not (tmp_path / "final_report.md").exists()

def test_contradicted_claims_are_not_approvable(tmp_path):
    draft = _write_draft(tmp_path, issues=["[CONTRADICTED] test claim"])
    result = _run_review(draft, "y")
    assert result.returncode == 1
    assert not (tmp_path / "final_report.md").exists()
