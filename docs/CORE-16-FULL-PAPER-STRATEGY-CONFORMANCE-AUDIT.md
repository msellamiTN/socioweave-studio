# CORE 16 — Full-Paper Strategy Conformance Audit (Initial Findings)

**Status:** audit findings recorded; remediation not yet implemented.  
**Audited repository base:** `d3fab0109d564004eef8d87bd2b9d6b3c7f61973`  
**Source:** *Societies of Decomposers: Social and Organisational Strategies for LLM-Based Prompt Decomposition*, Table 4, Sections 5.1–5.4, and Algorithms 1–2.  
**Scope:** targeted source-to-code inspection of all thirteen blueprint branches, adapter defaults, conditional strategy paths and reported software acceptance boundaries. This is not yet a complete formal proof of conformance.

## 1. Executive result

The initial audit correctly identified F16-01 in the adapter path, but its F16-02 through F16-05 conclusions were based too narrowly on the static blueprint and did not account for runtime control flow. The runtime already implements conditional S8 revision, bounded/convergence-aware S11 mediation, S4 Delphi early stopping, and S10 consensus stability stopping. This correction supersedes the initial claims for those four findings.

| Finding | Strategy | Re-audit status | Evidence |
|---|---|---|---|
| F16-01: adapter can silently supply the full prompt to partitioned agents | S1, S12 | **Resolved in CORE 17** | PR #85 requires an explicit prompt-view factory and rejects a restricted agent view equal to the full prompt. Semantic correctness of arbitrary provider output remains an external validation obligation. |
| F16-02: mediation additional rounds unconditional | S11 | **Not reproduced; initial finding withdrawn** | `runtime.py` evaluates agreement / optional ε-distance after each completed revision pair and suppresses later rounds on convergence. Runtime tests cover exact agreement, ε convergence, and continuing to T. |
| F16-03: peer-review revision branch unconditional | S8 | **Not reproduced; initial finding withdrawn** | `runtime.py` parses the editor verdict and skips the revision step on `accept`; tests assert accept (k+2 calls/depth3) and revise (k+3 calls/depth4). The blueprint is a worst-case schedule, not the executed trace. |
| F16-04: Delphi early-stop behavior absent | S4 | **Not reproduced; initial finding withdrawn** | Runtime compares each expert's successive drafts after facilitator completion and stops on exact stability or configured ε-distance. Tests cover exact stability, ε, continuation and missing distance evaluator. |
| F16-05: consensus early-stop behavior absent | S10 | **Partially resolved; refine paper mapping** | Runtime compares the completed shared-draft state across turns and stops on exact stability or configured ε-distance, then runs moderator closure. Tests cover stability, ε and maximum T. Whether moderator no-objection is an independent stop trigger requires a separate source-to-runtime check. |

**Corrected assessment:** the only confirmed F16 implementation defect from the original five is F16-01, now addressed by CORE 17. The other four were false positives caused by treating a maximum static blueprint as the actual executed trace. This audit still does not prove complete conformance across all strategy semantics.

## 2. Re-audit evidence and source-to-runtime interpretation

### F16-01 — Partitioned strategies can receive an unpartitioned prompt (confirmed; now fixed)

The original implementation observation remains valid for the adapter on the audited base. CORE 17 now:
- requires an explicit `prompt_view_factory` for S1 and S12;
- removes the full-prompt fallback for those strategies;
- rejects specialist/expert views exactly equal to the complete prompt;
- tests missing provider and full-prompt equality rejection.

**Residual limitation:** string inequality is only a fail-closed guard. It does not prove that a supplied S1 view is exactly the coordinator-assigned domain partition or that an S12 view is a valid paper-defined facet. The provider must still be checked against the frozen extraction and the source's facet construction rules.

### F16-02 — S11 mediation (withdrawn)

The protocol blueprint intentionally contains up to T mediation rounds. The runtime is the execution controller: after each complete mediator-summary plus two-revision round, it compares the two revised candidates. Exact equality stops; when a distance function and ε are explicitly supplied, distance ≤ ε stops. Otherwise the protocol continues up to T.

Existing regression tests in `engine/tests/test_runtime.py` cover:
- ε convergence after the first round (five calls, three executed stages);
- exact round-trace behavior and stage barriers;
- continued execution through T when parties remain different;
- required distance callback when ε is configured.

Thus a T-round blueprint is a maximum schedule, not evidence that every round executes unconditionally. Realized calls must be read from `StrategyRun`, not inferred from the blueprint count.

### F16-03 — S8 peer-review branch (withdrawn)

The blueprint represents the worst-case revise path. At execution, the runtime parses the editor JSON verdict and skips the author revision on `accept`. Existing tests assert both branches:
- accept: k+2 calls and depth 3;
- revise: k+3 calls and depth 4.

Malformed or missing editor verdicts fail closed. The catalogue's k+3 is correctly interpreted as the maximum/revise-path budget.

### F16-04 — S4 Delphi (withdrawn)

After each facilitator summary, the runtime compares every expert's current draft with that same expert's previous-round draft. It stops if all are exactly unchanged, or if the maximum supplied per-expert distance is at most ε. Otherwise it continues up to T. Tests cover exact stability, ε stopping, non-convergence through T, and rejection of ε without a distance callback.

### F16-05 — S10 consensus (partially resolved)

The runtime executes sequential participant turns and compares the final shared-draft state of adjacent completed rounds. It stops on exact equality or configured ε-distance and retains moderator closure at the actual stop round. Tests cover exact stability, ε stopping, and continuation through T.

**Remaining source question:** the paper also describes moderator no-objection as a stopping condition. The current runtime's stop controller uses shared-draft stability; the moderator is invoked for closure after that decision. Do not claim that an independently returned moderator no-objection can terminate an otherwise changing shared draft until that behavior is implemented and tested (if required by the paper's exact semantics).

## 3. Updated remediation order

1. Keep CORE 17's S1/S12 fail-closed adapter change; add source-aware validation of generated domain partitions and Jigsaw facets.
2. Reconcile S10's moderator no-objection wording with the precise source section and decide whether it is an independent stop condition.
3. Audit the runtime's actual S1/S12 partition and facet data path end-to-end, including prompt-view and input-content channels.
4. Continue a full source-to-runtime audit for all thirteen strategies; static blueprint conformance alone is insufficient.
5. Run the full suite on one exact commit and report static maximum schedule, executed trace, model calls and depth separately.
6. Keep scientific evaluation and empirical effectiveness as separate gates.

## 4. Existing evidence and its limits

- CORE 12 reports 230 tests passed, 0 failed, 0 skipped on code commit `3f846916f5074440961734b51ae47cb48b5d4f76`.
- CORE 14 reports 257 tests passed, 0 failed, 0 skipped on code commit `db3b9f963a82680c3a4ef93283fdc2e9b57b087f`.
- CORE 15 reports 259 tests passed, 0 failed, 0 skipped on code commit `5e3b4df53bb166f855cee648912d8689d30819e4`.

These reports establish historical software test results on their stated commits. They do not establish that the current main commit was tested end-to-end, that all branches match paper semantics, or that any strategy improves decomposition quality. No E1–E9 scientific effectiveness result is claimed.

## 5. Remediation order

1. Fix F16-01 first: partition/facet semantics are foundational and currently bypassable through the default adapter path.
2. Fix F16-03: make S8's editor decision a real control-flow branch.
3. Fix F16-02: separate S11's base procedure from conditional additional negotiation rounds.
4. Implement structured early-stop controllers for S4 and S10.
5. Re-run all strategy protocol, adapter, decision, runtime and orchestration tests on one exact commit.
6. Reconcile the resulting traces against the paper's call/depth formulas and branch conditions.
7. Only then update the conformance status. Scientific evaluation remains a separate gate.

## 6. Non-claims

This audit does not claim that all thirteen strategies are fully paper-conformant, that the listed findings are the only possible defects, or that software tests establish strategy effectiveness. It records concrete, source-traceable discrepancies found during the initial end-to-end review.
