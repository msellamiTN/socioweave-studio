# Core 05 — Algorithm 1 Structural Repair

**Status:** PASS — structural repair software acceptance on commit `b9efe9d40d85ed44d356a6bc312283ddf82d3aa7`.  
**Scientific source:** The final check/repair phase of Algorithm 1 in Section 6.1.

## 1. Paper contract

After the decision rule returns D*, Algorithm 1 checks V1, V2, V5 and hypothesis verdict completeness. If failures remain:

1. Cycles are broken by a deterministic rule without a model call: among the edges of a cycle, remove the edge supported by the fewest candidates; repeat until acyclic.
2. If failures other than cycles remain, send them to the agent that applied the decision rule (or the author when no agent applied it). That agent adds or extends subproblems in one repair call.
3. Re-run the checks. If failures remain, return the decomposition with the failure set for escalation. Repair is attempted once.

## 2. Software realization

- `remove_least_supported_cycle_edge` removes the least-supported edge from one reported cycle.
- `repair_decomposition` repeatedly finds and breaks cycles, validates again, optionally invokes one injected callback for non-cycle failures, and performs a final validation.
- Candidate support counts are required for every edge in the cycle. Missing evidence is an error; the implementation does not invent a count.
- Ties are broken lexicographically by edge identifier. The paper does not prescribe tie behavior; this is a deterministic engineering convention.
- The callback represents the one model repair call. The core does not choose an LLM/provider or construct its prompt.
- The final report is returned even if repair fails. No success is claimed before revalidation.

## 3. Scope boundary

The repair callback may return a still-invalid decomposition. It is invoked at most once. A new cycle introduced by the callback is reported by the final check and is not silently repaired in a second pass, matching Algorithm 1's single post-repair check.

V3 solvability and V4 faithfulness remain NOT_EVALUATED without executor evidence. This core performs no model call itself and does not establish scientific repair effectiveness.

## 4. Acceptance evidence

From `engine/`:

    python -m pip install -e '.[dev]'
    python -m pytest -q

**Result:** 96 passed in 0.09s; 0 failed; 0 skipped.  
**Exact tested commit:** `b9efe9d40d85ed44d356a6bc312283ddf82d3aa7`.  
**CI:** [Workflow run 44186324292](https://github.com/msellamiTN/socioweave-studio/actions/runs/44186324292).  
See [CORE-05-TEST-REPORT.md](CORE-05-TEST-REPORT.md) for detailed scope and limitations.

This acceptance is software-level repair-policy validation only; it is not evidence of empirical repair effectiveness, executor solvability or answer faithfulness.
