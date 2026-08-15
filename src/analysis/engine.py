"""
src/analysis/engine.py

AnalysisEngine: orchestrates all deterministic analyses and assembles
the complete evidence dict.

This is the single entry point for Stage 3. It:
  1. Calls each analysis module in turn.
  2. Assembles a capabilities record (what the data can and cannot support).
  3. Builds a metadata record (field decisions, version info, timestamp).
  4. Returns the full evidence dict keyed by section name.

The keys in the returned dict correspond 1:1 with evidence/*.json files
and with the section configuration used by the LLM context builder.

No LLM calls are made here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.analysis.alerts import compute_alerts
from src.analysis.case_analysis import compute_case_summary
from src.analysis.case_listing import build_case_listing
from src.analysis.case_table import build_case_table
from src.analysis.demographics import compute_demographics
from src.analysis.outcomes import compute_outcomes
from src.analysis.reactions import compute_reactions
from src.analysis.trends import compute_trends
from src.config.settings import (
    CASE_ID_FIELD,
    COUNTRY_FALLBACK_FIELD,
    COUNTRY_FIELD,
    DATE_FIELD,
    INVALID_AGE_UNIT_CODE,
    REACTION_FIELD,
    RECEIVEDATE_FIELD,
)

logger = logging.getLogger(__name__)

# Analysis version — increment when analysis logic changes
ANALYSIS_VERSION = "0.2.0"


class AnalysisEngine:
    """
    Runs all deterministic analyses on the validated ICSR dataset.

    Usage:
        engine = AnalysisEngine(source_file="path/to/data.xlsx")
        evidence = engine.run(clean_df)
    """

    def __init__(self, source_file: str | Path, top_n_reactions: int = 20) -> None:
        self.source_file = str(source_file)
        self.top_n_reactions = top_n_reactions

    def run(self, df: pd.DataFrame) -> dict:
        """
        Execute all analyses and return the complete evidence dict.

        Args:
            df: Clean normalised DataFrame from DataValidator.validate().

        Returns:
            dict with keys:
                metadata, case_summary, demographics, reactions,
                outcomes, alerts, trends, case_listing, capabilities
        """
        logger.info("Running deterministic analysis engine on %d rows ...", len(df))

        evidence = {}
        
        # Build case table
        case_df = build_case_table(df)

        # --- Core analyses ---
        logger.info("  [1/7] Case summary ...")
        evidence["case_summary"] = compute_case_summary(df, case_df)

        logger.info("  [2/7] Demographics ...")
        evidence["demographics"] = compute_demographics(df, case_df)

        logger.info("  [3/7] Reactions (top %d) ...", self.top_n_reactions)
        evidence["reactions"] = compute_reactions(df, case_df, top_n=self.top_n_reactions)

        logger.info("  [4/7] Outcomes ...")
        evidence["outcomes"] = compute_outcomes(df)

        logger.info("  [5/7] Alerts & seriousness criteria ...")
        evidence["alerts"] = compute_alerts(df, case_df)

        logger.info("  [6/7] Monthly trends ...")
        evidence["trends"] = compute_trends(df)

        logger.info("  [7/7] Case listing (%d cases) ...", df[CASE_ID_FIELD].nunique())
        evidence["case_listing"] = build_case_listing(df)

        # --- Metadata & capabilities ---
        evidence["metadata"] = self._build_metadata(df, evidence["case_summary"])
        evidence["capabilities"] = self._build_limitations(df)

        logger.info("Analysis complete. Evidence dict has %d sections.", len(evidence))
        return evidence

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def _build_metadata(self, df: pd.DataFrame, case_summary: dict) -> dict:
        """
        Build analysis metadata: Canonical data model counts, field mappings, and versioning.
        """
        outcome_entries = len(df["norm_outcomes"].explode().dropna().loc[lambda x: x != ""])
        return {
            "source_file": self.source_file,
            "analysis_version": ANALYSIS_VERSION,
            "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
            "canonical_data_model": {
                "source_rows": len(df),
                "unique_cases": df[CASE_ID_FIELD].nunique(),
                "reaction_records": len(df),
                "unique_reaction_pts": df[REACTION_FIELD].nunique(),
                "outcome_entries": outcome_entries,
            },
            "field_mapping": {
                "case_id_field": CASE_ID_FIELD,
                "reaction_field": REACTION_FIELD,
                "country_field": COUNTRY_FIELD,
                "report_date_field": RECEIVEDATE_FIELD,
                "alert_field": "fulfillexpeditecriteria"
            },
            "reporting_period_start": case_summary["reporting_period_start"],
            "reporting_period_end": case_summary["reporting_period_end"],
        }

    # ------------------------------------------------------------------
    # Limitations
    # ------------------------------------------------------------------

    def _build_limitations(self, df: pd.DataFrame) -> dict:
        """
        Build the explicit capability state object.
        """
        return {
            "expectedness": {
                "available": False,
                "reason": "No product label or CCDS supplied"
            },
            "soc_analysis": {
                "available": False,
                "reason": "No SOC field supplied"
            },
            "history_of_actions": {
                "available": False,
                "reason": "No history-of-actions data supplied"
            },
            "cumulative_analysis": {
                "available": False,
                "reason": "Prior reporting-period data not supplied"
            }
        }
