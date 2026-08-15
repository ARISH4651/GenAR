# GenAR Actual Architecture

Input Dataset
    ↓
Validation / Normalization — src/validation/validator.py
    ↓
Deterministic Analysis — src/analysis/ and Pandas
    ↓
Evidence JSON Store — src/evidence/
    ↓
Context Assembly — src/generation/context_builder.py
    ↓
Gemini — src/llm/provider.py, one API call
    ↓
Narrative Generation — src/generation/report_builder.py
    ↓
Output Validation — src/generation/output_validator.py
    ↓
Draft Report — src/reporting/markdown_writer.py
    ↓
Human Review — src/review.py
    ↓
Approved Final Report

## Responsibility boundaries

Python performs validation, normalization, counting, aggregation, percentages, demographics, reactions, outcomes, alerts, trends, case listings, evidence generation, required-section checks, and output validation. These operations are not delegated to the LLM.

Gemini is the sole model provider. It receives a system instruction, a section-specific context packet, and selected evidence. Its role is limited to narrative generation, interpretation of supplied evidence, and controlled regulatory-neutral wording. It does not receive the raw dataset directly and does not calculate deterministic metrics.

The human reviewer inspects generation status, validation status, issues, warnings, and section completeness. Successful generation and validation are prerequisites for approval.
