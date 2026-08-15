# GenAR — AI Engineering Challenge

GenAR is a Python prototype that transforms a supplied Bisoprolol ICSR safety dataset into a structured, evidence-backed PADER-style report.

## Architecture

The project implements a deterministic analysis pipeline coupled with an LLM generation layer:

1.  **Data Validation (`src/validation/`)**: Cleans and validates the raw Excel data using pandas and Pydantic schemas. Enforces normalisation rules and logs warnings for missing or anomalous data.
2.  **Analysis Engine (`src/analysis/`)**: Computes deterministic, case-level metrics from the validated dataset. Grouped into modules: demographics, reactions, outcomes, alerts, trends, and case listings. Crucially, **the LLM is not used for calculations**.
3.  **Evidence Store (`src/evidence/`)**: Serialises the outputs of the analysis engine into structured JSON files (`evidence/*.json`). This serves as the single source of truth for the LLM.
4.  **Context Builder (`src/generation/context_builder.py`)**: For each section of the PADER report, selects only the relevant JSON evidence and pairs it with a section-specific prompt (`prompts/*.txt`). Large data (like full case listings) are summarised.
5.  **LLM Generation (`src/llm/provider.py`)**: Uses the Gemini API (configurable) to generate narrative text based strictly on the provided evidence.
6.  **Output Validator (`src/generation/output_validator.py`)**: Scans LLM-generated text for hallucinations, missing required evidence figures, and forbidden phrases (e.g., claiming SOC analysis when none exists).
7.  **Markdown Writer (`src/reporting/markdown_writer.py`)**: Assembles the final report. Deterministic tables (like the Case Index) are appended directly from the evidence store, bypassing the LLM.

## Setup

1.  Clone the repository and navigate to the project directory.
2.  Install dependencies:
    ```bash
    pip install pandas openpyxl pydantic pytest pytest-cov python-dotenv google-generativeai
    ```
3.  Set up your environment variables by copying `.env.example` to `.env` and adding your Google Gemini API key:
    ```bash
    cp .env.example .env
    # Edit .env and add your GEMINI_API_KEY
    ```

## Usage

### Run the full pipeline (Data -> Evidence -> LLM Report)
Requires `GEMINI_API_KEY` to be set in `.env` or as an environment variable.
```bash
python -X utf8 src/main.py --input Bisoprolol_icsr_sample_1068rows.xlsx --output reports/report_output.md
```

### Dry Run (Skip LLM)
Test the deterministic pipeline and report assembly without making API calls. Uses a stub text generator.
```bash
python -X utf8 src/main.py --input Bisoprolol_icsr_sample_1068rows.xlsx --skip-llm --output reports/report_stub.md
```

### Skip Analysis (Reuse Evidence)
If you've already run the analysis step and want to quickly re-generate the report from existing evidence:
```bash
python -X utf8 src/main.py --input Bisoprolol_icsr_sample_1068rows.xlsx --skip-analysis
```

## Testing

Run the full test suite (77 tests covering validation, analysis, and generation modules):
```bash
python -X utf8 -m pytest tests/ -v
```
