"""
src/generation/output_validator.py

OutputValidator: validates LLM-generated narrative text against structured evidence.

Design:
  Every numeric claim in the generated text is evaluated as one of:

    VERIFIED     â€“ evidence explicitly provides the same subjectâ†’value pair
    UNVERIFIED   â€“ no evidence subject matches; the claim cannot be confirmed or denied
    CONTRADICTED â€“ a specific evidence subject IS matched and the value DIFFERS

  Section status:
    PASS              â€“ all claims VERIFIED, no capability violations
    PASS_WITH_WARNINGS â€“ at least one UNVERIFIED claim; no contradictions
    FLAGGED           â€“ at least one CONTRADICTED claim or capability violation

  Overall result status mirrors the worst per-section status.

  "FLAGGED with 0 issues" is impossible: every FLAGGED result contains â‰¥1 issue.

Sentence splitting:
  Splits ONLY on . ? ! that are followed by whitespace + uppercase letter
  (or end-of-string).  This prevents splitting decimal percentages like 88.56%.

Numeric extraction:
  Removes years (20xx), age-range labels (18-44, 75+), table refs,
  and full decimal numbers (36.99) before extracting integers.
  Numbers < 10 or > 999,999 are ignored as structurally implausible.
"""

from __future__ import annotations

import datetime
import logging
import re

from src.models.schemas import (
    ClaimState,
    OutputValidationIssue,
    OutputValidationResult,
    SectionValidationResult,
    ValidationStatus,
)

logger = logging.getLogger(__name__)

# Generic subjects that appear in many sentences and cannot pin a single fact
_GENERIC_SUBJECTS = frozenset({
    "cases", "unique cases", "total cases", "received",
})

# Phrases that indicate the LLM correctly stated a capability is unavailable
_NEGATIONS = (
    "not available", "unavailable", "not assessed", "not supplied",
    "no soc field", "no product label", "no ccds", "could not be determined",
    "was not", "is not", "were not", "no history", "not provided",
    "cannot be", "no prior", "assessment is", "analysis is",
)

# Unsupported safety-conclusion phrases that must not appear as positive claims
_SAFETY_CONCLUSION_TRIGGERS = (
    "no safety concerns",
    "favorable safety profile",
    "confirm an emerging safety signal",
    "the product is safe",
    "was caused by",
    "caused by bisoprolol",
    "the treatment was effective",
    "demonstrates safety",
    "no new safety signal",
    "no signals were identified",
)


class OutputValidator:
    """Validates LLM-generated narrative JSON against structured evidence facts."""

    # -------------------------------------------------------------------------
    # Public interface
    # -------------------------------------------------------------------------

    def validate(
        self,
        generated_json: dict[str, str],
        evidence: dict[str, dict],
    ) -> OutputValidationResult:
        result = OutputValidationResult()

        if not generated_json:
            result.status = ValidationStatus.FLAGGED
            result.issues.append(OutputValidationIssue(
                type="EMPTY_RESPONSE",
                state=ClaimState.CONTRADICTED,
                claim="Generated JSON is empty â€” no narrative text was returned.",
                reason="LLM returned no content.",
            ))
            return result

        facts = self._extract_facts(evidence)

        worst = ValidationStatus.PASS
        for section_name, text in generated_json.items():
            sec_result = self._validate_section(section_name, str(text), facts, evidence)
            result.per_section[section_name] = sec_result
            result.checked_claims += sec_result.checked_claims
            result.issues.extend(sec_result.issues)
            result.warnings.extend(sec_result.warnings)
            if sec_result.status == ValidationStatus.FLAGGED:
                worst = ValidationStatus.FLAGGED
            elif sec_result.status == ValidationStatus.PASS_WITH_WARNINGS and worst == ValidationStatus.PASS:
                worst = ValidationStatus.PASS_WITH_WARNINGS

        result.status = worst
        return result

    # -------------------------------------------------------------------------
    # Per-section validation
    # -------------------------------------------------------------------------

    def _validate_section(
        self,
        section_name: str,
        text: str,
        facts: list[dict],
        evidence: dict,
    ) -> SectionValidationResult:
        sec = SectionValidationResult(section_name=section_name)

        if not text.strip():
            sec.status = ValidationStatus.FLAGGED
            sec.issues.append(OutputValidationIssue(
                type="EMPTY_SECTION",
                state=ClaimState.CONTRADICTED,
                claim=f"Section '{section_name}' is empty.",
                reason="LLM returned no content for this section.",
            ))
            return sec

        self._check_capabilities(sec, text, evidence, section_name)
        self._check_safety_conclusions(sec, text, section_name)
        self._check_numbers(sec, text, facts, section_name)

        # Derive section status
        if sec.issues:
            # issues = CONTRADICTED claims or capability violations â†’ always FLAGGED
            sec.status = ValidationStatus.FLAGGED
        elif sec.warnings:
            sec.status = ValidationStatus.PASS_WITH_WARNINGS
        else:
            sec.status = ValidationStatus.PASS

        return sec

    # -------------------------------------------------------------------------
    # Fact extraction  (subject â†’ value)
    # -------------------------------------------------------------------------

    def _extract_facts(self, evidence: dict) -> list[dict]:
        """
        Build a flat list of {subject, value} pairs from all evidence sections.

        Each fact maps one or more natural-language subjects to a numeric value.
        Subjects are stored in lower-case for case-insensitive matching.
        """
        facts: list[dict] = []

        def add(subjects: list[str], value) -> None:
            if value is None:
                return
            for s in subjects:
                if s:
                    facts.append({"subject": s.strip().lower(), "value": value})

        # â”€â”€ Case summary â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        cs = evidence.get("case_summary", {})
        meta = evidence.get("metadata", {})
        cdm = meta.get("canonical_data_model", {})

        total_cases = cs.get("total_cases") or meta.get("unique_cases") or cdm.get("unique_cases")
        total_rows  = cs.get("total_rows")  or cdm.get("source_rows")
        serious     = cs.get("serious_cases")
        non_serious = cs.get("non_serious_cases")
        expedited   = cs.get("expedited_cases")
        multi_rxn   = cs.get("cases_with_multiple_reactions")

        add(["cases", "unique cases", "total cases", "received", "identified"], total_cases)
        add(["serious"], serious)
        add(["non-serious", "non serious"], non_serious)
        add(["expedited", "15-day", "alert"], expedited)
        add(["reaction rows", "reaction row"], total_rows)
        add(["cases containing multiple reactions", "cases with multiple reactions",
             "multi-reaction cases"], multi_rxn)

        # â”€â”€ Demographics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        demo = evidence.get("demographics", {})
        for sex, count in demo.get("sex_breakdown", {}).items():
            add([sex, f"{sex} patients", f"patients were {sex}"], count)

        for age_grp, count in demo.get("age_group_breakdown", {}).items():
            add([age_grp, f"aged {age_grp}", f"age {age_grp}",
                 f"patients aged {age_grp}"], count)

        for country, count in demo.get("country_breakdown", {}).items():
            add([country], count)

        # â”€â”€ Reactions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        rxns = evidence.get("reactions", {})
        rxn_rows   = rxns.get("total_reaction_rows") or total_rows
        unique_pts = rxns.get("unique_reaction_pts")

        add(["reaction rows", "reaction row"], rxn_rows)
        add([
            "unique meddra preferred terms (pts)",
            "unique meddra preferred terms",
            "unique preferred terms",
            "unique pts",
            "unique reaction pts",
        ], unique_pts)

        for rxn in rxns.get("top_reactions", []):
            add([rxn["reaction_pt"].lower()], rxn["count"])
        for rxn in rxns.get("top_serious_reactions", []):
            add([rxn["reaction_pt"].lower()], rxn["count"])

        # â”€â”€ Outcomes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        outs = evidence.get("outcomes", {})
        total_outcome_entries = outs.get("total_outcome_entries")
        add(["outcome entries", "total outcome entries", "outcome tokens",
             "total outcome tokens"], total_outcome_entries)

        for out in outs.get("outcomes", []):
            name = out["outcome"].lower()
            add([name, f"{name} tokens"], out["count"])

        # â”€â”€ Alerts / seriousness criteria â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        alerts = evidence.get("alerts", {})
        for crit in alerts.get("seriousness_criteria_breakdown", []):
            label = crit.get("criterion_label", "").lower()
            count = crit.get("cases_meeting_criterion")
            if label and count is not None:
                add([label, f"{label} cases"], count)

        # â”€â”€ Monthly trends â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        trends = evidence.get("trends", {})
        add(["cases in trend", "total cases in trend"], trends.get("total_cases_in_trend"))
        for entry in trends.get("monthly_case_counts", []):
            ym    = entry.get("year_month", "")
            count = entry.get("count")
            if ym and count is not None:
                try:
                    y, m = int(ym[:4]), int(ym[5:7])
                    month_label = datetime.date(y, m, 1).strftime("%B %Y").lower()
                    add([month_label, ym], count)
                except (ValueError, IndexError):
                    add([ym], count)

        return facts

    # -------------------------------------------------------------------------
    # Capability checks
    # -------------------------------------------------------------------------

    def _check_capabilities(
        self,
        sec: SectionValidationResult,
        text: str,
        evidence: dict,
        section_name: str,
    ) -> None:
        text_lower = text.lower()
        caps = evidence.get("capabilities", {})

        def negated(phrase: str) -> bool:
            """Return True if the phrase appears only in a negated context."""
            idx = text_lower.find(phrase)
            if idx == -1:
                return False
            window = text_lower[max(0, idx - 60): idx + len(phrase) + 60]
            return any(neg in window for neg in _NEGATIONS)

        # Expectedness
        if not caps.get("expectedness", {}).get("available", True):
            positive_expectedness = ["the reaction was expected", "the reaction was unexpected",
                                     "listed reaction", "unlisted reaction", "expected adverse reactions", "expected reactions were consistent", "the expected adverse reactions" ]
            for phrase in positive_expectedness:
                if phrase in text_lower and not negated(phrase):
                    sec.issues.append(OutputValidationIssue(
                        type="CAPABILITY_VIOLATION",
                        state=ClaimState.CONTRADICTED,
                        claim=f"[{section_name}] Discussed expectedness but capability is unavailable.",
                        sentence=phrase,
                        reason="No product label or CCDS was supplied; expectedness cannot be assessed.",
                    ))

        # SOC analysis
        if not caps.get("soc_analysis", {}).get("available", True):
            soc_triggers = ["system organ class", " soc ", "most common soc"]
            for trigger in soc_triggers:
                if trigger in text_lower and not negated(trigger):
                    sec.issues.append(OutputValidationIssue(
                        type="CAPABILITY_VIOLATION",
                        state=ClaimState.CONTRADICTED,
                        claim=f"[{section_name}] Asserted SOC analysis results but SOC data is unavailable.",
                        sentence=trigger,
                        reason="No SOC field was supplied in the dataset.",
                    ))

        # History of actions
        if not caps.get("history_of_actions", {}).get("available", True):
            history_triggers = [
                "label update", "labeling change", "dear healthcare professional",
                "safety study", "regulatory action", "rems", "risk management",
                "a label change was", "a labeling change was",
            ]
            for trigger in history_triggers:
                if trigger in text_lower and not negated(trigger):
                    sec.issues.append(OutputValidationIssue(
                        type="CAPABILITY_VIOLATION",
                        state=ClaimState.CONTRADICTED,
                        claim=f"[{section_name}] Discussed regulatory actions but history-of-actions is unavailable.",
                        sentence=trigger,
                        reason="No history-of-actions data was supplied.",
                    ))

    # -------------------------------------------------------------------------
    # Safety-conclusion checks
    # -------------------------------------------------------------------------

    def _check_safety_conclusions(
        self,
        sec: SectionValidationResult,
        text: str,
        section_name: str,
    ) -> None:
        text_lower = text.lower()
        for phrase in _SAFETY_CONCLUSION_TRIGGERS:
            if phrase in text_lower:
                # Check for a negation within 80 chars of the phrase
                idx = text_lower.find(phrase)
                window = text_lower[max(0, idx - 40): idx + len(phrase) + 40]
                if not any(neg in window for neg in _NEGATIONS):
                    sec.issues.append(OutputValidationIssue(
                        type="UNSUPPORTED_SAFETY_CONCLUSION",
                        state=ClaimState.CONTRADICTED,
                        claim=(
                            f"[{section_name}] Generated text contains an unsupported safety conclusion."
                        ),
                        sentence=phrase,
                        reason=(
                            "This statement goes beyond observable data. "
                            "Signal assessment requires qualified clinical review."
                        ),
                    ))

    # -------------------------------------------------------------------------
    # Numeric claim validation
    # -------------------------------------------------------------------------

    def _check_numbers(
        self,
        sec: SectionValidationResult,
        text: str,
        facts: list[dict],
        section_name: str,
    ) -> None:
        sentences = self._split_sentences(text)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            numbers = self._extract_integers(sentence)
            if not numbers:
                continue

            sent_lower = sentence.lower()

            # Facts whose subjects appear verbatim in this sentence
            matched = [f for f in facts if f["subject"] and f["subject"] in sent_lower]

            specific = [f for f in matched if f["subject"] not in _GENERIC_SUBJECTS]
            generic  = [f for f in matched if f["subject"] in _GENERIC_SUBJECTS]

            for num in sorted(numbers):
                sec.checked_claims += 1
                all_vals = {f["value"] for f in matched}

                # â”€â”€ VERIFIED â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                if num in all_vals:
                    continue   # at least one fact supports this number

                # â”€â”€ No subject context â†’ UNVERIFIED â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                if not matched:
                    sec.warnings.append(
                        f"[UNVERIFIED] [{section_name}] "
                        f"Number {num} has no matching evidence subject â€” cannot verify. "
                        f"Sentence: {sentence[:120]!r}"
                    )
                    continue

                # â”€â”€ Specific subjects matched but not this value â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                if specific:
                    spec_vals = {f["value"] for f in specific}
                    if len(spec_vals) == 1:
                        # Exactly one specific fact â€” clear CONTRADICTED
                        expected_val = next(iter(spec_vals))
                        sec.issues.append(OutputValidationIssue(
                            type="CONTRADICTED_NUMERIC_CLAIM",
                            state=ClaimState.CONTRADICTED,
                            claim=(
                                f"[{section_name}] Number {num} contradicts evidence. "
                                f"Evidence says {[f['subject'] for f in specific][0]} = {expected_val}."
                            ),
                            sentence=sentence,
                            expected=expected_val,
                            observed=num,
                            reason=(
                                f"The generated text states {num} for "
                                f"'{[f['subject'] for f in specific][0]}', "
                                f"but evidence records {expected_val}."
                            ),
                        ))
                    else:
                        # Multiple specific subjects with different values â†’ UNVERIFIED
                        sec.warnings.append(
                            f"[UNVERIFIED] [{section_name}] "
                            f"Number {num} could not be uniquely attributed. "
                            f"Subjects: {[f['subject'] for f in specific]}, "
                            f"Values: {sorted(spec_vals)}. "
                            f"Sentence: {sentence[:120]!r}"
                        )
                else:
                    # Only generic subjects (e.g. 'cases') matched â†’
                    # sentence likely lists multiple values; UNVERIFIED
                    sec.warnings.append(
                        f"[UNVERIFIED] [{section_name}] "
                        f"Number {num} matched only generic subjects {[f['subject'] for f in generic]}. "
                        f"Sentence: {sentence[:120]!r}"
                    )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """
        Split text into sentences without splitting inside decimal numbers.

        A boundary is recognised only when . ! ? is followed by whitespace
        and an uppercase letter, or at end-of-string.  This keeps "88.56%"
        in one sentence.
        """
        text = text.replace("\r\n", " ").replace("\n", " ")
        parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])|(?<=[.!?])\s*$', text)
        return [p.strip() for p in parts if p.strip()]

    @staticmethod
    def _extract_integers(text: str) -> set[int]:
        """
        Extract standalone integers, filtering structural noise.

        Removed before extraction:
        - 4-digit years (20xx)
        - Age-range labels (18-44, 0-17) and age+ labels (75+)
        - Table/Figure/Section references
        - "Top N" references
        - Full decimal numbers (36.99) to avoid extracting integer parts
        """
        # Strip years
        text = re.sub(r"\b20\d{2}\b", "", text)
        # Strip age-range labels e.g. 18-44, 0-17, 65-74
        text = re.sub(r"\b\d{1,3}[-â€“]\d{1,3}\b", "", text)
        # Strip age-plus labels e.g. 75+
        text = re.sub(r"\b\d{1,3}\+", "", text)
        # Strip table/figure/section refs
        text = re.sub(r"(?i)\b(table|figure|section)\s*\d+\b", "", text)
        text = re.sub(r"(?i)\btop\s*\d+\b", "", text)
        # Strip full decimal numbers so 36.99 doesn't contribute 36
        text = re.sub(r"\b\d+\.\d+\b", "", text)
        # Normalise thousands separators: 1,024 â†’ 1024
        text = re.sub(r"(\d),(\d{3})", r"\1\2", text)

        return {
            int(m) for m in re.findall(r"\b(\d+)\b", text)
            if 10 <= int(m) <= 999_999
        }

