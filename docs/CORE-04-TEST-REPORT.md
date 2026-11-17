# Core 04 — Decomposition Validity Test Report

**Acceptance status:** PASS — structural validation software acceptance  
**Exact accepted commit:** `346946bdee8bad31bbddbc23f82df36dc00900f6`  
**CI run:** [44185812190](https://github.com/msellamiTN/socioweave-studio/actions/runs/44185812190)  
**Job:** `test` — completed successfully  
**Environment:** GitHub Actions, Ubuntu 26.04 runner, CPython 3.11.18, pytest 9.2.0  
**Install:** `python -m pip install -e ".[dev]"`  
**Test command:** `python -m pytest -q`  
**Result:** **86 passed in 0.12s; 0 failed; 0 skipped.**

## Verified scope

The full integrated suite passed, including:
- V1 exact coverage comparison, including missing explicit requirements;
- confirmed hypotheses added to the effective requirement universe;
- rejected hypotheses excluded from the effective requirement universe;
- missing, duplicate and unknown hypothesis verdict detection;
- V2 self-loop and multi-node directed-cycle detection;
- deterministic cycle witness generation;
- V5 empty deliverable contributor detection;
- V5 sink-subproblem contribution checks;
- distinction between structural validation and executor-dependent checks;
- V3 and V4 explicitly reported as NOT_EVALUATED;
- validation of malformed hypothesis verdict values;
- Core 01–03 regression and integration coverage.

## Scientific boundaries

The implementation follows Definition 6 for V1–V5 and the hypothesis-verdict portion of Algorithm 1's final check.

This PASS is limited to software-level structural validation:
- V1, V2 and V5 are checked programmatically.
- Hypothesis verdict completeness is checked as required by Algorithm 1.
- V3 solvability is NOT_EVALUATED because no executor M is invoked.
- V4 faithfulness is NOT_EVALUATED because no composed answer is evaluated against hard constraints.
- No automatic cycle repair, one-call requirement repair or escalation orchestration is implemented in this Core.
- No benchmark or LLM quality claim is made.

A `structural_valid` result must not be interpreted as full Definition 6 validity until V3 and V4 have execution evidence.

## Decision

Core 04 meets the software acceptance gate on the exact commit above. The full integrated suite passed with no failures or skips. The structural validator can now be used by orchestration components, while execution-level solvability and faithfulness remain explicit downstream responsibilities.
