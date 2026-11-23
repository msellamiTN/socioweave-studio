# CORE 09 — Table 4 Protocol Semantic Audit

**Status:** source-grounded specification audit; no protocol compiler is claimed by this document.  
**Primary source:** uploaded paper, Table 4, PDF page 8 (printed page 8).  
**Purpose:** establish a traceable boundary between protocol semantics explicitly printed in Table 4 and engineering details that must not be silently invented.

## 1. Reading rules

Table 4 supplies, for each strategy: source/social principle, agent roster and visibility summary, pseudo-code, terminal decision rule, model-call complexity, and depth. Its notation explicitly defines parallel steps over agents (`||_i`), the agent count `n`, reviewer count `k`, and round count `T`.

This audit transcribes the operational meaning of the printed pseudo-code without adding hidden prompt formats, data schemas, retry rules, tie-breaking rules, or extra calls. The catalogue's call/depth formulas are checked against the table, but the table alone does not define every low-level role assignment and output serialization needed by a production compiler.

## 2. Strategy-by-strategy traceability

| ID | Paper-defined protocol sequence | Agents / visibility stated in Table 4 | Decision rule | Calls | Depth |
|---|---|---|---|---:|---:|
| S1 | Coordinator splits prompt by domain; specialists draft their assigned parts in parallel; coordinator checks the union against the prompt. | One coordinator and n specialists; each specialist sees its part. | authority | n+2 | 3 |
| S12 | n facet experts draft lists from their respective facets in parallel; aggregator merges the lists. | n facet experts and one integrator; each expert sees one facet. | union | n+1 | 2 |
| S2 | n participants generate unfiltered lists in parallel; aggregator merges them. | n participants and one aggregator; nothing is shared during generation. | union | n+1 | 2 |
| S3 | n members draft independently in parallel; each ranks the pooled set of drafts; select the draft with minimum sum of ranks. | n members and facilitator/rule; drafts hidden, then pooled. | rank-sum | 2n | 2 |
| S4 | For each of T rounds, experts draft or revise using their current draft and divergence summary in parallel; facilitator summarises the drafts; stop if stable; return the medoid draft. | n experts and one facilitator; only anonymous summaries are visible. | consensus | T(n+1) | 2T |
| S9 | n decomposer-voters draft independently in parallel; each votes on the pooled subproblem set; retain subproblems whose vote count is strictly greater than n/2. | n decomposer-voters and teller/rule; drafts hidden until the vote. | majority | 2n | 2 |
| S5 | Author drafts; critic critiques the draft; author revises using objections; judge judges the revised draft and objections. | Decomposer, critic, judge; critic sees the draft. | authority | 4 | 4 |
| S6 | First decomposer drafts; second decomposer drafts a counter-plan under the instruction not to assume the first draft; synthesizer merges both. | Two decomposers and synthesizer; second sees the first draft. | synthesis | 3 | 3 |
| S8 | Author drafts; k reviewers critique independently in parallel; editor judges draft and reviews; if decision is revise, author revises once; return the resulting draft. | Author, k reviewers, editor; reviewers isolated. | authority | k+3 | 4 |
| S13 | A drafts; B critiques A's draft; B revises it; A critiques B's revision; return B's revision. | Two agents swapping roles; full visibility. | authority | 4 | 4 |
| S7 | Two decomposers draft independently in parallel; each defends its draft; judge judges the defended cases. | Two decomposers and one judge; judge sees both cases. | authority | 5 | 3 |
| S11 | Two decomposers draft independently in parallel; mediator summarises the two drafts; both revise in parallel using the summary; return D1 when distance(D1,D2) ≤ ε. | Two decomposers and mediator; mediator sees both drafts. | compromise | 5 | 3 |
| S10 | Start with empty D; for up to T rounds, each of n participants sequentially revises the shared D; return D when stable or when moderator reports no objection. | n participants and moderator; everything shared. | consensus | nT+1 | nT+1 |

## 3. Exactness checks against the existing catalogue

The current `catalogue.py` contains the same 13 identifiers in the same table order and records the formulas shown above. At the paper's illustrative configuration n=3, k=3, T=2, the table implies:

| ID | Calls | Depth |
|---|---:|---:|
| S1 | 5 | 3 |
| S12 | 4 | 2 |
| S2 | 4 | 2 |
| S3 | 6 | 2 |
| S4 | 8 | 4 |
| S9 | 6 | 2 |
| S5 | 4 | 4 |
| S6 | 3 | 3 |
| S8 | 6 | 4 |
| S13 | 4 | 4 |
| S7 | 5 | 3 |
| S11 | 5 | 3 |
| S10 | 7 | 7 |

These are table-derived counts, not measured provider usage. The `calls` formulas count model-invoking protocol operations as represented by the paper's accounting; a future implementation must explicitly distinguish model calls from deterministic/local operations without changing the paper's formula.

## 4. Compiler blockers: what Table 4 does not fully specify

The following items are not fully operationalised by the table and must be treated as explicit implementation decisions or resolved from other paper sections before a compiler can claim exact fidelity.

1. **Agent identity and role assignment over rounds.** Table 4 gives roster descriptions, but does not define stable machine identifiers or all per-round role-assignment records.
2. **Visibility relation granularity.** Phrases such as “only anonymous summaries”, “drafts hidden, then pooled”, “reviewers isolated”, and “full visibility” need a precise observer-by-author relation at each stage. Table 4 does not enumerate all pairs.
3. **Anonymous Delphi summaries.** The table states anonymous summaries, but does not define pseudonym rotation, metadata stripping, or whether anonymity covers facilitator-visible source identities.
4. **Nominal-group ranking domain.** The table says each member ranks the set of drafts, but does not specify rank encoding, ties, missing ranks, or deterministic tie-breaking for equal rank sums.
5. **Majority-vote ballot domain.** The strict threshold (> n/2) is explicit; the encoding of ballots, abstentions, invalid votes, and item identity alignment is not.
6. **Delphi stopping and medoid.** “Stable” and `medoid{D_i}` are stated, but the distance function, stability predicate, medoid tie-break, and treatment of incomplete rounds are not defined in Table 4.
7. **Peer-review editor decision.** The branch “if v = revise” is explicit, but the editor's decision rubric and the non-revise terminal outcome are not specified in Table 4.
8. **Adversarial defense payload.** The sequence of draft, defense, and judge is explicit; the defense schema and judge's selection/tie policy are not.
9. **Mediation distance and termination.** The condition `dist(D1,D2) ≤ ε` is explicit; distance, ε calibration, and what happens if the condition is not met after the shown revision round are not specified in Table 4.
10. **Consensus deliberation stability.** Sequential revision and moderator no-objection are explicit; the stability detector, moderator schedule, and behavior at the T limit are not further defined in Table 4.
11. **Action payload schemas.** The table names draft, critique, revise, rank, vote, defend, summarise, merge, check and judge, but does not prescribe a universal machine-readable schema for these outputs.
12. **Failure and retry semantics.** The table does not define provider failure handling, retries, timeouts, malformed output repair, or whether any retry consumes an additional call.

No compiler should silently choose these values and label them as paper-defined.

## 5. Proposed compiler contract (engineering proposal, not paper text)

A future compiler may emit a typed `SocialStrategy` only when supplied with a separate, versioned `ProtocolOperationalization` record that declares all required choices above. The record should contain:

- paper strategy ID and paper/source revision;
- parameter values (n, k, T);
- agent roster and round-specific role assignments;
- per-round visibility relation, with explicit anonymity policy;
- ordered protocol stages and action-to-input dependencies;
- decision-rule parameters, thresholds, distance/stability functions and tie policies;
- model-call accounting policy and retry policy;
- a field-level provenance label: `paper_explicit`, `paper_elsewhere`, or `operational_choice`.

The compiler must reject missing required operational choices rather than fill defaults. It must preserve the paper's call/depth formulas as a separate invariant and compare the compiled schedule's model-call count and sequential depth against them.

## 6. Validation gates before implementation

- [ ] Review all paper sections that elaborate each strategy (not Table 4 alone).
- [ ] Approve an operationalisation record for each strategy with all non-source-defined choices marked.
- [ ] Add a source-to-field traceability test for every compiled field.
- [ ] Add schedule tests for parallel barriers, visibility, anonymity, branching and loops.
- [ ] Verify calls/depth algebraically for variable n, k, T, including boundary cases.
- [ ] Test that missing decision semantics fail closed.
- [ ] Only then expose a strategy as “compiled”; otherwise label it “specification incomplete”.

## 7. Non-claims

This audit is not a proof that the strategies improve decomposition quality. It does not execute any model, produce benchmark measurements, establish the correctness of operational choices, or claim that all Table 4 strategies are ready for deployment.
