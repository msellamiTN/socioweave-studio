# Core 15 — Unified Validation and Repair Integration

**Status:** IN PROGRESS — awaiting full CI acceptance.  
**Scientific basis:** Definition 6 (V1–V5), Algorithm 1 (hypothesis verdicts, cycle repair, one repair call and final check), and Algorithm 2 (candidate selection, escalation and budgeted orchestration).

## 1. Objective

Close the integration boundary between adaptive orchestration and final validity assessment. The selected decomposition must remain traceable to the evidence that justified its selection.

## 2. Delivered behavior

- AdaptiveResult retains the source prompt and the winning strategy's hypothesis verdicts, candidate-edge support counts and run identifier.
- The winning candidate is compared using its own effective requirement universe (explicit requirements plus its confirmed hypotheses), while the initial baseline remains evaluated against the explicit extraction until verdicts exist.
- finalize_adaptive_result recomputes structural validation for the selected decomposition from the retained winning verdicts.
- Without executor evidence, V3 and V4 remain NOT_EVALUATED.
- With an explicit ExecutionRun, the finalizer invokes the Core 06 evidence validator and returns a combined structural/execution validity report.

## 3. Explicit boundaries

- The finalizer does not execute subproblems and does not manufacture executor evidence.
- V3/V4 PASS means the supplied execution trace satisfies the software evidence contract; it is not an independent semantic proof that generated answers are true.
- A strategy's hypothesis verdicts apply to that strategy's candidate only. The initial union has no verdicts and therefore cannot silently inherit another candidate's confirmations.
- Candidate support counts remain the adapter's evidence; this Core preserves them with the selected result but does not infer missing counts.
- Strategy/provider quality and E1–E9 effectiveness remain unmeasured.

## 4. Acceptance tests

- Recompute V1/V2/V5 and hypothesis verdict completeness for the selected winner.
- Preserve winning strategy identity and verdict evidence.
- Keep V3/V4 NOT_EVALUATED when no execution run is supplied.
- Evaluate V3/V4 only from explicit, supplied Core 06 execution evidence.
- Exercise the complete mocked extraction → two drafts → strategy → decision → repair → finalization path.

Run from engine/:

    python -m pip install -e ".[dev]"
    python -m pytest -q

Acceptance is granted only after the complete CI suite passes on the final documentation commit.
