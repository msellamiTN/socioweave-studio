# Core 12 — Concrete Strategy Adapter Layer

**Status:** PASS — software protocol-adapter acceptance. See CORE-12-TEST-REPORT.md.  
**Source basis:** Paper Table 3, Table 4, Sections 5.1–5.4, and Algorithm 1 (pages 7–16).

## 1. Scope

Core 12 translates all thirteen established strategies into concrete SocialStrategy blueprints and connects those blueprints to the existing visibility-aware runtime. The five unexplored matrix cells C1–C5 are not accepted by this factory.

Files:
- engine/sociodec/strategy_protocols.py — protocol blueprints.
- engine/sociodec/strategy_adapter.py — runtime bridge and typed decision decoder contract.
- engine/sociodec/runtime.py — stage input visibility enforcement and anonymous aggregate histories.
- engine/tests/test_strategy_protocols.py
- engine/tests/test_strategy_adapter.py

## 2. Table 4 protocol realization

| Strategy | Protocol realization | Decision contract |
|---|---|---|
| S1 Division of labour | coordinator split → n domain-restricted specialists → coordinator check | authority |
| S12 Jigsaw | n facet-restricted experts → integrator | union |
| S2 Brainstorming | n isolated unfiltered drafts → aggregator | union |
| S3 Nominal group | n independent drafts → n rankings of pooled drafts | rank-sum |
| S4 Delphi | anonymous expert drafts/revisions and facilitator summaries over T rounds | consensus medoid |
| S9 Majority vote | independent drafts → ballots over pooled sub-problems | strict majority |
| S5 Devil's advocate | author draft → critic objections → author revision → judge | authority |
| S6 Dialectical inquiry | first plan → counter-plan informed by first → synthesizer | synthesis |
| S8 Peer review | author draft → k isolated reviews → editor → author revision | authority |
| S13 Role reversal | A draft → B critique → B repair → A critique | authority |
| S7 Adversarial procedure | two independent drafts → two defences → neutral judge | authority |
| S11 Mediation | two drafts → mediator summary → two parallel revisions | compromise |
| S10 Consensus deliberation | shared sequential amendments → moderator judgement | consensus |

Protocol call counts are checked against the catalogue's Table 4 formulae. S11 is the fixed five-call, three-stage base procedure; the paper discusses an additional round if revisions remain different, which is not silently folded into the base Table 4 cost.

## 3. Visibility and partitioning

- Every agent sees its own outputs.
- S1 and S12 require explicit prompt views. The factory refuses to invent domain or facet partitions.
- S2 participants generate independently; the aggregator can see their outputs in a separate aggregation round.
- S3 and S9 preserve independent first drafts and reveal the pooled material in a separate ranking/voting round.
- S4 experts receive anonymous facilitator summaries; the facilitator can inspect the drafts. Both visible history and aggregate input text anonymise author labels.
- S7 parties do not see the opposing party's draft/defence; the judge sees both cases in the decision phase.
- S8 reviewers see the author draft but not one another's reviews; the editor sees all reviews and the author receives the editor-approved feedback before revision.
- Runtime direct-step and aggregate-history inputs are now checked against the declared visibility relation. A protocol cannot use an input reference to bypass V. Phase transitions are represented as separate protocol rounds where the paper changes access after pooling or review.

## 4. Runtime bridge and decision boundary

ConcreteStrategyAdapter implements the Core 11 callable contract for one atomic strategy. It:
1. builds the strategy blueprint;
2. supplies prompt views, agent model identities and role contexts;
3. places permitted initial/chain seeds without seeding partitioned strategies;
4. runs the existing runtime with extraction hypotheses;
5. checks actual runtime calls against the supplied allowance;
6. calls an injected typed decoder; and
7. checks that the decoder's DecisionResult rule matches the paper strategy.

The decoder is deliberately injected. It must parse structured outputs into typed Candidate/Decomposition objects and invoke the existing pure decision operators. The adapter never treats arbitrary model text as a valid decomposition.

C8, Jigsaw→Devil's Advocate and the Algorithm 3 full pipeline are compositions, not atomic strategies. They require an explicit composite_executor; the adapter refuses to pretend that a composition is a single atomic protocol.

## 5. Explicit limitations

- S4's blueprint expands the maximum T rounds. Early termination on per-author stability requires a candidate-aware stopping controller and is not inferred from arbitrary text.
- S10's blueprint expands the maximum nT participant turns and moderator judgement. Early termination on a moderator no-objection signal requires a structured stopping controller.
- S11 implements the base Table 4 five-call round. Additional negotiation rounds need a bounded iterative controller.
- Structured model-output decoding and typed decision evidence are injected, not yet supplied by a concrete provider-specific JSON schema implementation.
- S1/S12 prompt-view construction is caller-supplied; the factory does not silently infer semantic partitions.
- S5/S8 seed choice is supplied by a seed selector; the adapter does not guess which initial draft has fewer failures.
- The adapter checks call accounting, not semantic correctness or provider determinism.

## 6. Acceptance

Run from engine/:

    python -m pip install -e ".[dev]"
    python -m pytest -q

Acceptance requires the full integrated suite, exact-commit CI and zero skipped tests. Software protocol conformance does not establish the strategies' comparative effectiveness; the paper's experimental campaign remains a separate scientific gate.
