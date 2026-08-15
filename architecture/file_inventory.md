# GenAR Repository Inventory

Generated during final-submission cleanup. No files were deleted during inventory.

## Proposed Structure Mapping

| Proposed location | Current location | Classification | Action |
|---|---|---|---|
| `src/main.py` | `src/main.py` | Required source | Retain |
| `src/review.py` | `src/review.py` | Required source | Retain |
| `src/review_manifest.py` | `src/review_manifest.py` | Required source | Retain |
| `src/analysis/` | `src/analysis/` | Required source | Retain |
| `src/generation/` | `src/generation/` | Required source | Retain |
| `src/llm/` | `src/llm/` | Required source | Retain |
| `src/reporting/` | `src/reporting/` | Required source | Retain |
| `src/validation/` | `src/validation/` | Required source | Retain |
| `src/models/` | `src/models/` | Required source | Retain |
| `src/config/` | `src/config/` | Required source/configuration | Retain |
| `prompts/` | `prompts/` | Required documentation/input | Retain |
| `tests/` | `tests/` | Required tests | Retain |
| `evidence/` | `evidence/` | Generated artifact | Retain as reproducible evidence output |
| `reports/` | `reports/` | Generated artifact | Retain final draft/review outputs; remove stale duplicates |
| `version1/` | `version1/` | Required documentation/reference | Retain |
| `architecture/` | Not present | Required documentation | Created for inventory and architecture notes |
| `README.md` | `README.md` | Required documentation | Retain |
| `requirements.txt` | `requirements.txt` | Required configuration | Retain |
| `.env.example` | `.env.example` | Required configuration | Retain |
| `.gitignore` | `.gitignore` | Required configuration | Retain |
| Dataset | `Bisoprolol_icsr_sample_1068rows.xlsx` | Dataset | Retain locally for offline verification; exclude from final submission if required |
| Helper scripts | `run_analysis.py`, `run_validation.py`, `inspect_data.py` | Development utilities | Retain because they are documented runnable utilities |
| Debug script | `scripts/debug_validator.py` | Temporary/debug artifact | Remove after confirming no imports/references |
| Logs/cache/environment | `.venv/`, `.pytest_cache/`, `__pycache__/`, `.env`, `stage1_output.txt`, `review_*.log`, `pipeline_final.log` | Cache/temporary artifact | Remove |

## Current Python File Map

All application Python modules are already located under `src/` in the proposed structure. No source-code moves or import changes are required. The test modules are already under `tests/`, and prompt files are already under `prompts/`.

## Cleanup Decision

The cleanup will remove only verified temporary/debug artifacts and stale duplicate generated reports. It will not modify application source, deterministic analysis, validator semantics, prompts, tests, configuration templates, or the one-call LLM flow.
