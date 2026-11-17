# Core 02 — Requirement Extraction Test Report

**Acceptance status:** PASS — software implementation and automated contract suite  
**Commit under test:** `4b4d0b29eb1f6b963662e9f115e67a4db65fd851`  
**Workflow run:** [44181085215](https://github.com/msellamiTN/socioweave-studio/actions/runs/44181085215)  
**Job:** `test` — completed successfully  
**Environment:** GitHub Actions, Ubuntu 26.04 runner, CPython 3.11.18, pytest 9.2.0  
**Command:** `python -m pytest -q` (after `python -m pip install -e ".[dev]"`)  
**Result:** **55 passed in 0.07s; 0 failed; 0 skipped.**

## Verification evidence

The workflow checked out the exact commit listed above, installed the engine in editable mode with development dependencies, and ran the complete pytest suite. The only test job and all its steps completed successfully.

The suite includes:
- Core 01 prompt/requirement model and integration regression coverage;
- extraction parsing and typed explicit/implicit separation;
- source-span validation and malformed JSON rejection;
- invalid records across extraction sections;
- union, deduplication and provenance preservation;
- provenance-key collision regression across requirement types/domains;
- custom equivalence matcher behavior;
- provider invocation contract and extractor ordering;
- ambiguity/conflict structural invariants.

## Scope and limitations

This PASS is an **automated software acceptance result**, not a scientific evaluation of extraction quality.

It does not establish:
- precision, recall or F1 against human-annotated gold requirements;
- semantic entailment between extracted requirement statements and their source spans;
- quality/calibration of implicit-requirement hypotheses;
- ambiguity/conflict detection precision or recall;
- independence of multiple extractors or reduced error correlation;
- model suitability, latency or throughput on a T4 GPU;
- end-to-end decomposition validity or executor-level solvability.

Those claims require the paper-aligned benchmark datasets, human annotation, repeated seeds, model/provider controls and statistical analysis. Until those experiments are run, extraction quality remains **not scientifically validated**.

## Decision

Core 02 meets the current software quality gate: full suite green on the exact commit, with boundary, negative, contract, regression and integration coverage represented in the test suite. The implementation may be used as the software foundation for Core 03. Semantic evaluation remains a separate research workstream and must not be represented as passed.
