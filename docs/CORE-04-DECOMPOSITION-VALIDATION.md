# Core 04 — Decomposition Validity Checks

**Status:** Implementation and full-suite acceptance pending.  
**Scientific source:** Definition 6 and the final check/repair phase of Algorithm 1.

## 1. Paper contract

Definition 6 defines validity of D for prompt P and executor M by five conditions:

- **V1 Coverage:** cov(D) = R(P).
- **V2 Acyclicity:** (S,E) is a directed acyclic graph.
- **V3 Solvability:** M solves each subproblem given the answers of its predecessors.
- **V4 Faithfulness:** the composed answer satisfies the hard constraints C_h.
- **V5 Composition:** κ(o) is non-empty for every deliverable o, and every sink of (S,E) belongs to some κ(o).

The paper explicitly distinguishes programmatically checkable V1, V2 and V5 from V3 and V4, which can only be observed by execution. Algorithm 1 additionally checks that every extracted implicit-requirement hypothesis has a confirmed/rejected verdict.

## 2. Validation design

`validate_decomposition` returns a structured `ValidationReport` with independent results for V1–V5 and hypothesis-verdict completeness.

- V1 compares the decomposition's union coverage with the explicit requirement set plus hypotheses whose verdict is confirmed. Rejected hypotheses are excluded; a missing verdict is a failure.
- V2 finds a directed cycle, if one exists, and reports its node sequence.
- V5 reports every deliverable with no contributors and every sink subproblem not referenced by any deliverable composition.
- V3 and V4 are always `NOT_EVALUATED` in this structural validator. They must never be reported as passing without executor evidence.
- Findings have stable machine-readable codes and affected subjects.

The caller supplies the explicit requirement universe R(P). A confirmed hypothesis is converted to a spanless Requirement with the same statement, type, domain and entity names and joins the effective coverage universe, as specified by the paper.

## 3. Scope boundary

This Core does not perform cycle repair, requirement repair, model calls, executor execution, answer composition or faithfulness adjudication. Algorithm 1 describes cycle removal and one-call repair after checks; those are orchestration/repair behavior and must be implemented separately from this pure validator.

A structurally valid report is not a claim that the decomposition is solvable or that the final answer is faithful.

## 4. Acceptance

From `engine/`:

    python -m pip install -e '.[dev]'
    python -m pytest -q

Acceptance requires the full integrated test suite, including negative and regression tests, to pass on the exact final commit. A test report must record the environment, command, count and limitations.
