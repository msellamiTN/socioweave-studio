# Core 06 — Execution Evidence for V3 and V4

**Status:** Implementation and full-suite acceptance pending.  
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

## 4. Acceptance

From `engine/`:

    python -m pip install -e '.[dev]'
    python -m pytest -q

Acceptance requires the complete integrated suite, including V3/V4 positive and negative cases, to pass on the exact final commit.
