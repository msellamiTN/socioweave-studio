# Core 10 — Adaptive Strategy Selector Test Report

**Status:** PASS — software acceptance.  
**Exact tested commit:** b57a0c89b8e0bd11948300794e4d567f16b81f1d  
**CI run:** https://github.com/msellamiTN/socioweave-studio/actions/runs/44189680999  
**Environment:** GitHub Actions, Ubuntu latest runner, CPython 3.11  
**Command:** python -m pytest -q (from engine/)  
**Result:** **176 passed in 0.27s; 0 failed; 0 skipped.**

## Coverage

- Prompt feature model: non-negative counts, family count, normalized Jaccard gaps, non-negative coupling ratio, strict boolean flags.
- Diagnosis: extraction-derived constraint/domain/hypothesis counts, ambiguity/conflict flags, content/structure gaps, mean coupling, decomposition distance, and initial union.
- Table 8: Rule 0; both reading rules; all seven production rules; all four scrutiny/default rules.
- Boundary conditions: epsilon, 2epsilon, theta_c, model-family requirement, coupling threshold.
- Escalation: uncovered requirement/hypothesis, cycle/composition, other failures, high stakes, and escalation after the fallback S5.
- Budget: mandatory extraction + two initial drafts, strategy cost reservation, one repair-call reserve, and unrun strategy reporting.
- Negative cases: invalid feature ranges/types, invalid budget, invalid thresholds and distance.
- Regression cases discovered during CI are retained in the suite.

## Scope and limitations

This is acceptance of the deterministic software planner, not evidence that the strategies improve decomposition quality.

The Core does not itself generate the initial isolated drafts, enforce model-family diversity, run the strategy protocol, inject seeds into runtime, execute Algorithm 1, refresh failures after every strategy, or compare competing decompositions by the complete paper lexicographic objective. Those are orchestration integrations still required for a complete end-to-end Algorithm 2 execution.

The extraction schema does not infer open-prompt, stakeholder-value and justified-plan flags; these are supplied by the caller. Budget estimates use full Table 4 catalogue costs plus one repair reserve. Seed-adjusted call savings are not yet represented and the estimate is therefore conservative, not an exact runtime call count.

No strategy-effectiveness, semantic extraction quality, solvability, faithfulness or production-readiness claim follows from these tests.
