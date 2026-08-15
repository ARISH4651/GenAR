# Version 1 Design: Reusable Regulatory Reporting System

GenAR V0 is intentionally PADER-specific. A future reusable system should preserve its evidence-grounded separation of concerns while making report definitions configurable.

## Configurable report types and sections

A report registry could define PADER, PSUR, PBRER, DSUR, and CSR profiles. Each profile would declare required sections, ordering, narrative rules, and output schema. Sections should be independently enabled, reordered, versioned, and validated.

## Evidence dependencies and reusable deterministic analysis

Each section should declare its evidence keys and deterministic analyses. Reusable analyses such as demographics, reactions, outcomes, seriousness, trends, and case listings could serve multiple report profiles. Evidence objects should carry stable schemas, provenance, source-period metadata, and calculation versions.

## Model abstraction concept

The current implementation remains Gemini-only. Conceptually, a future provider adapter could be selected by configuration, but V1 does not implement another provider. Every provider would receive the same evidence-grounded context contract and return the same structured narrative schema.

## Versioning, tracing, and evaluation

Report definitions, prompts, evidence schemas, deterministic analysis code, and model configuration should be versioned independently. Narrative claims should be traceable to their section, evidence key, source calculation, prompt version, and generation run. Evaluation should combine deterministic correctness tests, grounding tests, schema validation, forbidden-claim checks, section completeness, human review sampling, and regression fixtures.

## Future report families

The same framework can support PSUR, PBRER, DSUR, and CSR by adding profiles, section specifications, evidence dependencies, and evaluation suites. Those extensions should not alter the V0 Gemini-only implementation until separately designed and approved.
