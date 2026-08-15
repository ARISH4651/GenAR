"""
src/evidence/reader.py

Reads specific evidence sections from evidence/*.json files.

Used by the LLM Context Builder (Stage 5) to retrieve only the evidence
sections required for each report section — not all evidence at once.

Design principle: selective retrieval prevents the LLM from receiving
irrelevant context that could encourage hallucination or confusion.
Each report section gets only the evidence it needs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class EvidenceReader:
    """
    Reads evidence sections from the evidence/ directory.

    Usage:
        reader = EvidenceReader("evidence/")
        case_summary = reader.get("case_summary")
        context = reader.get_many(["case_summary", "demographics"])
    """

    def __init__(self, evidence_dir: str | Path = "evidence") -> None:
        self.evidence_dir = Path(evidence_dir)

    def get(self, section: str) -> dict:
        """
        Read and return one evidence section.

        Raises FileNotFoundError if the section has not been generated.
        """
        path = self.evidence_dir / f"{section}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Evidence section '{section}' not found at {path}. "
                "Run the analysis engine first."
            )
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        logger.debug("Read evidence section: %s (%d bytes)", section, path.stat().st_size)
        return data

    def get_many(self, sections: list[str]) -> dict[str, dict]:
        """
        Read and return multiple evidence sections as a combined dict.

        Args:
            sections: List of section names, e.g. ["case_summary", "reactions"]

        Returns:
            Dict mapping section name → evidence dict.
        """
        return {section: self.get(section) for section in sections}

    def available_sections(self) -> list[str]:
        """Return names of evidence sections present on disk."""
        return [p.stem for p in sorted(self.evidence_dir.glob("*.json"))]
