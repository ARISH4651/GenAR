"""
src/config/report_config.py

Configuration-driven mapping of PADER report sections to evidence keys.

This is the central design decision that makes the system generalisable:
  - Adding a new section = add an entry to SECTION_EVIDENCE_MAP
  - Changing which evidence a section uses = update this map
  - Supporting PSUR/PBRER/DSUR = new maps in version1/

The LLM receives ONLY the evidence sections listed here for each section.
It never receives the full evidence store.
"""

from __future__ import annotations
from pathlib import Path

# ---------------------------------------------------------------------------
# Section categorization
# ---------------------------------------------------------------------------

NARRATIVE_SECTIONS: list[str] = [
    "Narrative Summary and Analysis",
    "Summary Analysis of Cases",
    "Reaction/Adverse Event Analysis",
    "Trends and Important Observations",
]

DETERMINISTIC_SECTIONS: list[str] = [
    "Reporting Period",
    "Serious Cases / 15-Day Alerts",
    "History of Actions",
    "Case Index / Listing",
]

# ---------------------------------------------------------------------------
# PADER section order (defines the order in the final report)
# ---------------------------------------------------------------------------
SECTION_ORDER: list[str] = [
    "Reporting Period",
    "Narrative Summary and Analysis",
    "Summary Analysis of Cases",
    "Reaction/Adverse Event Analysis",
    "Serious Cases / 15-Day Alerts",
    "Trends and Important Observations",
    "History of Actions",
    "Case Index / Listing",
]

# ---------------------------------------------------------------------------
# Prompt file for narrative generation
# ---------------------------------------------------------------------------
PROMPTS_DIR = Path("prompts")
NARRATIVE_PROMPT_FILE = "narrative.txt"

