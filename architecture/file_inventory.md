# GenAR Final Submission Inventory

| Classification | Final contents |
|---|---|
| Required source | `src/` including analysis, validation, evidence, generation, reporting, models, config, LLM, `main.py`, `review.py`, and `review_manifest.py` |
| Required tests | `tests/` |
| Required prompts | `prompts/narrative.txt`, the only prompt loaded by the current production context builder |
| Required configuration | `.env.example`, `.gitignore`, `requirements.txt` |
| Required documentation | `README.md`, `architecture/architecture.md`, `version1/design.md`, `reports/README.md` |
| Generated/local artifacts excluded | dataset, `.env`, `.venv`, caches, evidence JSON, draft/final reports, review manifests, logs |
| Removed after reference audit | obsolete root-level utilities, unused legacy prompt files, debug script, and stale generated reports |

All application Python files were already under the proposed `src/` structure, so no source imports or runtime paths were moved. The final submission deliberately does not include a fabricated StubProvider report; a genuine `reports/report_output.md` must be generated through Gemini access.
