# Core 17 — Test Report

**Status:** Pending final CI verification.  
**Scope:** Metric/statistical calculation software only; no empirical campaign results.

## Evidence
- Implementation: engine/sociodec/metrics.py
- Tests: engine/tests/test_metrics.py
- Specification: docs/CORE-17-SCIENTIFIC-METRICS-STATISTICS.md
- Command: python -m pytest -q from engine/
- Tested commit, CI run, runtime and test count: fill only after inspecting the final workflow run.

## Limitations
- Gold annotations, equivalence judgments, execution outcomes and utilities must be supplied by the experiment campaign.
- Wilcoxon p-values use a tie-corrected normal approximation with continuity correction; exact/permutation sensitivity analysis is not implemented.
- Bootstrap intervals are percentile intervals and can be unstable for small samples.
- No E1–E9 experiment has been executed by adding these metric functions.
