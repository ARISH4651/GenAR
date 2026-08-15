"""
src/generation/context_builder.py

Builds the structured user prompt (context packet) for each report section.

Design principle:
  STATIC PROMPT (from prompts/*.txt)
  + DYNAMIC EVIDENCE (from evidence/*.json, section-specific)
  = LLM REQUEST

Each section gets ONLY the evidence it needs (from report_config.SECTION_EVIDENCE_MAP).
Large evidence sections (case_listing, 514 KB) are replaced with a compact summary
when passed to the LLM — the LLM never receives the full case table.

The context packet is a plain string (the Gemini user message). The system prompt
is passed separately via the GeminiProvider's system_instruction.
"""

import json
import logging
from pathlib import Path

from src.config.report_config import PROMPTS_DIR, NARRATIVE_PROMPT_FILE

logger = logging.getLogger(__name__)

# Maximum number of top reactions to include in context
MAX_REACTIONS_IN_CONTEXT = 20

class ContextBuilder:
    """
    Assembles the single unified user-message context packet for the Gemini LLM.
    """

    def __init__(self, prompts_dir: str | Path = PROMPTS_DIR) -> None:
        self.prompts_dir = Path(prompts_dir)
        self._prompt_cache: str | None = None

    def build_narrative_context(self, evidence: dict[str, dict]) -> str:
        """
        Build the user message containing all evidence for the narrative sections.

        Args:
            evidence: Dict of {evidence_key: evidence_dict} covering all required
                      data for the narrative generation.

        Returns:
            Formatted string to send as the user message to the LLM.
        """
        system_prompt = self._load_prompt()
        sanitized_evidence = self._sanitize_evidence(evidence)
        
        metadata = sanitized_evidence.get("metadata", {})
        capabilities = sanitized_evidence.get("capabilities", {})
        
        start = metadata.get("reporting_period_start", "unknown")
        end = metadata.get("reporting_period_end", "unknown")
        
        # Build individual JSON blocks for clarity
        blocks = []
        for key in ["case_summary", "demographics", "reactions", "outcomes", "alerts", "trends"]:
            if key in sanitized_evidence:
                block_json = json.dumps(sanitized_evidence[key], indent=2, ensure_ascii=False)
                blocks.append(f"{key.upper()}:\n```json\n{block_json}\n```\n")

        evidence_str = "\n".join(blocks)
        caps = json.dumps(capabilities, indent=2)

        message = (
            f"REPORT TYPE\nPADER-style\n\n"
            f"REPORTING PERIOD\n{start} to {end}\n\n"
            f"CAPABILITIES (Use this to determine if info is unavailable):\n```json\n{caps}\n```\n\n"
            f"VERIFIED EVIDENCE (authoritative — use only these figures):\n\n"
            f"{evidence_str}\n"
            f"INSTRUCTIONS:\n{system_prompt}"
        )

        logger.debug(
            "Unified Narrative Context built: %d chars, %d evidence keys",
            len(message), len(sanitized_evidence),
        )
        return message

    def _load_prompt(self) -> str:
        if self._prompt_cache is not None:
            return self._prompt_cache

        path = self.prompts_dir / NARRATIVE_PROMPT_FILE
        if not path.exists():
            raise FileNotFoundError(f"Narrative prompt file not found: {path}")

        text = path.read_text(encoding="utf-8").strip()
        self._prompt_cache = text
        return text

    def _sanitize_evidence(self, evidence: dict[str, dict]) -> dict[str, dict]:
        sanitized = {}
        for key, data in evidence.items():
            if key == "reactions":
                sanitized[key] = self._trim_reactions(data)
            elif key != "case_listing":
                # Ensure we never pass the full case listing to Gemini
                sanitized[key] = data
        return sanitized

    @staticmethod
    def _trim_reactions(reactions_data: dict) -> dict:
        result = dict(reactions_data)
        if "top_reactions" in result:
            result["top_reactions"] = result["top_reactions"][:MAX_REACTIONS_IN_CONTEXT]
        if "top_serious_reactions" in result:
            result["top_serious_reactions"] = result["top_serious_reactions"][:MAX_REACTIONS_IN_CONTEXT]
        return result
