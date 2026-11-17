# Core 01 — Acceptance Test Report

**Decision: PASS (automated software acceptance).**

## Tested revision

- Repository: `msellamiTN/socioweave-studio`
- Branch: `main`
- Commit: `49aedd17566318873841fb3eed7d16a7d57744a5`
- CI run: [44180857556](https://github.com/msellamiTN/socioweave-studio/actions/runs/44180857556)
- Environment: GitHub Actions, Ubuntu 26.04.1, CPython 3.11.18
- Install: `python -m pip install -e ".[dev]"`
- Test command: `python -m pytest -q` (working directory `engine/`)
- Result: **39 passed in 0.11s; 0 failed; 0 skipped**

## Evidence by quality layer

| Layer | Evidence | Result |
|---|---|---|
| Static/import and package installation | Editable package installation and test-module imports in CI | PASS |
| Unit tests | Prompt, interpretation, requirement, entity, and source-span behavior | PASS |
| Boundary tests | Empty/blank fields, invalid intervals, exact-end offsets, overrun, Unicode | PASS |
| Negative tests | Invalid constructors, missing spans, duplicate entities, invalid ranges | PASS |
| Integration | Extracted requirements validated through the Prompt model | PASS |
| Property/invariant checks | Exhaustive valid half-open slices for parameterized short Unicode strings; frozen value behavior | PASS |
| Regression | Invalid extraction span fixture was caught, corrected, and retained in CI | PASS |
| Contract | Prompt tuple aliases, hard/soft partition, entity/requirement distinction, source-span contract | PASS |
| Reproducibility | Exact commit, Python version, runner OS, install and test commands recorded above | PASS |

## Scope and scientific limitations

- This report certifies the implemented Core 01 software contract and automated tests only.
- The paper requires source spans, but the half-open character-offset convention is an implementation choice.
- The implementation checks span bounds and non-empty source text; it does not prove semantic entailment between a requirement statement and its span.
- It stores a declared interpretation and does not enumerate `Int(x)` or infer implicit requirements.
- No claim is made about LLM extraction accuracy, semantic correctness, benchmark quality, or downstream decomposition validity.

## Acceptance decision

Core 01 is accepted as a tested domain-model increment. Core 02 remains a separately scoped extraction implementation; its semantic evaluation remains outstanding. Continue to enforce the complete-suite gate for every subsequent Core.