# Core 17 — Test Report

**Status:** PASS — metric/statistical calculation software acceptance only.  
**Exact tested commit:** d9ac96553b9b701af198668577836274422edc10  
**CI run:** 44200262195 — https://github.com/msellamiTN/socioweave-studio/actions/runs/44200262195

## Evidence
- Implementation: engine/sociodec/metrics.py
- Tests: engine/tests/test_metrics.py
- Specification: docs/CORE-17-SCIENTIFIC-METRICS-STATISTICS.md
- Environment: GitHub Actions, Ubuntu latest, CPython 3.11.18, pytest 9.2.0
- Command: python -m pytest -q from engine/
- Result: **295 passed in 0.43s; 0 failed; 0 skipped.**

## Corrections retained as regression history
- Initial test run exposed two assertions using a non-existent field name; tests now assert the public validity field.
- A subsequent test caught one remaining stale assertion; corrected and rerun on the exact accepted commit.
- The small-sample p-value test reflects the documented normal approximation rather than asserting an exact-test threshold.

## Limitations
- Gold annotations, equivalence judgments, execution outcomes and utilities must be supplied by the experiment campaign.
- Wilcoxon p-values use a tie-corrected normal approximation with continuity correction; exact/permutation sensitivity analysis is not implemented.
- Bootstrap intervals are percentile intervals and can be unstable for small samples.
- No E1–E9 experiment, human annotation campaign or provider-backed evaluation has been executed.
- Software acceptance does not establish semantic extraction quality, strategy superiority or production readiness.
