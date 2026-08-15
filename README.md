# GenAR — Evidence-Grounded PADER Report Generator

GenAR is a Gemini-based Python prototype that transforms an ICSR safety dataset into an evidence-grounded PADER-style report. Python performs validation, normalization, deterministic analysis, aggregation, percentage calculation, evidence generation, and output validation. Gemini is used only for controlled narrative generation from selected evidence.

## Architecture

Input dataset → validation/normalization → deterministic analysis → evidence JSON store → section-specific context assembly → Gemini (one narrative call) → narrative sections → output validation → draft report → human review → approved final report.

Python computes demographics, reactions, outcomes, alerts, trends, case listings, counts, percentages, and evidence. Gemini interprets supplied evidence and produces regulatory-neutral narrative text; it does not receive the raw dataset directly or calculate deterministic metrics. Human review is required before approval.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add a Gemini key only for a genuine AI-generation run:

```powershell
Copy-Item .env.example .env
# Edit .env and set GEMINI_API_KEY
```

Never commit `.env`. The project uses the modern `google-genai` SDK and contains only the Gemini provider.

## Running

Genuine Gemini path:

```powershell
python -X utf8 src\main.py --input <dataset>
```

The default genuine report output is `reports/report_output.md`. Set `GEMINI_API_KEY` and optionally `GEMINI_MODEL`.

Offline validation path:

```powershell
python -X utf8 src\main.py `
  --input <dataset> `
  --skip-llm `
  --output reports\draft_report.md
```

`--skip-llm` uses `StubProvider` for offline testing only. Its output is not a genuine AI-generated report and must not be approved as the final submission artifact.

Human review:

```powershell
python -X utf8 src\review.py reports\draft_report.md
```

The reviewer inspects generation status, validation status, issues, warnings, and section completeness. Approval requires successful generation and validation; rejection does not create `final_report.md`.

## Evidence grounding and prompts

The raw dataset is not sent directly to Gemini. The pipeline creates evidence JSON first, then builds a section-specific context packet from that evidence and the production prompt in `prompts/narrative.txt`. The output validator checks unsupported, contradicted, or unverified claims, expectedness wording, unavailable capabilities, required sections, and forbidden safety conclusions.

## Tests and evaluation

```powershell
python -m pytest tests\ -v
```

Tests cover deterministic analysis, evidence-backed narrative validation, and review-related behavior.

## Genuine report artifact

A genuine `reports/report_output.md` must come from the Gemini path. This repository does not fabricate one or present StubProvider output as genuine. If Gemini access or quota is unavailable, `reports/README.md` records that the report still needs to be regenerated with valid Gemini access.

## Limitations and Version 1

The current implementation is PADER-specific, depends on the expected input schema, requires Gemini access for genuine narrative generation, does not replace regulatory or medical review, and requires human approval. The conceptual reusable-system design is documented in `version1/design.md`.
