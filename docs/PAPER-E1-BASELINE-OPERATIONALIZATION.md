# E1 baseline operationalization audit

## Purpose

This document separates what the paper specifies from implementation choices
that would otherwise be silently invented. It is a pre-implementation gate for
the six E1 baselines, not a claim that baseline runs have been completed.

Primary source: *Societies of Decomposers: Social and Organisational Strategies
for LLM-Based Prompt Decomposition*, Section 8.1 (Baselines and procedure) and
Table 13 (Experimental settings).

## Source-supported baseline definitions

| ID | Baseline | What Section 8.1 explicitly says |
|---|---|---|
| `single_plan_and_solve` | Single decomposer with plan-and-solve prompting | One decomposer; plan-and-solve prompting |
| `single_self_refinement` | Single decomposer with self-refinement | The plan-and-solve single decomposer adds self-refinement |
| `single_self_consistency` | Single-model sampling | Samples several decompositions from one model and keeps the most frequent sub-problems |
| `decomposer_plus_evaluator` | Separate evaluator | A decomposer is followed by a separate evaluator |
| `multi_agent_debate` | Multi-agent debate | Debate is applied to the decomposition |
| `nominal_multi_agent` | Nominal group | Independent drafts; select the best by coverage; no interaction |

The paper additionally states that every strategy and baseline uses the same
models, the executor is fixed as ME, and the sampling and debate baselines
receive the same number of calls as the strategy they are compared against.
Table 13 specifies MA/MB/MC as the three model families, a homogeneous MA-only
variant, n=3, k=3, T≤2, drafting temperature 0.7, criticism/review 0.2,
ranking/voting/merging/judging 0, 1,024 decomposition tokens, 512 tokens for
other calls, and five seeds.

## What the paper does not specify

The cited baseline paragraph and Table 13 do not fully define:

1. Exact prompt templates, output schemas and stopping rules for all six
   baselines.
2. The number of self-refinement cycles and whether critique and revision are
   separate calls.
3. The evaluator's rubric, output schema, authority, and whether it may request
   a revision.
4. The debate roles, turn order, visibility, stopping rule and how the final
   decomposition is selected.
5. The sample count for self-consistency beyond the requirement that its call
   budget be matched to the compared strategy.
6. The number of nominal independent drafts and tie-breaking among equal
   coverage candidates.
7. Whether nominal/self-consistency coverage selection uses the aggregated
   extracted requirement set, a dataset reference, or another declared
   requirement universe. Using gold references for selection would risk
   evaluation leakage and must not be assumed.
8. Whether “same number of calls” means method calls alone or method plus the
   fixed executor call count. The fixed executor is common to all conditions,
   but the campaign must record the accounting convention explicitly.

These omissions are not permission to choose arbitrary implementations and
label them as exact reproductions.

## Candidate operationalization — requires preregistration

The following are implementable interpretations, **not paper facts**. Freeze
them in the E1 manifest and report them as operational choices before any
empirical run:

| Baseline | Candidate protocol | Decisions that must be frozen |
|---|---|---|
| Plan-and-solve | One model call returns a typed decomposition using an explicit plan-then-construct instruction | Exact prompt, output schema, model identity, whether one call is fixed |
| Self-refinement | One draft, one self-critique, one revised decomposition | Whether critique/revision are distinct calls; whether more than one cycle is allowed |
| Self-consistency | Repeated independent samples from one model; aggregate sub-problems by the same registered matcher and retain the most frequent | Sample count, tie policy, dependency and deliverable-composition reconstruction, call-budget mapping |
| Decomposer + evaluator | Decomposer produces a typed candidate; a separate evaluator returns a structured assessment | Evaluator rubric, model separation, revise/no-revise branch and exact call budget |
| Multi-agent debate | Multiple agents exchange structured arguments about candidate decompositions under a fixed turn schedule | Agent count, visibility, rounds, final decision rule and exact budget allocation |
| Nominal multi-agent | Independent drafts with no cross-agent visibility; select the candidate with maximum coverage over the preregistered non-gold requirement universe | Draft count, coverage universe, tie-breaking and call-budget mapping |

### Required controls

- The method and fixed executor call counts must be logged separately.
- Sampling and debate baselines must match the call budget of each compared
  strategy, as required by Table 13; no budget may be inferred from a strategy
  name alone.
- The nominal baseline must not use gold decomposition labels or hidden test
  annotations to choose its winner.
- Self-consistency must state which equivalence matcher defines “most
  frequent”. The current default matcher is a lexical proxy and is not semantic
  equivalence.
- All baseline outputs must pass through the same typed decoder, structural
  validation, fixed executor ME, dataset-aware metric applicability and trace
  accounting as strategy outputs.
- No baseline result may be generated from mock data or substituted synthetic
  scores.

## Implementation status

- E1 condition manifest: baseline IDs and matched-strategy budget fields exist.
- Direct method/executor runner: accepts a baseline adapter and enforces the
  registered upper call budget.
- Executable adapters for the six baseline IDs: **not implemented**.
- Baseline prompt templates and call-allocation contract: **not frozen**.
- E1 empirical results: **none claimed**.

## Exit criteria

Baseline implementation can begin once the candidate operationalization is
frozen. It is ready for E1 only when each baseline has focused tests for its
protocol, call accounting, decision rule, failure paths, typed output decoding,
and budget matching against the compared strategy.
