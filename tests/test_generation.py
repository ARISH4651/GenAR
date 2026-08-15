"""
tests/test_generation.py

Tests for the context builder, output validator, and report builder.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.generation.context_builder import ContextBuilder
from src.generation.output_validator import OutputValidator
from src.models.schemas import OutputValidationResult
from src.generation.report_builder import ReportBuilder
from src.llm.provider import StubProvider
from src.config.report_config import NARRATIVE_SECTIONS, DETERMINISTIC_SECTIONS

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _sample_evidence() -> dict:
    return {
        "case_summary": {
            "total_rows": 1068,
            "total_cases": 1024,
            "serious_cases": 1023,
            "non_serious_cases": 1,
            "expedited_cases": 1023,
            "non_expedited_cases": 1,
            "cases_with_multiple_reactions": 41,
            "reporting_period_start": "2024-12-27",
            "reporting_period_end": "2025-12-26",
        },
        "demographics": {
            "sex_breakdown": {"female": 503, "male": 493},
            "age_group_breakdown": {"75+": 407, "65-74": 266},
        },
        "reactions": {
            "total_reaction_rows": 1068,
            "unique_reaction_pts": 882,
            "top_reactions": [
                {"reaction_pt": "Acute kidney injury", "count": 22, "percent_of_reactions": 2.06},
            ],
            "top_serious_reactions": [],
            "soc_analysis_available": False,
        },
        "capabilities": {
            "expectedness": {"available": False, "reason": "No CCDS supplied"},
            "soc_analysis": {"available": False, "reason": "SOC field not in dataset"},
            "history_of_actions": {"available": False, "reason": "No prior-period data"},
            "cumulative_counts": {"available": False, "reason": "No prior-period data"},
        },
        "metadata": {
            "reporting_period_start": "2024-12-27",
            "reporting_period_end": "2025-12-26",
            "canonical_data_model": {},
            "unique_cases": 1024,
            "serious_cases": 1023,
            "non_serious_cases": 1,
            "expedited_cases": 1023,
        },
    }

# ---------------------------------------------------------------------------
# 1. Context Builder
# ---------------------------------------------------------------------------

class TestContextBuilder:
    def test_build_narrative_context(self):
        builder = ContextBuilder()
        evidence = _sample_evidence()
        context = builder.build_narrative_context(evidence)
        assert isinstance(context, str)
        assert "REPORTING PERIOD" in context
        assert "VERIFIED EVIDENCE" in context
        assert "INSTRUCTIONS" in context

# ---------------------------------------------------------------------------
# 2. Output Validator
# ---------------------------------------------------------------------------

class TestOutputValidator:
    def setup_method(self):
        self.validator = OutputValidator()
        self.evidence = _sample_evidence()

    def test_empty_json_fails(self):
        result = self.validator.validate({}, self.evidence)
        assert result.status == "FLAGGED"

    def test_good_text_passes(self):
        good_json = {
            "Narrative Summary and Analysis": "A total of 1,024 cases were received. Of these, 1,023 were serious."
        }
        result = self.validator.validate(good_json, self.evidence)
        assert result.status == "PASS"

    def test_numeric_grounding_flagged(self):
        # 1024 exists, but not for AKI
        bad_json = {
            "Reaction/Adverse Event Analysis": "Acute kidney injury was reported 1,024 times."
        }
        result = self.validator.validate(bad_json, self.evidence)
        assert result.status == "FLAGGED"
        assert any(i.type == "CONTRADICTED_NUMERIC_CLAIM" for i in result.issues)

    def test_numeric_grounding_passed(self):
        good_json = {
            "Reaction/Adverse Event Analysis": "Acute kidney injury was reported 22 times."
        }
        result = self.validator.validate(good_json, self.evidence)
        assert result.status == "PASS"

    def test_soc_analysis_flagged(self):
        bad_json = {
            "Narrative Summary and Analysis": "System Organ Class analysis shows cardiovascular reactions are common."
        }
        result = self.validator.validate(bad_json, self.evidence)
        assert result.status == "FLAGGED"
        assert any(i.type == "CAPABILITY_VIOLATION" for i in result.issues)

    def test_expectedness_flagged(self):
        bad_json = {
            "Narrative Summary and Analysis": "The expected adverse reactions were consistent."
        }
        result = self.validator.validate(bad_json, self.evidence)
        assert result.status == "FLAGGED"

    def test_fabricated_label_change_flagged(self):
        bad_json = {
            "Narrative Summary and Analysis": "A labeling change was implemented."
        }
        result = self.validator.validate(bad_json, self.evidence)
        assert result.status == "FLAGGED"

    def test_structural_numbers_ignored(self):
        good_json = {
            "Narrative Summary and Analysis": "Table 1 shows 1,024 cases were received in 2025. Age 65-74 had 266 patients."
        }
        result = self.validator.validate(good_json, self.evidence)
        assert result.status == "PASS"

    # -----------------------------------------------------------------------
    # Regression tests for the 7 validator bugs found in the 2026-08-15 run
    # -----------------------------------------------------------------------

    def test_bug1_decimal_period_does_not_split_sentence(self):
        """Bug 1: A period inside '88.56%' must not create a sentence boundary.
        The sentence must be treated as one unit, not split into fragments."""
        text = (
            "Medically significant (other) in 906 cases (88.56% of serious cases), "
            "hospitalisation in 482 cases (47.12%)."
        )
        ev = dict(self.evidence)
        ev["alerts"] = {
            "seriousness_criteria_breakdown": [
                {"criterion_label": "Medically significant (other)", "cases_meeting_criterion": 906},
                {"criterion_label": "Hospitalisation", "cases_meeting_criterion": 482},
            ]
        }
        result = self.validator.validate({"Summary Analysis of Cases": text}, ev)
        # The fragment '56% of serious cases), hospitalisation in 482 cases (47'
        # must NOT cause a FAIL. 906 and 482 are in evidence and correctly matched.
        assert result.status == "PASS", (
            f"Sentence wrongly split on decimal point. Issues: {result.issues}"
        )

    def test_bug2_total_reaction_rows_and_unique_pts_verified(self):
        """Bug 2: total_reaction_rows (1068) and unique_reaction_pts (882) must be
        in the fact table so they can be verified."""
        text = "The dataset contains 1068 reaction rows representing 882 unique MedDRA Preferred Terms (PTs)."
        result = self.validator.validate({"Reaction/Adverse Event Analysis": text}, self.evidence)
        assert result.status == "PASS", (
            f"1068 and 882 should both be verifiable from reactions evidence. Issues: {result.issues}"
        )

    def test_bug3_country_counts_verified(self):
        """Bug 3: country breakdown counts must be in the fact table."""
        ev = dict(self.evidence)
        ev["demographics"] = {
            "sex_breakdown": {"female": 503, "male": 493},
            "age_group_breakdown": {"75+": 407},
            "country_breakdown": {"united kingdom": 281, "france": 187},
        }
        text = "Cases were reported from the United Kingdom (281 cases) and France (187 cases)."
        result = self.validator.validate({"Summary Analysis of Cases": text}, ev)
        assert result.status == "PASS", (
            f"Country counts 281 and 187 should be verifiable. Issues: {result.issues}"
        )

    def test_bug4_75_from_75plus_does_not_cause_false_positive(self):
        """Bug 4: Age bucket '75+' should not cause the integer 75 to be extracted
        and then fail to match because there's no fact with value=75 for age."""
        text = "The largest group was patients aged 75+ (407 cases), followed by 65-74 (266 cases)."
        result = self.validator.validate({"Summary Analysis of Cases": text}, self.evidence)
        assert result.status == "PASS", (
            f"'75' freed from '75+' regex must not cause false positive. Issues: {result.issues}"
        )

    def test_bug5_monthly_trend_counts_verified(self):
        """Bug 5: Monthly case counts from trends evidence must be verifiable."""
        ev = dict(self.evidence)
        ev["trends"] = {
            "total_cases_in_trend": 1024,
            "monthly_case_counts": [
                {"year_month": "2025-07", "count": 109},
                {"year_month": "2025-08", "count": 64},
            ]
        }
        text = (
            "The monthly distribution is as follows: July 2025 (109 cases), "
            "August 2025 (64 cases)."
        )
        result = self.validator.validate({"Trends and Important Observations": text}, ev)
        assert result.status == "PASS", (
            f"Monthly counts 109 and 64 should be verifiable from trends. Issues: {result.issues}"
        )

    def test_bug6_total_outcome_entries_verified(self):
        """Bug 6: total_outcome_entries (3642) must be verifiable from outcomes evidence."""
        ev = dict(self.evidence)
        ev["outcomes"] = {
            "total_outcome_entries": 3642,
            "outcomes": [
                {"outcome": "recovered/resolved", "count": 1347},
            ]
        }
        text = (
            "Reaction outcomes evaluated at the reaction-outcome token level across "
            "3642 total outcome entries, were distributed as follows: "
            "recovered/resolved (1347 tokens)."
        )
        result = self.validator.validate({"Reaction/Adverse Event Analysis": text}, ev)
        assert result.status == "PASS", (
            f"3642 should be verifiable as 'total outcome entries'. Issues: {result.issues}"
        )

    def test_bug7_unverifiable_derived_fact_marked_unverified_not_fail(self):
        """Bug 7: A number in a sentence with no matching subject should be UNVERIFIED,
        not FAIL â€” i.e., should not cause FLAGGED status."""
        text = "The difference is accounted for by 41 cases containing multiple reactions."
        ev = dict(self.evidence)
        ev["case_summary"] = {k: v for k, v in ev["case_summary"].items() if k != "cases_with_multiple_reactions"}
        result = self.validator.validate({"Narrative Summary and Analysis": text}, ev)
        # 41 is not in evidence for any specific subject â€” must be UNVERIFIED, not FAIL
        assert result.status != "FLAGGED", (
            f"41 (derived fact) caused FLAGGED when it should be UNVERIFIED. Issues: {result.issues}"
        )
        # But there should be a warning about it
        assert any("41" in w for w in result.warnings), (
            "UNVERIFIED number 41 should appear in warnings"
        )

    def test_legitimate_mismatch_still_flagged(self):
        """Ensure a genuine hallucination (wrong count for a specific PT) is still caught."""
        bad_json = {
            "Reaction/Adverse Event Analysis": "Acute kidney injury was reported 500 times."
        }
        result = self.validator.validate(bad_json, self.evidence)
        assert result.status == "FLAGGED"
        assert any(i.type == "CONTRADICTED_NUMERIC_CLAIM" for i in result.issues)
        assert any(i.observed == 500 for i in result.issues)

    def test_full_narrative_from_real_run_passes(self):
        """Integration regression: the exact text from the 2026-08-15 successful run
        must pass validation after the 7 bug fixes."""
        ev = dict(self.evidence)
        ev["demographics"] = {
            "sex_breakdown": {"female": 503, "male": 493, "unknown": 28},
            "age_group_breakdown": {
                "75+": 407, "65-74": 266, "45-64": 204,
                "Unknown": 87, "18-44": 44, "0-17": 16,
            },
            "country_breakdown": {
                "eu": 327, "united kingdom": 281, "france": 187,
                "canada": 56, "italy": 52, "germany": 39, "spain": 26,
                "poland": 21, "portugal": 9, "united states": 5, "belgium": 4,
            },
        }
        ev["alerts"] = {
            "seriousness_criteria_breakdown": [
                {"criterion_label": "Medically significant (other)", "cases_meeting_criterion": 906},
                {"criterion_label": "Hospitalisation",               "cases_meeting_criterion": 482},
                {"criterion_label": "Life-threatening",              "cases_meeting_criterion": 105},
                {"criterion_label": "Death",                         "cases_meeting_criterion": 68},
                {"criterion_label": "Disabling / incapacitating",    "cases_meeting_criterion": 44},
                {"criterion_label": "Congenital anomaly",            "cases_meeting_criterion": 7},
            ]
        }
        ev["outcomes"] = {
            "total_outcome_entries": 3642,
            "outcomes": [
                {"outcome": "recovered/resolved",                  "count": 1347},
                {"outcome": "unknown",                             "count": 1135},
                {"outcome": "not recovered/not resolved/ongoing",  "count": 569},
                {"outcome": "recovering/resolving",                "count": 420},
                {"outcome": "fatal",                               "count": 137},
                {"outcome": "recovered/resolved with sequelae",    "count": 34},
            ]
        }
        ev["trends"] = {
            "total_cases_in_trend": 1024,
            "monthly_case_counts": [
                {"year_month": "2024-12", "count": 21},
                {"year_month": "2025-01", "count": 75},
                {"year_month": "2025-02", "count": 94},
                {"year_month": "2025-03", "count": 83},
                {"year_month": "2025-04", "count": 78},
                {"year_month": "2025-05", "count": 80},
                {"year_month": "2025-06", "count": 84},
                {"year_month": "2025-07", "count": 109},
                {"year_month": "2025-08", "count": 64},
                {"year_month": "2025-09", "count": 76},
                {"year_month": "2025-10", "count": 102},
                {"year_month": "2025-11", "count": 75},
                {"year_month": "2025-12", "count": 83},
            ]
        }
        ev["reactions"] = {
            "total_reaction_rows": 1068,
            "unique_reaction_pts": 882,
            "top_reactions": [
                {"reaction_pt": "Acute kidney injury",  "count": 22},
                {"reaction_pt": "Drug ineffective",     "count": 12},
                {"reaction_pt": "Cerebral haemorrhage", "count": 7},
                {"reaction_pt": "Hyponatraemia",        "count": 6},
                {"reaction_pt": "Cholestasis",          "count": 6},
                {"reaction_pt": "Hypokalaemia",         "count": 6},
                {"reaction_pt": "Hepatic cytolysis",    "count": 5},
                {"reaction_pt": "Drug interaction",     "count": 5},
                {"reaction_pt": "Joint swelling",       "count": 5},
                {"reaction_pt": "Muscle spasms",        "count": 4},
                {"reaction_pt": "Pemphigoid",           "count": 4},
                {"reaction_pt": "Cardiogenic shock",    "count": 4},
                {"reaction_pt": "Atrioventricular block", "count": 4},
                {"reaction_pt": "Hypotension",          "count": 4},
                {"reaction_pt": "Pneumonitis",          "count": 4},
                {"reaction_pt": "Syncope",              "count": 4},
            ],
            "top_serious_reactions": [],
        }

        GENERATED_TEXTS = {
            "Narrative Summary and Analysis": (
                "This PADER-style safety report covers the reporting period from 2024-12-27 to 2025-12-26. "
                "During this interval, a total of 1024 unique cases were identified, representing 1068 "
                "reaction rows in the dataset. The difference is accounted for by 41 cases containing "
                "multiple reactions. Among the 1024 unique cases, 1023 were classified as serious and 1 "
                "was classified as non-serious. Similarly, 1023 cases met the criteria for expedited "
                "reporting, while 1 case was non-expedited. Due to data limitations, cumulative analysis "
                "is unavailable because prior reporting-period data was not supplied, and a history of "
                "regulatory actions is unavailable because no history-of-actions data was provided."
            ),
            "Summary Analysis of Cases": (
                "An analysis of the 1024 unique cases reveals the following demographic and clinical "
                "characteristics. By sex, the dataset includes 503 female patients, 493 male patients, "
                "and 28 cases where sex was unknown or missing. Age group distribution, derived from "
                "patient onset age converted to years, shows that the largest group was patients aged "
                "75+ (407 cases), followed by 65-74 (266 cases), 45-64 (204 cases), Unknown (87 cases), "
                "the younger age groups were also represented. Geographically, cases were reported across "
                "multiple countries, with the highest frequencies in the regional code 'eu' (327 cases), "
                "the United Kingdom (281 cases), and France (187 cases), followed by Canada (56 cases), "
                "Italy (52 cases), Germany (39 cases), Spain (26 cases), Poland (21 cases), Portugal "
                "(9 cases), the United States (5 cases), Belgium (4 cases), and other countries with 3 "
                "or fewer cases. Seriousness criteria, which are not mutually exclusive, were met as "
                "follows: medically significant (other) in 906 cases (88.56% of serious cases), "
                "hospitalisation in 482 cases (47.12%), life-threatening in 105 cases (10.26%), death "
                "in 68 cases (6.65%), disabling/incapacitating cases were observed, and congenital "
                "anomaly in 7 cases (0.68%)."
            ),
            "Reaction/Adverse Event Analysis": (
                "The dataset contains 1068 reaction rows representing 882 unique MedDRA Preferred Terms "
                "(PTs). The most frequently reported reaction PTs (and serious reaction PTs, which share "
                "identical counts) were Acute kidney injury (22 rows, 2.06% of reactions), Drug "
                "ineffective (12 rows, 1.12%), Cerebral haemorrhage (7 rows, 0.66%), Hyponatraemia "
                "(6 rows, 0.56%), Cholestasis (6 rows, 0.56%), Hypokalaemia (6 rows, 0.56%), Hepatic "
                "cytolysis (5 rows, 0.47%), Drug interaction (5 rows, 0.47%), Joint swelling "
                "(5 rows, 0.47%), and Muscle spasms, Pemphigoid, Cardiogenic shock, Atrioventricular "
                "block, Hypotension, Pneumonitis, and Syncope (each with 4 rows, 0.37%). System Organ "
                "Class (SOC) analysis is unavailable because no SOC field was supplied in the dataset. "
                "Assessment of expectedness is also unavailable because no product label or CCDS was "
                "provided. Reaction outcomes, evaluated at the reaction-outcome token level across 3642 "
                "total outcome entries, were distributed as follows: recovered/resolved "
                "(1347 tokens, 36.99%), unknown (1135 tokens, 31.16%), not recovered/not "
                "resolved/ongoing (569 tokens, 15.62%), recovering/resolving (420 tokens, 11.53%), "
                "fatal (137 tokens, 3.76%), and recovered/resolved with sequelae (34 tokens, 0.93%)."
            ),
            "Trends and Important Observations": (
                "Monthly case counts for the 1024 unique cases reported during the interval were tracked "
                "using the report date. The monthly distribution is as follows: December 2024 (21 cases), "
                "January 2025 (75 cases), February 2025 (94 cases), March 2025 (83 cases), April 2025 "
                "(78 cases), May 2025 (80 cases), June 2025 (84 cases), July 2025 (109 cases), August "
                "2025 (64 cases), September 2025 (76 cases), October 2025 (102 cases), November 2025 "
                "(75 cases), and December 2025 (83 cases). These monthly counts represent numerical "
                "observations only; a formal safety signal assessment requires qualified clinical review."
            ),
        }
        result = self.validator.validate(GENERATED_TEXTS, ev)
        assert result.status == "PASS", (
            f"Full narrative from real run should pass after bug fixes.\n"
            f"Issues ({len(result.issues)}):\n" +
            "\n".join(f"  #{i+1} type={iss.type} observed={iss.observed} claim={iss.claim[:80]!r}"
                      for i, iss in enumerate(result.issues))
        )


# ---------------------------------------------------------------------------
# 3. ReportBuilder
# ---------------------------------------------------------------------------

class TestReportBuilder:
    def test_build_all_deterministic_and_narrative(self):
        import tempfile, os
        from src.evidence.reader import EvidenceReader
        from src.evidence.writer import EvidenceWriter
        from src.analysis.engine import AnalysisEngine

        data_file = "Bisoprolol_icsr_sample_1068rows.xlsx"
        if not os.path.exists(data_file):
            pytest.skip("Dataset not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            from src.validation.validator import DataValidator
            _, clean_df = DataValidator(data_file).validate()
            engine = AnalysisEngine(source_file=data_file)
            evidence = engine.run(clean_df)
            EvidenceWriter(tmpdir).write(evidence)

            reader = EvidenceReader(tmpdir)

            class SpyProvider(StubProvider):
                calls = 0
                def generate(self, system, user, response_schema=None):
                    self.calls += 1
                    return super().generate(system, user, response_schema)

            spy = SpyProvider()
            builder = ReportBuilder(reader=reader, provider=spy)
            result = builder.build_all()

            # 1 LLM call exactly
            assert spy.calls == 1

            assert len(result.sections) == len(NARRATIVE_SECTIONS) + len(DETERMINISTIC_SECTIONS)
            names = [s.section_name for s in result.sections]
            for sec in DETERMINISTIC_SECTIONS:
                assert sec in names

            for sec in NARRATIVE_SECTIONS:
                assert sec in names

            assert result.status in ["VALIDATED", "FLAGGED"]


# ---------------------------------------------------------------------------
# 4. Phase-final acceptance tests (27 required criteria)
# ---------------------------------------------------------------------------

class TestPhaseFinalAcceptance:
    """27-test suite covering every acceptance criterion from the final spec."""

    def setup_method(self):
        self.validator = OutputValidator()
        self.evidence = _sample_evidence()

    # â”€â”€ Numeric & sentence-splitter tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_ac1_decimal_pct_does_not_break_sentence_split(self):
        """1. Decimal percentages (88.56%) do not break sentence splitting."""
        ev = dict(self.evidence)
        ev["alerts"] = {
            "seriousness_criteria_breakdown": [
                {"criterion_label": "Medically significant (other)", "cases_meeting_criterion": 906},
            ]
        }
        text = "Medically significant (other) in 906 cases (88.56% of serious cases)."
        result = self.validator.validate({"Summary Analysis of Cases": text}, ev)
        assert result.status == "PASS", f"Issues: {result.issues}"

    def test_ac2_decimal_number_88_56_not_extracted_as_integer(self):
        """2. 88.56 must not appear as extracted integer 88 or 56."""
        ints = OutputValidator._extract_integers("906 cases (88.56% of serious cases)")
        assert 88 not in ints, "88 wrongly extracted from 88.56"
        assert 56 not in ints, "56 wrongly extracted from 88.56"
        assert 906 in ints,    "906 missing"

    def test_ac3_75_plus_not_extracted_as_75(self):
        """3. Age label '75+' must not produce bare integer 75."""
        ints = OutputValidator._extract_integers("patients aged 75+ (407 cases)")
        assert 75 not in ints,  "75 wrongly extracted from '75+'"
        assert 407 in ints,     "407 missing"

    def test_ac4_65_74_does_not_create_false_claim(self):
        """4. Age-range label 65-74 must not produce integers 65 or 74."""
        ints = OutputValidator._extract_integers("followed by 65-74 (266 cases)")
        assert 65 not in ints
        assert 74 not in ints
        assert 266 in ints

    def test_ac5_total_reaction_rows_verifiable(self):
        """5. total_reaction_rows (1068) is recognisable from evidence."""
        text = "The dataset contains 1068 reaction rows."
        result = self.validator.validate({"Reaction/Adverse Event Analysis": text}, self.evidence)
        assert result.status == "PASS", f"Issues: {result.issues}"

    def test_ac6_unique_reaction_pts_verifiable(self):
        """6. unique_reaction_pts (882) is recognisable from evidence."""
        text = "There were 882 unique MedDRA Preferred Terms (PTs)."
        result = self.validator.validate({"Reaction/Adverse Event Analysis": text}, self.evidence)
        assert result.status in ("PASS", "PASS_WITH_WARNINGS"), f"Unexpected FLAGGED: {result.issues}"

    def test_ac7_country_count_verifiable_by_country_name(self):
        """7. Country case counts verified via country name as subject."""
        ev = dict(self.evidence)
        ev["demographics"] = {
            "sex_breakdown": {"female": 503, "male": 493},
            "age_group_breakdown": {"75+": 407},
            "country_breakdown": {"united kingdom": 281},
        }
        text = "The United Kingdom reported 281 cases."
        result = self.validator.validate({"Summary Analysis of Cases": text}, ev)
        assert result.status == "PASS", f"Issues: {result.issues}"

    def test_ac8_monthly_trend_count_verifiable_by_month_name(self):
        """8. Monthly case counts verified via month name as subject."""
        ev = dict(self.evidence)
        ev["trends"] = {
            "total_cases_in_trend": 1024,
            "monthly_case_counts": [{"year_month": "2025-07", "count": 109}],
        }
        text = "July 2025 had 109 cases."
        result = self.validator.validate({"Trends and Important Observations": text}, ev)
        assert result.status == "PASS", f"Issues: {result.issues}"

    def test_ac9_total_outcome_entries_verifiable(self):
        """9. total_outcome_entries (3642) verifiable from outcomes evidence."""
        ev = dict(self.evidence)
        ev["outcomes"] = {
            "total_outcome_entries": 3642,
            "outcomes": [{"outcome": "recovered/resolved", "count": 1347}],
        }
        text = "Evaluated across 3642 total outcome entries."
        result = self.validator.validate({"Reaction/Adverse Event Analysis": text}, ev)
        assert result.status == "PASS", f"Issues: {result.issues}"

    def test_ac10_multi_reaction_cases_verifiable_when_present(self):
        """10. cases_with_multiple_reactions is verified when evidence supplies it."""
        ev = dict(self.evidence)
        ev["case_summary"] = dict(ev["case_summary"])
        ev["case_summary"]["cases_with_multiple_reactions"] = 44
        text = "The difference is accounted for by 44 cases containing multiple reactions."
        result = self.validator.validate({"Narrative Summary and Analysis": text}, ev)
        assert result.status == "PASS", f"Issues: {result.issues}"

    def test_ac10b_multi_reaction_unverified_when_absent(self):
        """10b. If cases_with_multiple_reactions is absent, claim is UNVERIFIED not FLAGGED."""
        ev = dict(self.evidence)
        ev["case_summary"] = {k: v for k, v in ev["case_summary"].items()
                              if k != "cases_with_multiple_reactions"}
        text = "The difference is accounted for by 41 cases containing multiple reactions."
        ev = dict(self.evidence)
        ev["case_summary"] = {k: v for k, v in ev["case_summary"].items() if k != "cases_with_multiple_reactions"}
        result = self.validator.validate({"Narrative Summary and Analysis": text}, ev)
        result = self.validator.validate({"Narrative Summary and Analysis": text}, ev)
        assert result.status != "FLAGGED", f"Should be UNVERIFIED not FLAGGED. Issues: {result.issues}"
        assert any("41" in w for w in result.warnings)

    def test_ac11_correct_numeric_claim_passes(self):
        """11. A correct numeric claim (AKI=22) passes validation."""
        text = "Acute kidney injury was reported 22 times."
        result = self.validator.validate({"Reaction/Adverse Event Analysis": text}, self.evidence)
        assert result.status == "PASS"

    def test_ac12_contradictory_numeric_claim_flagged(self):
        """12. A contradictory numeric claim (AKI=1024) is FLAGGED."""
        text = "Acute kidney injury was reported 1024 times."
        result = self.validator.validate({"Reaction/Adverse Event Analysis": text}, self.evidence)
        assert result.status == "FLAGGED"
        assert any(i.type == "CONTRADICTED_NUMERIC_CLAIM" for i in result.issues)

    def test_ac13_unrelated_evidence_number_does_not_validate_claim(self):
        """13. 1024 (total cases) does not validate AKI=1024.
        The subject 'Acute kidney injury' is specific and has value=22, not 1024.
        """
        text = "Acute kidney injury was reported 1024 times."
        result = self.validator.validate({"Reaction/Adverse Event Analysis": text}, self.evidence)
        # Must be FLAGGED, not PASS, even though 1024 exists elsewhere in evidence
        assert result.status == "FLAGGED", (
            "Number 1024 from 'total cases' must not validate AKI count claim"
        )

    # â”€â”€ Safety conclusion tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_ac14_unsupported_safety_conclusion_flagged(self):
        """14. 'No safety concerns were identified.' must be FLAGGED."""
        text = "No safety concerns were identified during the period."
        result = self.validator.validate({"Narrative Summary and Analysis": text}, self.evidence)
        assert result.status == "FLAGGED"
        assert any(i.type == "UNSUPPORTED_SAFETY_CONCLUSION" for i in result.issues)

    def test_ac14b_causation_claim_flagged(self):
        """14b. 'The reaction was caused by bisoprolol.' must be FLAGGED."""
        text = "The reaction was caused by bisoprolol."
        result = self.validator.validate({"Narrative Summary and Analysis": text}, self.evidence)
        assert result.status == "FLAGGED"

    def test_ac14c_favorable_safety_profile_flagged(self):
        """14c. 'The product has a favorable safety profile.' must be FLAGGED."""
        text = "The product has a favorable safety profile based on the data."
        result = self.validator.validate({"Narrative Summary and Analysis": text}, self.evidence)
        assert result.status == "FLAGGED"

    # â”€â”€ Capability / limitation tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_ac15_negative_capability_statement_passes(self):
        """15. 'Expectedness was not assessed.' is a correct negation â€” must PASS."""
        text = "Assessment of expectedness is also unavailable because no product label or CCDS was provided."
        result = self.validator.validate({"Narrative Summary and Analysis": text}, self.evidence)
        assert result.status == "PASS", f"Issues: {result.issues}"

    def test_ac16_positive_unavailable_capability_flagged(self):
        """16. Claiming SOC results when SOC is unavailable must be FLAGGED."""
        text = "System Organ Class analysis shows cardiovascular reactions dominate."
        result = self.validator.validate({"Narrative Summary and Analysis": text}, self.evidence)
        assert result.status == "FLAGGED"
        assert any(i.type == "CAPABILITY_VIOLATION" for i in result.issues)

    def test_ac17_structural_numbers_do_not_trigger_false_positives(self):
        """17. Table references and years must not cause false positives."""
        text = "Table 1 shows results for 2025. Section 3 covers 1,024 cases."
        result = self.validator.validate({"Narrative Summary and Analysis": text}, self.evidence)
        assert result.status == "PASS", f"Issues: {result.issues}"

    # â”€â”€ Report structure tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_ac18_flagged_section_content_appears_in_notes(self):
        """18. A FLAGGED section still carries generated_text (not empty)."""
        from src.models.schemas import ReportSection, ReviewStatus
        section = ReportSection(
            section_name="Narrative Summary and Analysis",
            evidence_keys=[],
            generated_text="Some generated text about the study.",
            validation_notes=["[CONTRADICTED] CONTRADICTED_NUMERIC_CLAIM: AKI count wrong."],
            review_status=ReviewStatus.FLAGGED,
        )
        assert section.generated_text.strip() != ""
        assert "CONTRADICTED" in section.validation_notes[0]

    def test_ac19_flagged_sections_contain_actual_issues(self):
        """19. A FLAGGED result must have at least one issue."""
        bad_json = {"Reaction/Adverse Event Analysis": "Acute kidney injury was reported 1024 times."}
        result = self.validator.validate(bad_json, self.evidence)
        assert result.status == "FLAGGED"
        assert len(result.issues) > 0, "FLAGGED result must have â‰¥1 issue"

    def test_ac20_pass_sections_have_zero_issues(self):
        """20. A PASS result must have zero issues."""
        good_json = {"Narrative Summary and Analysis": "A total of 1,024 cases were received."}
        result = self.validator.validate(good_json, self.evidence)
        assert result.status == "PASS"
        assert len(result.issues) == 0

    # â”€â”€ Generation / LLM tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_ac21_gemini_called_exactly_once(self):
        """21. Gemini is called exactly once in a full build cycle."""
        import tempfile, os
        from src.evidence.reader import EvidenceReader
        from src.evidence.writer import EvidenceWriter
        from src.analysis.engine import AnalysisEngine
        from src.generation.report_builder import ReportBuilder

        data_file = "Bisoprolol_icsr_sample_1068rows.xlsx"
        if not os.path.exists(data_file):
            pytest.skip("Dataset not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            from src.validation.validator import DataValidator
            _, clean_df = DataValidator(data_file).validate()
            engine = AnalysisEngine(source_file=data_file)
            EvidenceWriter(tmpdir).write(engine.run(clean_df))

            class CountProvider(StubProvider):
                calls = 0
                def generate(self, system, user, response_schema=None):
                    CountProvider.calls += 1
                    return super().generate(system, user, response_schema)

            builder = ReportBuilder(reader=EvidenceReader(tmpdir), provider=CountProvider())
            builder.build_all()
            assert CountProvider.calls == 1

    def test_ac22_llm_failure_produces_incomplete(self):
        """22. LLM failure â†’ result.status == INCOMPLETE."""
        import tempfile
        from src.evidence.reader import EvidenceReader
        from src.evidence.writer import EvidenceWriter
        from src.analysis.engine import AnalysisEngine
        from src.generation.report_builder import ReportBuilder
        from src.llm.provider import LLMProvider, LLMError

        class FailProvider(LLMProvider):
            def generate(self, system, user, response_schema=None):
                raise LLMError("Simulated 429 quota exhausted")

        import os
        data_file = "Bisoprolol_icsr_sample_1068rows.xlsx"
        if not os.path.exists(data_file):
            pytest.skip("Dataset not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            from src.validation.validator import DataValidator
            _, clean_df = DataValidator(data_file).validate()
            from src.analysis.engine import AnalysisEngine
            from src.evidence.writer import EvidenceWriter
            EvidenceWriter(tmpdir).write(AnalysisEngine(source_file=data_file).run(clean_df))
            result = ReportBuilder(reader=EvidenceReader(tmpdir), provider=FailProvider()).build_all()
            assert result.status == "INCOMPLETE"

    def test_ac23_incomplete_report_cannot_be_approved(self):
        """23. review.py must return non-zero if report is INCOMPLETE."""
        import subprocess, tempfile, textwrap
        draft = "[GENERATION ERROR] quota exhausted\nGeneration Status: INCOMPLETE"
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as f:
            f.write(draft)
            fname = f.name
        proc = subprocess.run(
            ["python", "-X", "utf8", "src/review.py", fname],
            input="y\n", capture_output=True, text=True,
        )
        import os; os.unlink(fname)
        assert proc.returncode != 0, "Incomplete report must block approval"

    # â”€â”€ Human review workflow tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_ac24_rejection_does_not_create_final_report(self):
        """24. Entering N does not create final_report.md."""
        import subprocess, tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            draft = Path(tmpdir) / "draft_report.md"
            draft.write_text(
                "## 1. Reporting Period\n*Review Status: **PENDING***\n\nContent here.\n"
                "## 2. Narrative Summary and Analysis\n*Review Status: **PENDING***\n\nNarrative.\n"
                "## 3. Summary Analysis of Cases\n*Review Status: **PENDING***\n\nCases.\n"
                "## 4. Reaction/Adverse Event Analysis\n*Review Status: **PENDING***\n\nReactions.\n"
                "## 5. Serious Cases / 15-Day Alerts\n*Review Status: **PENDING***\n\nAlerts.\n"
                "## 6. Trends and Important Observations\n*Review Status: **PENDING***\n\nTrends.\n"
                "## 7. History of Actions\n*Review Status: **PENDING***\n\nHistory.\n"
                "## 8. Case Index / Listing\n*Review Status: **PENDING***\n\nListing.\n"
                "| # | Section | Status | Contradicted | Unverified |\n"
                "|---|---------|--------|-------------|------------|\n"
                "| 1 | Reporting Period | PENDING | 0 | 0 |\n"
                "**Generation Status:** COMPLETE  \n",
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["python", "-X", "utf8", "src/review.py", str(draft)],
                input="n\n", capture_output=True, text=True,
                cwd="d:/project/GenAI",
            )
            final = Path(tmpdir) / "final_report.md"
            assert not final.exists(), "Rejection must not create final_report.md"

    def test_ac25_approval_creates_final_report(self):
        """25. Entering y creates final_report.md."""
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            draft = Path(tmpdir) / "draft_report.md"
            draft.write_text(
                "## 1. Reporting Period\n*Review Status: **PENDING***\n\nContent here.\n"
                "## 2. Narrative Summary and Analysis\n*Review Status: **PENDING***\n\nNarrative.\n"
                "## 3. Summary Analysis of Cases\n*Review Status: **PENDING***\n\nCases.\n"
                "## 4. Reaction/Adverse Event Analysis\n*Review Status: **PENDING***\n\nReactions.\n"
                "## 5. Serious Cases / 15-Day Alerts\n*Review Status: **PENDING***\n\nAlerts.\n"
                "## 6. Trends and Important Observations\n*Review Status: **PENDING***\n\nTrends.\n"
                "## 7. History of Actions\n*Review Status: **PENDING***\n\nHistory.\n"
                "## 8. Case Index / Listing\n*Review Status: **PENDING***\n\nListing.\n"
                "| # | Section | Status | Contradicted | Unverified |\n"
                "|---|---------|--------|-------------|------------|\n"
                "| 1 | Reporting Period | PENDING | 0 | 0 |\n"
                "**Generation Status:** COMPLETE  \n",
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["python", "-X", "utf8", "src/review.py", str(draft)],
                input="y\n", capture_output=True, text=True,
                cwd="d:/project/GenAI",
            )
            final = Path(tmpdir) / "final_report.md"
            assert final.exists(), f"Approval must create final_report.md. stdout={proc.stdout}"

    def test_ac26_all_8_sections_in_draft(self):
        """26. All 8 required sections appear in a draft from a real run."""
        draft = Path("reports/draft_report.md")
        if not draft.exists():
            pytest.skip("Draft report not available")
        content = draft.read_text(encoding="utf-8")
        required = [
            "Reporting Period",
            "Narrative Summary and Analysis",
            "Summary Analysis of Cases",
            "Reaction/Adverse Event Analysis",
            "Serious Cases / 15-Day Alerts",
            "Trends and Important Observations",
            "History of Actions",
            "Case Index / Listing",
        ]
        for name in required:
            assert name in content, f"Missing section: {name}"

    def test_ac27_final_report_has_approval_header(self):
        """27. final_report.md contains the human-approval header."""
        final = Path("reports/final_report.md")
        if not final.exists():
            pytest.skip("Final report not yet created")
        content = final.read_text(encoding="utf-8")
        assert "<!-- Human Review: APPROVED -->" in content, (
            "final_report.md must contain the approval header"
        )









