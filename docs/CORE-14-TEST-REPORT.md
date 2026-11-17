# Core 14 — Strategy Decision Assembly Test Report

**Status:** PASS — software decision-assembly acceptance.  
**Exact tested code commit:** db3b9f963a82680c3a4ef93283fdc2e9b57b087f  
**CI run:** https://github.com/msellamiTN/socioweave-studio/actions/runs/44195876842  
**Environment:** GitHub Actions, Ubuntu latest runner, CPython 3.11  
**Command:** python -m pytest -q (from engine/)  
**Result:** **257 passed in 0.25s; 0 failed; 0 skipped.**

## Verified scope

- The strategy adapter defaults to the typed strategy decision decoder while retaining explicit decoder injection for controlled extensions.
- S1 coordinator check, S2 brainstorming union and S12 Jigsaw union resolve from typed candidate outputs.
- S3 rank-sum resolves complete rankings against the candidate pool.
- S4 medoid uses each expert's latest candidate after revisions.
- S9 majority resolves voter ballots to exact pooled candidate/subproblem references and then canonical semantic signatures.
- S5 and S7 use explicit judge selections; S8 uses the editor's explicit selection.
- S6 accepts an explicit synthesizer-produced typed candidate.
- S10 uses an explicit moderator selection and records the consensus rule.
- S11 requires an explicit negotiated decomposition and rationale.
- S13 requires an explicit authority selection and rationale; critique is not silently treated as a vote.
- Candidate identifiers are canonicalized to runtime author identity so revisions replace earlier candidates.
- Hypothesis verdicts are merged only when consistent; conflicting verdicts fail closed.
- Candidate edge-support counts use source/target identifiers expected by Algorithm 1 repair.
- Seed serialization uses the typed candidate JSON contract so seeded draft outputs can pass the same parser.

## Initial test correction

The first integration test correctly exposed that union and majority operators intentionally canonicalize local subproblem identifiers (union-* and majority-*). Assertions were corrected to compare semantic decomposition content rather than assume input IDs survive those operators. This is a test expectation correction, not a change to paper semantics.

## Boundaries

- S11/S13 explicit adjudication remains required because the current protocol output trace lacks a typed negotiated decomposition or final authority selection.
- Decision assembly does not prove that the selected candidate, judge rationale or synthesized output is semantically correct.
- S1/S12 partition quality remains caller-supplied.
- V1/V2/V5 structural checks and V3/V4 executor evidence remain separate.
- E1–E9 strategy-effectiveness experiments remain unexecuted.

## Decision

Core 14 passes software decision-assembly acceptance on the exact tested code commit. All 257 integrated tests passed, with no failures or skips.
