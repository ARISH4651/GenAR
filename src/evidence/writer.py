"""
src/evidence/writer.py

Writes the evidence dict produced by AnalysisEngine.run() to individual
JSON files in the evidence/ directory.

One file per evidence section:
  evidence/metadata.json
  evidence/case_summary.json
  evidence/demographics.json
  evidence/reactions.json
  evidence/outcomes.json
  evidence/alerts.json
  evidence/trends.json
  evidence/case_listing.json
  evidence/capabilities.json

These files are the VERIFIED EVIDENCE STORE — the authoritative source
of facts for the LLM generation step. They are human-readable and
auditable independently of the generated report.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Sections that get their own JSON file
EVIDENCE_SECTIONS = [
    "metadata",
    "case_summary",
    "demographics",
    "reactions",
    "outcomes",
    "alerts",
    "trends",
    "case_listing",
    "capabilities",
]


class EvidenceWriter:
    """
    Serialises the analysis evidence dict to evidence/*.json files.

    Usage:
        writer = EvidenceWriter("evidence/")
        writer.write(evidence_dict)
    """

    def __init__(self, evidence_dir: str | Path = "evidence") -> None:
        self.evidence_dir = Path(evidence_dir)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def write(self, evidence: dict) -> dict[str, Path]:
        """
        Write all sections from evidence dict to individual JSON files.

        Returns a dict mapping section name → file path for verification.
        Raises KeyError if a required section is missing from evidence.
        """
        written: dict[str, Path] = {}
        missing = [s for s in EVIDENCE_SECTIONS if s not in evidence]
        if missing:
            raise KeyError(f"Evidence dict is missing required sections: {missing}")

        for section in EVIDENCE_SECTIONS:
            path = self._write_section(section, evidence[section])
            written[section] = path

        logger.info(
            "Evidence store written: %d files in %s",
            len(written),
            self.evidence_dir,
        )
        return written

    def _write_section(self, section: str, data) -> Path:
        """Serialise one section to a JSON file."""
        path = self.evidence_dir / f"{section}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=_json_default)
        logger.debug("Wrote %s (%d bytes)", path.name, path.stat().st_size)
        return path


def _json_default(obj):
    """Fallback JSON serialiser for non-standard types."""
    import numpy as np
    import pandas as pd

    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return str(obj.date())
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")
