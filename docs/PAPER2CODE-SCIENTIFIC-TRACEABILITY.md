# Paper2Code Scientific Traceability Baseline

**Source of truth:** *Societies of Decomposers: Social and Organisational Strategies for LLM-Based Multi-Agent Prompt Decomposition*, uploaded source PDF, Sections 1–9 and Tables 1–16.

**Repository baseline:** `main` at `868644416d21aa9c0672ca42071d9693f9bbcc35` (verified 2026-11-19).
**Scope:** This document distinguishes source requirements, existing implementation evidence, and scientific evidence. A passing unit test is software evidence, not experimental validation.

## 1. Acceptance rule

A paper contribution is complete only when:
1. its source definition/algorithm is transcribed faithfully;
2. its implementation is mapped to concrete modules and functions;
3. independent tests exercise the stated invariants and edge cases;
4. experimental claims have real, reproducible observations where the paper requires them;
5. limitations and deviations are recorded.

Statuses used here:
- **Implemented (reported):** repository contains implementation; requires current-head verification.
- **Software-tested (reported):** prior CI/test evidence exists.
- **Partial:** only part of the source requirement is represented.
- **Missing / unverified:** no adequate evidence is currently established.
- **Scientific validation pending:** requires real benchmark/provider execution or human annotation.

## 2. Source-to-code traceability

| Paper source | Required contribution | Existing repository evidence | Status / next verification |
|---|---|---|---|
| §1, RQ1–RQ4; contributions | Motivation, four research questions, five contribution groups | README and project docs describe the implementation | Partial: create claim-level traceability; ensure every contribution is represented |
| §3.1, Fig. 1 | Smart-administration running prompt; nine reference sub-problems; thirteen dependencies; implicit s3 | Prompt/decomposition models and example documentation exist | Partial: encode the exact source example and reference graph as a versioned fixture, not a hand-waved example |
| Definition 1 | Prompt P=(x,ι), interpretation (g,C,I,O), hard/soft constraints, inputs, deliverables, Int(x), ambiguity/conflict | `models/prompt.py`, prompt tests | Verify exact field semantics, ambiguity/conflict conditions and interpretation boundary |
| Definition 2 | Atomic typed requirements, domain labels, source spans; entities; explicit and implicit requirements | `extraction.py`, prompt/requirement models | Partial: verify typed source-span coverage, entity separation and implicit requirement semantics |
| Definition 3, Eq. (1) | q extractors; dedup; split R-hat vs H-hat; ambiguity/conflict flags; hypothesis verdicts | `extraction.py`, extraction tests | Scientific validation pending: matcher/dedup accuracy, recall against human requirements, hypothesis verdict audit |
| Definition 4 | Sub-problem tuple (question, inputs, outputs, local constraints) | `models/decomposition.py` | Verify all fields and schema/serialization against source |
| Definition 5 | Decomposition D=(S,E,κ) with sub-problems, dependencies and composition map | `models/decomposition.py` | Verify dependency direction and deliverable composition semantics |
| Definition 6 | V1 coverage; V2 acyclicity; V3 solvability; V4 faithfulness; V5 composition correctness | `validation.py` | Partial by design: V1/V2/V5 structural checks; V3/V4 require execution and must remain NOT_EVALUATED until then |
| Definition 7, Eq. (2) | Equivalence matcher; Jaccard distance over sub-problems and edges; ε=0.1 default | `metrics.py`, `decisions.py` | Formula and matcher audit required; test empty sets, canonicalization, edge equivalence, thresholds |
| Definition 8; Table 9 | Coverage, redundancy, coupling, depth, utility | `metrics.py`, `evaluation.py` | Formula audit + dataset-specific applicability; utility requires fixed executor outcome |
| Definition 9 | Agent a=(m,c,μ) | strategy/provider model layer | Verify model, context and memory semantics and whether actual provider invocation preserves them |
| Definition 10 | Strategy σ=(A,R,α,V,π,ω,η) | `models/strategy.py`, `catalogue.py`, `strategy_protocols.py` | Partial: check all components and anonymity/visibility semantics against Table 4 |
| §4; Table 3 | Human mechanism, human precondition, agent reconstruction and weakened/lost property | catalogue/docs | Partial: retain source preconditions and explicit analogy limitations in strategy specs |
| §5.1–5.4; Table 4 | Thirteen protocols, agent roles, visibility, pseudo-code, decision rules, calls and depth | `catalogue.py`, `strategy_protocols.py`, `runtime.py`; PR #17 adds profiles | Partial: PR #17 conformance profiles are on an unmerged branch; independently compare actual prompts/provider traces with all Table 4 protocols |
| §5.5; Table 5 | Production-mode × decision-rule design matrix; five unexplored candidate strategies | Existing catalogue; PR #17 keeps C1–C5 separate | Partial: verify all five candidate definitions and admissibility, not merely catalogue identifiers |
| §6; Algorithm 1 | Generic bounded strategy execution, stop checks, repair/check, failure set | `runtime.py`, `execution.py`, `repair.py`, `validation.py` | Software verification and proof-to-code audit required; include termination, bounds and fail-closed behavior |
| §6; Propositions 1–5 | Termination; union coverage; selection bounded by best candidate; majority loses rare items; correlated-agent majority behaviour | mathematical docs/tests may exist | Missing claim-level proof/test map: transcribe assumptions, check proof validity, build executable counterexamples/property tests |
| §7.1–7.2; Definition 11 | Typed composition of phases; T1–T3 admissibility conditions and incompatibilities | `strategy_composition.py` and composition tests | Partial: validate every Table 10 composition and invalid composition, including phase state/independence |
| §7.2; Definition 12 | Sequential chaining σ1 ▷ σ2; first strategy completes; only one eligible author receives seed | `strategy_composition.py`; PR #17 regression | Implemented in branch evidence; verify full paper semantics and merge only after review |
| §7.3; Table 7–8 | Prompt features, diagnostic checks, ordered decision list, escalation and budget handling | `selector.py`, `orchestrator.py` | Partial: reproduce exact ordered rules and selector overhead; test false negatives, false positives and unseen features |
| §7; Algorithm 2 | Adaptive selector algorithm | selector/orchestrator | Algorithm-to-code proof and live execution evidence missing |
| §7; Table 11; Algorithm 3 | Combinations C1–C8; C1 four-phase pipeline, judge independence, bounded repair/failure recording | `strategy_composition.py`, orchestration/runtime | Partial: C1–C8 need exact source-to-runtime conformance; C1 must enforce independent judge family and exact call bounds |
| §8.1; Table 12 | Five datasets and dataset-specific references/metric applicability | `datasets.py` registry and JSONL loader | Incomplete: dataset registry is not a complete benchmark pack; reference structures and licensing/provenance need validation |
| §8.1; Table 13 | Three agent model families; fixed executor; n=3,k=3,T≤2; temperatures; output limits/schema; q=3 extraction; five seeds; 100 prompts/public benchmark; 60 smart-administration; budget matching; human ratings; Wilcoxon/Holm | `experiments.py`, `campaign.py`, provider runtime and Colab template | Not experimentally established: pin exact model versions/access dates, data snapshots, config, prompts, seeds and provider traces |
| §8.2; Table 14 | E1–E9 experimental questions, factors, measures and expectations | generic experiment/evaluation infrastructure | Not reproduced: dedicated experiment implementations, real runs, raw results and analysis are missing/unverified |
| Table 15; §9 | Complementary concepts, design risks and open issues | documentation | Partial: map every concept and limitation into platform controls and final discussion |
| Table 16; Appendix | Hand-built strategy walkthrough summaries for the running prompt | docs/examples | Verify all walkthroughs match the paper and are labelled illustrative, never experimental evidence |

## 3. Strategy inventory from Table 4

The source orders the strategies as follows. The implementation must preserve these identifiers and source semantics:

| ID | Strategy | Core protocol feature | Source calls / depth |
|---|---|---|---|
| S1 | Division of labour | Coordinator partitions by domain; specialists draft parts; coordinator checks ownership | n+2 / 3 |
| S12 | Jigsaw | Experts draft facets independently; integrator merges | n+1 / 2 |
| S2 | Brainstorming | Unfiltered independent generation; aggregator unions/merges | n+1 / 2 |
| S3 | Nominal group | Independent drafts, hidden drafts, ranking, rank-sum | 2n / 2 |
| S4 | Delphi | Anonymous expert rounds, facilitator summaries, stability stop | T(n+1) / 2T |
| S9 | Majority vote | Independent drafts and isolated ballots; majority inclusion | 2n / 2 |
| S5 | Devil's advocate | Draft, assigned critic objections, revision, judge | 4 / 4 |
| S6 | Dialectical inquiry | Second decomposer sees first and constructs counter-plan; synthesis | 3 / 3 |
| S8 | Peer review | Author draft, isolated reviewers, editor decision, optional revision | k+3 / 4 |
| S13 | Role reversal | Two agents exchange author/critic roles across rounds | 4 / 4 |
| S7 | Adversarial procedure | Two independent parties defend drafts before neutral judge | 5 / 3 |
| S11 | Mediation | Two drafts, mediator divergence summary, revisions, compromise stop | Table 4 base 5 / 3; bounded iterative cost separately specified in §5.4.2 |
| S10 | Consensus deliberation | Shared draft, sequential turns, moderator closes on stability/no objection | nT+1 / nT+1 |

**Critical:** Table 4's nominal call/depth figures and the detailed bounded iterative costs in strategy subsections must not be conflated. In particular S11 has a five-call/three-stage initial protocol, while §5.4.2 gives the bounded iterative accounting (2+3T calls; 1+2T stages).

## 4. Experimental reproduction matrix

The source defines nine distinct experiments. All are currently classified **not scientifically reproduced** until real observations and manifests are present.

| Experiment | Required independent variable / comparison | Primary outcomes | Minimum implementation evidence |
|---|---|---|---|
| E1 | Strategy and baseline across all datasets | All applicable Table 9 metrics | Direct per-strategy runner; budget-matched single-/multi-agent baselines; paired prompt records |
| E2 | Strategy × prompt features φ(P) | Utility, coverage, process gain | Prompt feature annotations and stratified analysis |
| E3 | Strategy × dataset | Utility, process gain | Domain-specific runs and metric applicability |
| E4 | Homogeneous MA-only vs heterogeneous MA/MB/MC | Process gain, error correlation | Exact model-family/version records; correlation computed from errors |
| E5 | n={2,3,5}, T={1,2,3} | Utility vs calls and depth | Factorial controlled runs with fixed executor |
| E6 | Seeded defect type | Critic/reviewer/judge precision and recall | Ground-truth defect injection and blinded scoring |
| E7 | Selection, vote, union, synthesis on identical drafts | Coverage, redundancy, validity | Shared draft corpus; only decision rule changes |
| E8 | C1–C8 vs best single strategy, equal budget | Process gain, cost | Budget-controlled composition runs |
| E9 | Agent order, seed, prompt paraphrase | Decomposition stability | Controlled perturbations and distance analysis |

## 5. Dataset obligations from Table 12

| Dataset | Source role | Required references / measures | Current gap |
|---|---|---|---|
| BREAK | Natural-language decomposition / semantic parsing | Reference sub-questions; agreement, validity V2/V5, redundancy, stability, cost; coverage does not apply | Verify source snapshot, split, reference adapter and scoring |
| StrategyQA | Multi-hop reasoning | Supporting facts; answer accuracy, solvability, process gain, stability, cost; coverage does not apply | Verify exact reference evidence and execution checks |
| TaskBench | Task dependencies and multiple domains | Reference sub-task graph; agreement, V2/V5, coupling, stability, cost; coverage does not apply | Verify graph representation and matcher |
| TravelPlanner | Constraint-heavy plans judged by execution | Annotated constraints, final-plan checks; utility, solvability, process gain, V2/V5, restricted coverage, stability, cost | No reference decomposition; implement source-defined constraint checks |
| Smart-administration | Ambiguity, conflicting objectives, multiple institutions | Practitioner-reviewed requirements, hypotheses, reference decompositions; all Table 9 metrics and hypothesis verdicts | Source says set of 60 prompts and materials to be released with code; verify actual availability, provenance and annotation before claiming readiness |

## 6. Experimental protocol controls that must be enforced

- Agent model families MA, MB, MC; homogeneous condition uses MA only.
- Fixed executor ME for all strategies.
- n=3 agents, k=3 reviewers, T≤2 for the main protocol.
- Temperature 0.7 for drafting; 0.2 for criticism/review; 0 for ranking, voting, merging and judging.
- Output limits: 1,024 tokens for decomposition; 512 for other calls.
- Fixed JSON decomposition schema: sub-problems, inputs, outputs and dependencies.
- q=3 extractors, union, human audit of 20% of prompts.
- Five seeds per configuration.
- 100 prompts per public benchmark; 60 smart-administration prompts.
- Baselines receive the calls of the compared strategy.
- Two human annotators rate 10% of decompositions; report Cohen's κ.
- Paired-prompt Wilcoxon signed-rank tests with Holm correction, α=0.05.
- Exact model versions and access dates must be recorded with results.

Do not silently substitute models, datasets, sample sizes, metric definitions or statistical procedures. Any unavoidable deviation must be explicitly reported as a deviation, not as a reproduction.

## 7. Platform and delivery audit

The verified main tree contains the Python engine, tests, docs, branding assets and one Colab notebook. It does **not** contain a visible web application/frontend directory in the inspected tree. Therefore the requested professional web application is not yet evidenced by this repository snapshot.

The Colab notebook is a template, not evidence of a completed T4 run. It must pin a commit, environment, model configuration and dataset snapshot. GPU use should be justified by the actual workload; provider API experiments do not become T4 experiments merely by running in Colab.

## 8. Immediate execution order

1. Complete definition/proposition/algorithm proof-to-code audit (§3, §6, §7).
2. Reconcile Table 4 strategy protocols and Table 5 candidate strategies with actual provider-visible prompts and traces.
3. Audit the equivalence matcher, reference annotations and dataset-specific metrics before running any strategy comparison.
4. Implement the direct E1 runner and budget-matched baselines; do not use adaptive selection as a substitute for E1.
5. Run a small real E1 pilot, inspect failures and costs, then run the full protocol.
6. Implement E2–E9 with separate configurations and immutable manifests.
7. Build and validate the professional web app around the real experiment API and artifacts.
8. Validate the Colab execution path and T4 only where applicable.
9. Release only after all claims have supporting evidence.

## 9. Evidence boundaries and release gates

- **G0 Source fidelity:** exact source specification and traceability reviewed.
- **G1 Semantic implementation:** algorithms and strategies match the paper.
- **G2 Software correctness:** unit, property, integration and provider-contract tests pass.
- **G3 Benchmark readiness:** datasets, references, metric applicability and annotation protocol validated.
- **G4 Scientific execution:** real experiments completed with raw observations and manifests.
- **G5 Statistical reproduction:** analyses, uncertainty, paired tests and multiple-comparison correction verified.
- **G6 Product delivery:** web app, Colab path, documentation and reproducible release verified.

A green CI is evidence for G2 only. It must never be presented as G4 or G5.
