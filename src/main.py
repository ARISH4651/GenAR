"""
src/main.py â€” GenAR Pipeline CLI

Full pipeline entry point:
  1. Load configuration and API key
  2. Validate ICSR dataset
  3. Run deterministic analysis
  4. Write evidence store (evidence/*.json)
  5. Generate report sections (LLM)
  6. Validate each section
  7. Assemble final Markdown report

Usage:
    python -X utf8 src/main.py --input Bisoprolol_icsr_sample_1068rows.xlsx
    python -X utf8 src/main.py --input data.xlsx --skip-llm   # test without API key
    python -X utf8 src/main.py --input data.xlsx --output reports/my_report.md

Environment:
    GEMINI_API_KEY  (required unless --skip-llm)
    GEMINI_MODEL    (optional, default: gemini-2.5-flash)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Load .env before anything else
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optional â€” use env vars directly if not installed

# Ensure src/ is on path when running as script
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("genar")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="genar",
        description="GenAR â€” AI-assisted PADER report generator",
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to ICSR dataset (.xlsx or .csv)",
    )
    parser.add_argument(
        "--evidence-dir", "-e",
        default="evidence",
        help="Directory to write/read evidence JSON files (default: evidence/)",
    )
    parser.add_argument(
        "--output", "-o",
        default="reports/draft_report.md",
        help="Output path for the draft Markdown report",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        default=False,
        help="Skip LLM calls and use stub text (for testing without API key)",
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        default=False,
        help="Skip data validation and analysis â€” use existing evidence store",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Gemini model name (default: gemini-2.5-flash or GEMINI_MODEL env var)",
    )
    parser.add_argument(
        "--top-n-reactions",
        type=int,
        default=20,
        help="Number of top reactions to include in analysis (default: 20)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start_time = time.time()

    _banner()

    # ------------------------------------------------------------------ #
    # Step 1: Evidence store â€” validate + analyse (or reuse existing)
    # ------------------------------------------------------------------ #
    if args.skip_analysis:
        logger.info("--skip-analysis: reusing existing evidence store in %s/", args.evidence_dir)
    else:
        logger.info("Step 1/4: Validating dataset: %s", args.input)
        from src.validation.validator import DataValidator
        validator = DataValidator(args.input)
        try:
            result, clean_df = validator.validate()
        except FileNotFoundError as e:
            logger.error("%s", e)
            return 1

        if not result.is_valid:
            logger.error("Validation FAILED â€” cannot proceed.\n%s", result.summary())
            return 1

        logger.info(
            "  Validated: %d rows, %d unique cases, %d warnings",
            result.metadata.total_rows,
            result.metadata.unique_cases,
            len(result.warnings),
        )

        logger.info("Step 2/4: Running deterministic analysis ...")
        from src.analysis.engine import AnalysisEngine
        engine = AnalysisEngine(
            source_file=args.input,
            top_n_reactions=args.top_n_reactions,
        )
        evidence = engine.run(clean_df)

        logger.info("Step 3/4: Writing evidence store to %s/ ...", args.evidence_dir)
        from src.evidence.writer import EvidenceWriter
        writer = EvidenceWriter(args.evidence_dir)
        written = writer.write(evidence)
        logger.info("  Written: %d evidence files", len(written))

    # ------------------------------------------------------------------ #
    # Step 4: LLM report generation
    # ------------------------------------------------------------------ #
    logger.info("Step 4/4: Generating report sections ...")

    from src.evidence.reader import EvidenceReader
    reader = EvidenceReader(args.evidence_dir)

    # Verify evidence is present
    available = reader.available_sections()
    if not available:
        logger.error(
            "Evidence store is empty. Run without --skip-analysis first, "
            "or check that %s/ contains JSON files.", args.evidence_dir
        )
        return 1

    # Set up LLM provider
    if args.skip_llm:
        logger.info("  Using StubProvider (--skip-llm specified)")
        from src.llm.provider import StubProvider
        provider = StubProvider()
    else:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.error(
                "GEMINI_API_KEY not set. "
                "Copy .env.example to .env and add your key, "
                "or use --skip-llm for a dry run."
            )
            return 1
        from src.llm.provider import GeminiProvider, LLMError
        try:
            provider = GeminiProvider(api_key=api_key, model=args.model)
        except LLMError as e:
            logger.error("%s", e)
            return 1

    # Generate all sections
    from src.generation.report_builder import ReportBuilder
    builder = ReportBuilder(reader=reader, provider=provider)
    result = builder.build_all()
    sections = result.sections

    # Summary of generation
    if result.status == "INCOMPLETE":
        logger.error("Generation INCOMPLETE due to LLM error: %s", result.error)
        logger.error("Draft report will be saved, but cannot be approved until this is resolved.")
    
    flagged = [s for s in sections if s.review_status.value == "flagged"]
    if flagged:
        logger.warning(
            "  %d section(s) FLAGGED by validator: %s",
            len(flagged),
            [s.section_name for s in flagged],
        )
    elif result.status != "INCOMPLETE":
        logger.info("  All %d sections generated without flags.", len(sections))

    # Assemble the Markdown report
    metadata = reader.get("metadata")
    from src.reporting.markdown_writer import MarkdownWriter
    report_writer = MarkdownWriter(output_path=args.output)
    report_path = report_writer.write(
        sections=sections,
        metadata=metadata,
        case_listing_path=Path(args.evidence_dir) / "case_listing.json",
    )
    from src.review_manifest import write_review_manifest
    review_path = write_review_manifest(report_path, sections, result.status)
    logger.info("Review manifest saved: %s", review_path)

    # ------------------------------------------------------------------ #
    # Done
    # ------------------------------------------------------------------ #
    elapsed = time.time() - start_time
    logger.info("")
    logger.info("=" * 60)
    logger.info("GenAR complete in %.1f seconds.", elapsed)
    logger.info("Report saved: %s", report_path)
    logger.info("Evidence: %s/", args.evidence_dir)

    if result.status == "INCOMPLETE":
        logger.error(
            "ACTION REQUIRED: Generation failed (INCOMPLETE). "
            "Report cannot be finalized until generation succeeds."
        )
    elif flagged:
        logger.warning(
            "ACTION REQUIRED: %d section(s) flagged â€” review validation notes "
            "in the report before use.", len(flagged)
        )
    else:
        logger.info(
            "All sections passed automated validation. "
            "Run the human review CLI to approve:"
        )
        logger.info("  python src/review.py %s", report_path)
    logger.info("=" * 60)

    return 0


def _banner() -> None:
    print("""
  ___            _   ____
 / __|  ___  _ _  /_\\ |  _ \\
| (_ | / -_)| ' \\/ _ \\| |_) |
 \\___| \\___||_||_/_/ \\_|____/
 GenAR â€” AI-assisted PADER Generator v0.1.0
""")


if __name__ == "__main__":
    sys.exit(main())

