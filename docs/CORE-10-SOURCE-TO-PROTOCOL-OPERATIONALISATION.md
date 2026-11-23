# CORE 10 — Source-to-Protocol Operationalisation Audit

**Status:** source-grounded specification refinement; no new executable strategy compiler is claimed.  
**Primary source:** uploaded *Societies of Decomposers: Social and Organisational Strategies for LLM-Based Multi-Agent Prompt Decomposition*, especially Sections 5.1–6.2 and Algorithm 1 (PDF pages 7–17), read together with Table 4 (PDF page 8).  
**Depends on:** CORE 09, Table 4 Protocol Semantic Audit.

## 1. Purpose and correction to CORE 09

CORE 09 intentionally audited Table 4 in isolation and listed implementation blockers. The full paper resolves some of those blockers in Sections 5–6. Those fields must be attributed to **paper_elsewhere**, not treated as unspecified or silently replaced by engineering defaults.

This document refines the source-to-field map. It does not claim that every strategy is now directly compilable: the paper still leaves some serialization, provider-failure, and implementation details open. Where the paper provides a conceptual rule but not a machine representation, the distinction is preserved.

Provenance labels used here:

- `paper_explicit`: stated directly in Table 4 or its notation.
- `paper_elsewhere`: specified in another section, figure, example, or Algorithm 1.
- `operational_choice`: a concrete implementation representation or policy not fixed by the paper.

## 2. Cross-strategy execution semantics from Section 6.1 / Algorithm 1

| Field | Source-grounded semantics | Provenance | Remaining implementation boundary |
|---|---|---|---|
| Input extraction | Unless caller supplies them, extract requirements \hat R, hypotheses \hat H, and entities \hat N using q calls. | paper_elsewhere | Exact extractor model/prompt and q configuration are deployment parameters. |
| Agent context | Acting agent receives its prompt view, hypotheses, and only history entries whose author is visible to it in the current round. | paper_elsewhere | Concrete context serialization is operational. |
| Prompt view | Whole prompt by default; partition/facet view for strategies that split the prompt. | paper_elsewhere | Strategy-specific view mapping must be encoded and tested. |
| Self-visibility | Every agent sees its own outputs: (a,a) belongs to V_t for every round. | paper_elsewhere | Direct invariant for compiler/runtime. |
| Anonymity flag η | When enabled, author names are removed from context. | paper_elsewhere | Whether additional metadata is stripped is not specified; do not claim cryptographic anonymity. |
| Candidate metadata | Every candidate carries composition map κ and hypothesis verdicts v. | paper_elsewhere | Typed schema/serialization is an operational representation of the paper's objects. |
| Seeds | A seed is a same-prompt draft owned by one agent; it is adopted as that agent's first-round draft and skips the corresponding call. Other agents see it only if visibility permits. Agents with part/facet views ignore seeds. | paper_elsewhere | Seed validation, storage and exact identity representation are operational. |
| Stability (general loop) | From round 2, stable when each author’s current candidate is within ε of that same author's previous-round candidate. Stop on stability or after L steps. | paper_elsewhere | Distance function and ε calibration need a declared implementation; paper gives the criterion but not one universal distance algorithm. |
| Latest candidate | Only the latest candidate per author enters the decision rule; earlier revisions are superseded. For shared sequential amendment, keep the latest version. | paper_elsewhere | Candidate lineage representation is operational. |
| No candidate | If no candidate is produced, return failure. | paper_elsewhere | Failure object schema is operational. |
| Final check | Check V1 uncovered requirements, V2 cycles, V5 deliverable without sub-problem or dead-end sub-problem, and missing hypothesis verdicts. | paper_elsewhere | Exact validators/thresholds must follow the paper's formal definitions elsewhere in the manuscript. |
| Cycle repair | Break cycles without a model call by repeatedly removing the cycle edge supported by the fewest candidates. | paper_elsewhere | Tie handling when support counts tie is not specified. |
| Other repair | Send remaining non-cycle failures in one call to the decision-rule agent, or to D⋆'s author if the rule has no agent; attempt once, re-check, then return remaining failures F. | paper_elsewhere | Repair output schema and tie/error handling are operational. |
| Cost accounting | Table 4 strategy calls exclude common extraction q and optional repair call; cycle breaking is local/no-call. | paper_elsewhere | Runtime must report base protocol calls separately from extraction, repair, retries and non-model work. |
| Termination bound | Algorithm 1 states at most q + L + 1 model calls, with L the Table 4 call count for the configured maximum rounds; repair is at most one call. | paper_elsewhere | Retry policies are not part of this bound unless explicitly excluded/accounted separately. |

**Important accounting note:** the paper's Table 4 formulas are protocol-call formulas. An implementation must not silently fold extraction, repair, retries, failed provider attempts, or local deterministic work into that number. Report each category separately and preserve the paper-defined base count.

## 3. Strategy-specific details recovered beyond Table 4

| Strategy | Additional paper-defined semantics | Source | Open operational choices |
|---|---|---|---|
| S1 Division of labour | Coordinator partitions by domain; each specialist sees only its assigned part; coordinator checks union against prompt. The paper explicitly warns that a wrong coordinator split cannot be repaired by specialists who never see the whole prompt. | Section 5.1.1, PDF pp. 8–9 | Domain taxonomy, split serialization, and coverage-check rubric. |
| S12 Jigsaw | Facets derive from extracted requirements: requirement facets group requirement types; actor facet contains entities plus requirements mentioning each entity. Integrator unions partial lists, deduplicates, and adds cross-facet dependencies. Empty facets are dropped and cost no call. | Section 5.1.2, PDF p. 9 | Exact requirement-type partition T_i, entity mention extraction representation, duplicate equivalence and dependency payload schema. Existing S12 implementation must be checked against these statements. |
| S2 Brainstorming | Participants return unfiltered lists without dependencies; aggregator merges duplicates and groups items. Higher temperature and distinct personas are suggested to increase variety without extra calls. | Section 5.2.1, PDF p. 9 | Temperature, persona policy, duplicate equivalence and grouping schema. The paper does not mandate numeric temperature values. |
| S3 Nominal group | Drafts are pooled without author names; every member ranks every draft; return draft with minimum sum of ranks. Rank sum is a deterministic rule and costs no model call. | Section 5.2.2, PDF p. 10 | Rank encoding, tie resolution and malformed/missing rankings. |
| S4 Delphi | Authors work separately; facilitator summarizes divergences without naming authors; each agent revises in light of summary. Stop when every draft satisfies max_i dist(D_i^t,D_i^{t-1}) ≤ ε or t=T. | Sections 5.2.3, PDF pp. 10–11 | Distance implementation and ε calibration; facilitator summary serialization. |
| S9 Majority vote | Agents draft independently; vote separately on each item in pooled sub-problem list; ballot is b_i: union_j S_j → {0,1}; retain items with strictly more than n/2 votes; teller is a rule. | Section 5.2.4, PDF p. 11 | Stable item identity/alignment across drafts and invalid ballot handling. Strict threshold is paper-defined. |
| S5 Devil’s advocate | Critic receives draft and prompt; returns typed objections limited to missing sub-problem, redundant sub-problem, hidden dependency; author revises; judge checks objections were answered and approves. | Section 5.3.1, PDF p. 11 | Typed objection fields, approval rubric, judge rejection/repair behavior. |
| S6 Dialectical inquiry | Second decomposer reads D1, identifies its main assumption, inverts it, and decomposes P again; synthesizer compares both and builds a third decomposition. | Section 5.3.2 and Fig. 5b, PDF p. 12 | How assumption extraction/inversion is represented and synthesis schema. |
| S8 Peer review | Reviewers assess the same draft in isolated contexts against a rubric; editor reads reports and accepts or requests revision; one revision is in Table 4; each additional revision round adds k+2 calls. | Section 5.3.3, PDF p. 13 | Rubric content, editor arbitration rule, acceptance output schema. |
| S13 Role reversal | A drafts; B attacks; roles swap; B repairs and defends D1; A attacks the repair. Round-specific roles are explicitly given. Last attack is not followed by repair unless another round is added; optional judge adds one call. | Section 5.3.4 and Fig. 5d, PDF p. 13 | Attack payload schema and whether optional extra round/judge is enabled (declare as variant, not default). |
| S7 Adversarial procedure | Two decomposers independently draft and each writes a short defence; neutral judge who wrote nothing selects one draft with a rubric. Judge should be from another model family per the paper's stated rationale. | Section 5.4.1, PDF p. 14 | Defence schema, rubric weights, tie policy and model-family identity policy. |
| S11 Mediation | Mediator identifies agreements/disagreements, asks each agent what the other's choice would cost, and guides both to a joint decomposition. Stop when drafts agree / dist(D1,D2)≤ε / after T rounds. | Section 5.4.2, PDF pp. 14–15 | Distance/ε, exact turn schedule and operational representation of “agree”; Table 4's single revision round is the n=2, one-round cost instance. |
| S10 Consensus deliberation | Shared decomposition amended sequentially by participants; moderator gives floor and stops when no participant objects. General description adds stop when a full turn leaves shared draft stable, dist(D_t,D_{t−1})≤ε, or t=T. Every agent sees every turn. | Section 5.4.3, PDF p. 15 | Speaker ordering policy, moderator no-objection representation and distance function. |

## 4. Reconciliation: what is now resolved vs still open

### Resolved by the full paper (not by Table 4 alone)

- Generic context construction, visibility filtering, self-visibility and anonymity flag.
- Seed semantics and skipped first-draft call.
- General stability condition, maximum loop length and latest-candidate selection.
- Final validation categories, cycle-breaking rule and one-shot repair.
- Exclusion of common extraction and optional repair from Table 4 call counts.
- Jigsaw facet construction and empty-facet dropping.
- Brainstorming's no-filter/no-dependency generation and merge stage.
- Nominal-group anonymity and minimum rank-sum rule.
- Delphi anonymous divergence summaries and stopping criterion.
- Majority-vote binary item ballots and strict > n/2 threshold.
- Devil's advocate objection categories and judge's objection-response check.
- Dialectical assumption inversion.
- Peer-review isolated rubric-based reviews and incremental revision cost.
- Role reversal round-specific roles and optional extra judge.
- Adversarial short defences and neutral selection.
- Mediation agreement/disagreement work and maximum-round stop.
- Consensus full-turn stability and sequential shared context.

### Still not fully specified as machine-executable semantics

1. A universal distance function for decomposition structures and its normalization.
2. Numeric ε defaults: the paper gives a default ε=0.1 for selector Table 8, but that must not be assumed automatically for every protocol distance unless explicitly established.
3. Tie policies: rank-sum ties, medoid ties, cycle-edge support ties, judge selection ties.
4. Machine-readable schemas for candidates, composition maps κ, verdicts, typed objections, defences, ballots, reviews, mediator summaries and editor decisions.
5. Duplicate equivalence and grouping algorithm for union-based strategies.
6. Exact domain partitioning for S1 and requirement-type partition T_i for S12.
7. Provider failure, timeout, retry and malformed-output repair semantics.
8. Stable item identity when majority voters evaluate the pooled set.
9. Exact model-family enforcement and evidence for claims of independence.
10. Whether any strategy-specific stop rule shortens the Table 4 nominal maximum and how its realized calls are reported.

## 5. Compiler and runtime design consequences

A future compiler should not encode every strategy as a flat list of calls. The source requires at least:

- typed candidate lineage and author identity;
- round-scoped role assignment;
- stage barriers and per-agent visibility;
- explicit prompt views (whole prompt, domain part, requirement facet, actor facet);
- strategy-specific branch/stop conditions;
- deterministic local decision operators where the paper assigns a rule rather than an agent;
- a separate final validation/repair phase;
- provenance metadata on every compiled field.

Suggested provenance enum:

`paper_explicit | paper_elsewhere | operational_choice`

Suggested readiness states:

- `SOURCE_SPECIFIED`: the semantic rule is present in the paper.
- `OPERATIONALIZED`: an implementation representation has been explicitly selected and documented.
- `VALIDATED`: tests establish conformance to that operationalisation.
- `EXPERIMENTALLY_EVALUATED`: the strategy has been run under the paper's experimental protocol.
- `REPRODUCED`: the relevant reported paper result has been independently reproduced.

These states are deliberately not interchangeable. Passing a compiler test does not establish empirical effectiveness or paper reproduction.

## 6. Required tests before claiming compiler fidelity

1. **Traceability:** every compiled field maps to a page/section/algorithm line and a provenance label.
2. **Algorithm 1 invariants:** self-visibility, visibility-filtered history, η name removal, seed ownership/skip, latest candidate, stop at L, and one-shot repair.
3. **Cost separation:** base Table 4 calls vs extraction q vs repair vs retries vs local operations.
4. **Strategy semantics:** S12 facets/empty drop; S2 no dependencies; S3 min rank sum; S4 Delphi stop; S9 strict majority; S5 typed objection classes; S6 assumption inversion; S8 independent reviewers; S13 role swap; S7 neutral selection; S11 agreement/ε/T; S10 full-turn stability.
5. **Fail-closed behavior:** missing operational choices must prevent a strategy from being marked operationalized.
6. **No overclaim:** test status must never imply experiment completion or scientific reproduction.

## 7. Recommended implementation order

1. Reconcile the existing S12 Jigsaw factory against Section 5.1.2 and Algorithm 1; retain its existing tests and close any semantic gaps.
2. Implement the shared provenance-aware execution specification and Algorithm 1 invariants independently of provider execution.
3. Operationalize S2 as the first simple aggregation protocol, with duplicate/grouping choices explicitly declared.
4. Add S1 only after a domain-split representation is agreed.
5. Implement the more complex decision and iterative protocols only after their missing distance, tie, rubric and identity policies are declared.

## 8. Non-claims

This audit does not implement the compiler, prove the paper's propositions, validate the operational choices, run any benchmark, or establish that a strategy improves quality. It is a source interpretation and engineering specification artifact. The paper's worked examples are illustrative, not experimental measurements.
