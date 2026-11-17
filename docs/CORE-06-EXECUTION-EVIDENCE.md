# Core 06 — Execution Evidence for V3 and V4

**Status:** PASS — execution evidence contract acceptance on commit `0194fb0efc7d696de99527c6d61b41bd098a70a0`.  
**Scientific source:** Definition 6, V3 and V4; experimental protocol describing a fixed executor (M_E).

## 1. Paper contract

- **V3 Solvability:** executor M solves each subproblem using the answers of its predecessors.
- **V4 Faithfulness:** the composed answer satisfies the prompt's hard constraints (C_h).

The paper states that V3 and V4 can only be observed by execution. In the experimental protocol, a fixed executor (M_E) solves subproblems in topological order and composes their answers for each strategy.

## 2. Engineering realization

This Core defines an execution evidence contract:
- `ExecutionRun` identifies the executor, ordered subproblem executions, composed answer and hard-constraint assessments.
- `SubproblemExecution` records solved/failed status, produced answer and the exact predecessor answers consumed.
- `assess_execution` checks that every subproblem has one record, all required predecessors were consumed, predecessor answers match their recorded outputs, and the execution order is topological.
- V4 requires an evidence-bearing assessment for every hard constraint; missing, foreign or violated assessments fail.
- `combine_validity` combines the structural report from Core 04 with execution evidence to expose full validity.

## 3. Scientific boundary

This is a software evidence contract, not a new theorem in the paper. The code checks completeness and consistency of supplied execution/evaluator records. It does not independently prove that a tool actually ran, that an executor's answer is correct, or that a natural-language claim satisfies a constraint.

V4 PASS means the supplied verifier evidence is complete and affirmative. It must be backed by a trusted evaluator, test, measurement or human assessment appropriate to the constraint. The evaluator provenance and raw evidence should be persisted by the experiment runner.

## 4. Acceptance evidence

From `engine/`:

    python -m pip install -e '.[dev]'
    python -m pytest -q

**Result:** 108 passed in 0.14s; 0 failed; 0 skipped.  
**Exact tested commit:** `0194fb0efc7d696de99527c6d61b41bd098a70a0`.  
**CI:** [Workflow run 44186672952](https://github.com/msellamiTN/socioweave-studio/actions/runs/44186672952).  
See [CORE-06-TEST-REPORT.md](CORE-06-TEST-REPORT.md) for detailed scope and limitations.

This acceptance is software-level evidence-contract validation only; it is not empirical executor or benchmark validation.
