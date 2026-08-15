"""
src/generation/report_builder.py

ReportBuilder: orchestrates section-by-section report generation.

Flow per section:
  1. Look up required evidence keys from SECTION_EVIDENCE_MAP.
  2. Retrieve evidence via EvidenceReader (selective — not all evidence).
  3. Build context packet (ContextBuilder).
  4. Call LLM provider.
  5. Validate output (OutputValidator).
  6. Return ReportSection with generated text + validation notes.

Special handling for deterministic-body sections (Case Index / Listing):
  The LLM generates only the introductory paragraph.
  The case table is appended by MarkdownWriter from case_listing.json.

All LLM calls are logged with the section name and response length.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.config.report_config import (
    NARRATIVE_SECTIONS,
    DETERMINISTIC_SECTIONS,
    SECTION_ORDER,
)
from src.evidence.reader import EvidenceReader
from src.generation.context_builder import ContextBuilder
from src.generation.output_validator import OutputValidator
from src.generation import deterministic_builder
from src.llm.provider import LLMProvider, LLMError
from src.models.schemas import (
    ClaimState,
    NarrativeResponse,
    ReportSection,
    ReviewStatus,
    ValidationStatus,
)

logger = logging.getLogger(__name__)

class ReportGenerationResult:
    def __init__(self):
        self.sections: list[ReportSection] = []
        self.status = "VALIDATED"
        self.error: str | None = None

class ReportBuilder:
    """
    Generates all report sections.
    1. Deterministic sections via Python code.
    2. Narrative sections via a single Gemini API call.
    """

    def __init__(
        self,
        reader: EvidenceReader,
        provider: LLMProvider,
        evidence_dir: str = "evidence",
    ) -> None:
        self.reader = reader
        self.provider = provider
        self.context_builder = ContextBuilder()
        self.validator = OutputValidator()

    def build_all(self) -> ReportGenerationResult:
        result = ReportGenerationResult()
        sections_dict: dict[str, ReportSection] = {}

        # 1. Deterministic Sections
        logger.info("Generating %d deterministic sections...", len(DETERMINISTIC_SECTIONS))
        metadata = self.reader.get("metadata") or {}
        capabilities = self.reader.get("capabilities") or {}
        alerts = self.reader.get("alerts") or {}
        case_summary = self.reader.get("case_summary") or {}
        case_listing = self.reader.get("case_listing") or []
        
        # We know exactly which sections are deterministic
        det_map = {
            "Reporting Period": deterministic_builder.build_reporting_period(metadata),
            "Serious Cases / 15-Day Alerts": deterministic_builder.build_alerts(alerts, case_summary),
            "History of Actions": deterministic_builder.build_history_of_actions(capabilities),
            "Case Index / Listing": deterministic_builder.build_case_listing(case_listing),
        }

        for sec in DETERMINISTIC_SECTIONS:
            sections_dict[sec] = ReportSection(
                section_name=sec,
                evidence_keys=[],
                generated_text=det_map.get(sec, ""),
                validation_notes=["[INFO] Generated deterministically."],
                review_status=ReviewStatus.PENDING,
                generated_at=datetime.now(timezone.utc),
            )

        # 2. Narrative Sections
        logger.info("Generating narrative sections via LLM (1 API call)...")
        
        evidence_packet = {
            "metadata": metadata,
            "capabilities": capabilities,
            "case_summary": case_summary,
            "demographics": self.reader.get("demographics") or {},
            "reactions": self.reader.get("reactions") or {},
            "outcomes": self.reader.get("outcomes") or {},
            "alerts": alerts,
            "trends": self.reader.get("trends") or {},
        }
        
        user_message = self.context_builder.build_narrative_context(evidence_packet)
        system_prompt = self.context_builder._load_prompt() # Or move system prompt to provider config
        
        try:
            # We expect a structured Pydantic response
            response = self.provider.generate(system_prompt, user_message, response_schema=NarrativeResponse)
            
            # Map response fields back to section names
            generated_texts = {
                "Narrative Summary and Analysis": response.narrative_summary,
                "Summary Analysis of Cases": response.case_analysis,
                "Reaction/Adverse Event Analysis": response.reaction_analysis,
                "Trends and Important Observations": response.trends,
            }
            
            # Validate output
            validation = self.validator.validate(generated_texts, evidence_packet)
            
            # Per-section validation status and notes
            for sec_name in NARRATIVE_SECTIONS:
                sec_text = generated_texts.get(sec_name, "")
                sec_val = validation.per_section.get(sec_name)

                # Build human-readable validation notes for the report
                sec_notes: list[str] = []

                if sec_val is None:
                    sec_notes = ["[INFO] Automated checks passed."]
                    sec_status = ReviewStatus.PENDING
                else:
                    # Add CONTRADICTED issues first
                    for iss in sec_val.issues:
                        note = (
                            f"[CONTRADICTED] {iss.type}: {iss.claim}  \n"
                            f"  Observed: {iss.observed}  \n"
                            f"  Expected: {iss.expected}  \n"
                            f"  Reason: {iss.reason}"
                        )
                        sec_notes.append(note)

                    # Add UNVERIFIED warnings
                    for warn in sec_val.warnings:
                        sec_notes.append(warn)

                    if not sec_notes:
                        sec_notes = ["[INFO] All automated checks passed."]

                    # Map section validation status to review status
                    if sec_val.status == ValidationStatus.FLAGGED:
                        sec_status = ReviewStatus.FLAGGED
                        if result.status != "INCOMPLETE":
                            result.status = "FLAGGED"
                    elif sec_val.status == ValidationStatus.PASS_WITH_WARNINGS:
                        sec_status = ReviewStatus.PENDING  # PENDING = awaiting human review
                    else:
                        sec_status = ReviewStatus.PENDING

                sections_dict[sec_name] = ReportSection(
                    section_name=sec_name,
                    evidence_keys=[],
                    generated_text=sec_text,
                    validation_notes=sec_notes,
                    review_status=sec_status,
                    generated_at=datetime.now(timezone.utc),
                )
                
        except LLMError as e:
            logger.error("LLM Generation Failed: %s", e)
            result.status = "INCOMPLETE"
            result.error = str(e)
            
            # Create stub sections for failed narratives
            for sec in NARRATIVE_SECTIONS:
                sections_dict[sec] = ReportSection(
                    section_name=sec,
                    evidence_keys=[],
                    generated_text=f"[GENERATION ERROR] {e}",
                    validation_notes=["[ERROR] Generation failed."],
                    review_status=ReviewStatus.FLAGGED,
                    generated_at=datetime.now(timezone.utc),
                )

        # 3. Assemble final list in correct order
        for sec in SECTION_ORDER:
            if sec in sections_dict:
                result.sections.append(sections_dict[sec])
            else:
                logger.warning("Section %s is missing from builder logic.", sec)
                
        return result
