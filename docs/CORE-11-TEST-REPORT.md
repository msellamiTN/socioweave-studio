# Core 11 — Adaptive Orchestrator Test Report

**Status:** PASS — software orchestration acceptance.  
**Exact tested code commit:** 87ef835854c11bdc5574bcb54cd88091b321fd61  
**CI run:** https://github.com/msellamiTN/socioweave-studio/actions/runs/44192309216  
**Environment:** GitHub Actions, Ubuntu latest runner, CPython 3.11  
**Command:** python -m pytest -q (from engine/)  
**Result:** **186 passed in 0.36s; 0 failed; 0 skipped.**

## Verified scope

- Extraction is invoked once; q is derived from retained extractor-level results.
- Two initial drafts are requested separately and both are forwarded as seeds to the first strategy adapter.
- Diagnosis is computed from extraction and the two initial drafts.
- The initial union is checked and cycles are removed using support counts; no model repair call is made at this stage.
- Rule 0 returns the checked union when it is valid and no escalation condition applies.
- Initial-union failures trigger the corresponding Algorithm 2 escalation.
- C8 strategy adapter invocation and sequential chaining are exercised.
- The previous strategy result is forwarded as the chain seed to the next strategy.
- Algorithm 1 validation/repair is applied to strategy outputs.
- Actual adapter call counts, strategy-specific Table 4 allowances and the one-call repair reserve are enforced.
- Budget truncation reports strategies not run.
- The C1 Algorithm 3 phase-composition allowance is tested as 2n + 3 (nine calls for n=3), not as four full sequential strategy runs.
- The paper lexicographic best-result order is implemented using subproblem equivalence for redundancy and |E|/|S| for coupling.
- Invalid adapter outputs, insufficient budget and over-budget adapters fail closed.
- Event trace records extraction, initial drafts, diagnosis, initial union, strategy execution, best updates, escalation and budget stops.

## Scientific and engineering boundaries

- The orchestration is integrated through injected adapters. A concrete provider-backed adapter must still instantiate each strategy's SocialStrategy, preserve its visibility/role/decision-rule semantics, invoke the runtime, and produce the decision result. The orchestrator does not fabricate these protocol definitions.
- Initial-draft isolation and model-family selection are adapter responsibilities; separate calls and author indices do not prove statistical independence.
- Semantic flags open, val and just remain caller-supplied because the current extraction schema does not infer them.
- The strategy adapter is required to apply the relevant decision operator and report actual call counts and candidate edge-support evidence. The orchestrator validates reported counts; it cannot reverse external calls if an adapter lies.
- Strategy cost reservations use Table 4 formulas and preserve the repair reserve. Seed adoption can reduce actual calls; the full catalogue allowance is an upper bound.
- C1 is phase composition under Algorithm 3. The adapter must implement the composition protocol, not call four complete strategies serially.
- Structural validation checks V1, V2, V5 and hypothesis verdict completeness. V3 solvability and V4 faithfulness remain NOT_EVALUATED without executor evidence.
- Passing tests establish software control-flow behavior, not semantic decomposition quality, LLM extraction accuracy, strategy effectiveness, or production readiness.

## Decision

Core 11 meets the software orchestration acceptance gate on the exact code commit above. The full integrated test suite passed with no failures or skips. Provider-backed strategy adapters and executor-backed V3/V4 evidence remain separate integration and scientific-validation gates.
