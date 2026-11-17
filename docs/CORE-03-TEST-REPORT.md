# Core 03 — Decomposition Model Test Report

**Acceptance status:** PASS — software model and contract suite  
**Exact tested commit:** `d8160ed2f2211c964d51a4ef5ec08beecac7bd0a`  
**CI run:** [44185214955](https://github.com/msellamiTN/socioweave-studio/actions/runs/44185214955)  
**Job:** `test` — completed successfully  
**Environment:** GitHub Actions, Ubuntu 26.04 runner, CPython 3.11.18, pytest 9.2.0  
**Install:** `python -m pip install -e ".[dev]"`  
**Test command:** `python -m pytest -q`  
**Result:** **75 passed in 0.12s; 0 failed; 0 skipped.**

## Verified scope

The complete integrated suite passed, including Core 01 and Core 02 regressions and the new Core 03 tests:
- Definition 4 subproblem representation and requirement coverage;
- Definition 5 decomposition representation (D=(S,E,κ));
- directed dependency orientation and reference integrity;
- deliverable-to-subproblem composition and union coverage;
- uniqueness and non-empty identifier/text contracts;
- duplicate subproblem, dependency, contributor and deliverable-key rejection;
- dangling dependency and composition reference rejection;
- prompt-relative local-constraint membership in C;
- prompt-relative requirement coverage membership in R(P);
- declared deliverable key validation and totality of κ over prompt deliverables;
- explicit preservation of cycles/self-edges and empty contributor sets for later validity checking.

## Scientific and architectural boundaries

The implementation follows Definitions 4 and 5. The representation uses stable string identifiers for subproblems and stores requirement/constraint references as Core 01 values.

The model's prompt-relative validator checks that local constraints are drawn from C, coverage labels are drawn from the supplied R(P), and κ has exactly the declared deliverable keys. It does not establish that a dependency edge is semantically justified by actual input/output use; this is represented by the producer and requires later semantic validation.

This PASS does not establish decomposition validity:
- V1 complete coverage is not checked here;
- V2 acyclicity is not checked here;
- V3 executor solvability requires execution;
- V4 faithfulness requires evaluating the composed answer against hard constraints;
- V5 non-empty deliverable contribution and sink coverage are reserved for Core 04.

No benchmark, LLM quality, or executor-level scientific result is claimed.

## Decision

Core 03 meets the software acceptance gate on the exact commit above: the complete integrated pytest suite passed with no failures or skips. Core 04 may now implement formal validity checks while preserving the distinction between programmatically checkable V1/V2/V5 properties and execution-dependent V3/V4 properties.
