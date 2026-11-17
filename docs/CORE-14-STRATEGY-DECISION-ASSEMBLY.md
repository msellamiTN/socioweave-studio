# Core 14 — Strategy Decision Assembly

**Status:** PASS — software decision-assembly acceptance. See CORE-14-TEST-REPORT.md.  
**Scientific basis:** paper Definitions 9–10, Table 4, Sections 5–7 and Algorithms 1–3. The code applies the paper's decision rules to typed protocol evidence; it does not infer missing adjudications.

## Scope

- \`engine/sociodec/strategy_decoding.py\` resolves typed protocol outputs into strategy-specific decisions.
- \`engine/sociodec/strategy_adapter.py\` now uses this decoder by default; callers may still inject a custom decoder.
- \`engine/sociodec/protocol_decoding.py\` canonicalizes candidate identifiers to the runtime author identity and decodes typed candidate evidence.
- \`engine/tests/test_strategy_decoding.py\` exercises all supported atomic strategy decision paths and explicit missing-evidence failures.

## Decision mapping

| Strategy | Decision assembly |
|---|---|
| S1 Division of Labour | Coordinator's checked decomposition, represented as an authority result over the single checked candidate |
| S12 Jigsaw | Union of expert facet decompositions |
| S2 Brainstorming | Union of independent participant decompositions |
| S3 Nominal Group | Rank-sum over complete candidate permutations |
| S4 Delphi | Consensus medoid over each expert's latest draft |
| S9 Majority Vote | Strict-majority subproblem ballots resolved against the pooled candidate set |
| S5 Devil's Advocate | Judge's explicit selection among the author's latest candidate |
| S6 Dialectical Inquiry | Explicit synthesizer candidate accepted through the synthesis operator |
| S8 Peer Review | Editor's explicit selection among the author's latest candidate |
| S13 Role Reversal | Authority selection requires explicit adjudication; the final critique alone is not treated as a vote |
| S7 Adversarial Procedure | Neutral judge's explicit selection between party candidates |
| S11 Mediation | Mediator's negotiated decomposition is required as explicit adjudication; two revised proposals are not silently called a compromise |
| S10 Consensus Deliberation | Moderator's explicit selection among the latest participant drafts, recorded as \`consensus\` |

## Evidence and invariants

- Candidate identity is canonicalized to the runtime author, so revisions replace that author's previous candidate instead of creating accidental extra voters.
- Ranking permutations are checked by the rank-sum operator against the current candidate pool.
- Ballots must reference an existing candidate and subproblem; subproblem references are converted to canonical semantic signatures before majority aggregation.
- Hypothesis verdicts must refer to extracted hypotheses; conflicting verdicts from different protocol outputs fail closed.
- Candidate edge-support counts are returned as evidence for downstream repair.
- No candidate is selected from arbitrary prose or by lexical preference unless the underlying operator explicitly specifies an engineering tie-break.

## Explicit adjudication boundary

The current paper protocol trace for S11 contains two party drafts, a mediator summary and two revisions, but no typed mediator-produced final decomposition. The S13 trace ends with an agent-A critique, not a typed authority selection. Therefore \`DecisionAdjudication\` is required for those two cases:
- S11: negotiated decomposition and rationale.
- S13: selected candidate identifier and rationale.

This is intentional fail-closed behavior. A critique or summary is not silently upgraded into a decision. No additional model call is added to the paper's Table 4 call budget.

## Limitations

- This core assembles decisions; it does not prove semantic quality of a judge's rationale, candidate, or synthesis.
- Structural V1/V2/V5 validation and V3/V4 execution evidence remain separate.
- The majority operator follows strict \`> n/2\` subproblem support; it can remove rare items.
- S10 is represented by the explicit moderator selection output; a separate adaptive early-stop controller remains future work.
- S11/S13 need explicit adjudication evidence until the paper's protocol output contract specifies an unambiguous final decision message.

## Acceptance

Run from \`engine/\`:

    python -m pip install -e ".[dev]"
    python -m pytest -q

Acceptance requires all integrated tests, zero skips, exact-commit CI, and a test report.
