"""
src/review.py â€” GenAR Human Review CLI

Usage:
    python -X utf8 src/review.py reports/draft_report.md

Workflow:
    1. Parse draft_report.md to extract generation/validation status.
    2. Display a structured summary for the reviewer.
    3. Block approval if report is INCOMPLETE or has CONTRADICTED claims.
    4. On approval  â†’ write reports/final_report.md
    5. On rejection â†’ leave draft unchanged; do NOT touch final_report.md

The final report prepends a human-approval header to the draft content.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Parsing helpers
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _count_pattern(content: str, pattern: str) -> int:
    return len(re.findall(pattern, content))


def _extract_generation_status(content: str) -> str:
    """Determine if generation was COMPLETE or INCOMPLETE."""
    if "[GENERATION ERROR]" in content:
        return "INCOMPLETE"
    match = re.search(r"\*\*Generation Status:\*\*\s*(.+)", content)
    if match:
        return match.group(1).strip()
    return "COMPLETE"


def _extract_sections(content: str) -> list[dict]:
    """
    Extract each PADER section heading and its review status from the draft.
    Returns a list of {name, status} dicts.
    """
    # Match lines like: ## 2. Narrative Summary and Analysis
    section_pattern = re.compile(r"^## (\d+)\.\s+(.+)$", re.MULTILINE)
    status_pattern  = re.compile(r"\*Review Status: \*\*(\w+)\*\*\*")

    sections = []
    matches = list(section_pattern.finditer(content))

    for i, m in enumerate(matches):
        section_num  = m.group(1)
        section_name = m.group(2).strip()
        # Skip non-section headings (Validation Summary, Generation Notes)
        if section_name in ("Validation Summary", "Generation Notes"):
            continue
        # Find status in the text immediately following this heading
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        chunk = content[m.end(): end]
        status_m = status_pattern.search(chunk)
        status = status_m.group(1).upper() if status_m else "UNKNOWN"
        sections.append({
            "number": int(section_num),
            "name": section_name,
            "status": status,
        })

    return sections


def _extract_validation_table(content: str) -> list[dict]:
    """Parse the Validation Summary table rows."""
    rows = []
    in_table = False
    for line in content.splitlines():
        if "| # | Section | Status |" in line:
            in_table = True
            continue
        if in_table:
            if line.startswith("|---|"):
                continue
            if not line.startswith("|"):
                break
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 5:
                rows.append({
                    "number":       parts[0],
                    "section":      parts[1],
                    "status":       parts[2],
                    "contradicted": int(parts[3]),
                    "unverified":   int(parts[4]),
                })
    return rows


def _count_contradicted(content: str) -> int:
    return _count_pattern(content, r"\[CONTRADICTED\]")


def _count_unverified(content: str) -> int:
    return _count_pattern(content, r"\[UNVERIFIED\]")


def _is_approvable(gen_status: str, contradicted: int, sections: list[dict]) -> tuple[bool, str]:
    """
    Determine whether the draft is eligible for approval.

    Blocking conditions:
    - Generation status contains 'INCOMPLETE'
    - Any CONTRADICTED claims exist
    - Any required section is MISSING
    """
    required = {
        "Reporting Period",
        "Narrative Summary and Analysis",
        "Summary Analysis of Cases",
        "Reaction/Adverse Event Analysis",
        "Serious Cases / 15-Day Alerts",
        "Trends and Important Observations",
        "History of Actions",
        "Case Index / Listing",
    }
    present = {s["name"] for s in sections}
    missing = required - present

    if "INCOMPLETE" in gen_status.upper():
        return False, f"Report generation is INCOMPLETE. Resolve generation errors first."
    if missing:
        return False, f"Required sections missing: {', '.join(sorted(missing))}."
    if contradicted > 0:
        return (
            False,
            f"{contradicted} CONTRADICTED claim(s) detected. "
            "Contradictions must be resolved before approval.",
        )
    return True, ""


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Main
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

SEPARATOR = "=" * 62


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="genar-review",
        description="GenAR Human Review CLI",
    )
    parser.add_argument(
        "draft_file",
        help="Path to the draft report (e.g., reports/draft_report.md)",
    )
    args = parser.parse_args()

    draft_path = Path(args.draft_file)
    if not draft_path.exists():
        print(f"Error: Draft file '{draft_path}' not found.", file=sys.stderr)
        return 1

    content = draft_path.read_text(encoding="utf-8")
    manifest_path = draft_path.with_suffix(".review.json")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        gen_status = manifest.get("generation_status", "INCOMPLETE")
        section_map = manifest.get("per_section", {})
        sections = [{"number": i, "name": name, "status": data.get("status", "UNKNOWN")} for i, (name, data) in enumerate(section_map.items(), start=1)]
        val_rows = []
        contradicted = len(manifest.get("issues", []))
        unverified = len(manifest.get("warnings", []))
    else:
        # Legacy drafts remain reviewable; all new pipeline output is manifest-first.
        gen_status = _extract_generation_status(content)
        sections = _extract_sections(content)
        val_rows = _extract_validation_table(content)
        contradicted = _count_contradicted(content)
        unverified = _count_unverified(content)

    approvable, block_reason = _is_approvable(gen_status, contradicted, sections)

    # â”€â”€ Display â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print()
    print(SEPARATOR)
    print("GenAR Human Review")
    print(SEPARATOR)
    print()
    print(f"Report:  {draft_path.resolve()}")
    print()
    print(f"Generation Status:  {gen_status}")
    print(f"Contradicted claims: {contradicted}")
    print(f"Unverified claims:   {unverified}")
    print()

    # Section table
    print(f"{'#':<4} {'Section':<40} {'Status':<20} {'Contra':<8} {'Unver'}")
    print("-" * 80)
    if val_rows:
        for row in val_rows:
            print(
                f"{row['number']:<4} {row['section']:<40} {row['status']:<20} "
                f"{row['contradicted']:<8} {row['unverified']}"
            )
    else:
        for s in sections:
            print(f"{s['number']:<4} {s['name']:<40} {s['status']:<20}")

    print()

    # Blocking message (if any)
    if not approvable:
        print(SEPARATOR)
        print(f"CANNOT APPROVE: {block_reason}")
        print(SEPARATOR)
        return 1

    # Approval prompt
    if unverified > 0:
        print(
            f"Note: {unverified} UNVERIFIED claim(s) remain. "
            "These could not be confirmed against evidence but are not contradictions. "
            "Human review is required."
        )
        print()

    try:
        choice = input("Approve this report? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nReview cancelled.")
        return 1

    if choice == "y":
        final_path = draft_path.parent / "final_report.md"
        approved_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        approval_header = "\n".join([
            "<!-- Human Review: APPROVED -->",
            f"<!-- Approved by: Human Reviewer -->",
            f"<!-- Approved at: {approved_at} -->",
            f"<!-- Source draft: {draft_path.name} -->",
            "",
        ])

        final_content = approval_header + content
        final_path.write_text(final_content, encoding="utf-8")

        print()
        print(SEPARATOR)
        print(f"APPROVED. Final report written: {final_path.resolve()}")
        print(SEPARATOR)
        return 0
    else:
        print()
        print(SEPARATOR)
        print("NOT APPROVED. Draft unchanged. Final report was NOT created.")
        print(SEPARATOR)
        return 0


if __name__ == "__main__":
    sys.exit(main())




