# Direct E1 condition runner

This increment adds the execution seam between the E1 preregistration manifest
and actual condition runs.

## Execution contract

For each frozen prompt/seed/condition, the runner executes exactly:

1. The explicitly selected strategy or baseline adapter.
2. The same predeclared fixed executor adapter (ME).
3. Structural V1/V2/V5 and hypothesis-verdict checks.
4. Execution-evidence V3/V4 checks.
5. Dataset-aware metrics, call-budget enforcement, output hashes and provider traces.

It does **not** invoke Algorithm 2, `run_adaptive`, plan a strategy chain,
compare candidate decompositions, or select a winner. Each row evaluates the
decomposition returned by its own method adapter.

## Implemented strategy path

`DirectProtocolStrategyAdapter` executes one of the thirteen paper strategies
through the visibility-aware protocol runtime. It routes each agent to the
model identity registered for the condition and requires provider-call traces.

Paper-specific runtime semantics now include:

- S1: coordinator-generated partition JSON is consumed by specialists; the
  runtime validates the specialist roster and prevents full-prompt/sibling
  partition leakage.
- S4, S10 and S11: the direct adapter passes the default `ε = 0.1` and a
  typed Definition 7 decomposition-distance callback to the runtime.
- S10: when a stable round ends deliberation early, the single moderator
  closure is recorded immediately after the actual last participant turn.
- S11: the mediator's negotiated decomposition remains explicit adjudication
  evidence; the runtime does not infer it from a summary.

The default matcher is `exact-output-local-constraints-v1`. It is a lexical
proxy, not semantic equivalence; matcher sensitivity remains an experimental
risk and must be reported.

## Baseline path: implemented under operational profile v1

The six baseline IDs have direct adapters in
`sociodec.direct_baselines.DirectBaselineAdapter`. They are executed through
the same `MethodRun` interface and then the same fixed executor ME,
validation, metric-applicability and trace-accounting path as strategies.

The operational details not specified in §8.1 are frozen under
`e1-baselines-operational-profile-v1` and are recorded in each result's
metadata. In particular, the profile defines self-refinement as draft/critique/
revision, self-consistency as budget-sized independent sampling with
matcher-based frequency aggregation, evaluator as non-mutating assessment,
debate as two drafts plus budget-matched debate turns and judge, and nominal
selection as three isolated drafts ranked by extracted-requirement coverage.
These are implementation choices, not claims about the paper's exact prompts
or omitted protocol details.

The full source-vs-operationalization boundary is documented in
[the E1 baseline operationalization audit](PAPER-E1-BASELINE-OPERATIONALIZATION.md).
The adapters have unit-test coverage; no provider-backed E1 baseline
experiments or empirical results are claimed.

## Adapter obligations

- A method adapter must implement `run(condition, prompt, seed)` and return
  `MethodRun` with actual model invocation count and provider trace.
- An executor adapter must implement `execute(prompt, decomposition, seed)`
  and return `ExecutorRun` containing an `ExecutionRun`, actual executor call
  count and provider trace.
- The executor identity is checked before and after execution.
- The condition's registered call budget applies to strategy/baseline method
  calls, as required for Table 13 budget matching. Fixed executor ME calls are
  recorded separately and included in total observed cost, but do not consume
  the method-call budget.
- Utility is recorded only when an independent scorer is explicitly supplied.
- Cross-condition metrics (stability, reference agreement and process gain)
  are not imputed by a single-condition run; they belong to the paired analysis
  layer.

## Resumable campaign execution

`sociodec.direct_e1_campaign.DirectE1CampaignRunner` executes a frozen set of
`E1Condition` rows against an explicit prompt snapshot and injected prompt,
extraction, method and fixed-executor adapters. It verifies baseline-to-strategy
call-budget matching, preserves exact prompt text, records per-condition
successes/failures, and fsyncs each JSONL record. Existing records are accepted
only when the campaign configuration hash matches; failed rows are not silently
retried in place.

The runner is an orchestration seam, not a dataset loader or model deployment.
Real provider credentials, dataset snapshots, prompt interpretation factories,
extractors, model routing and executor ME must be supplied by the experiment
operator. A complete paper grid can be represented as conditions, while smaller
pilot subsets can be used for infrastructure validation without being reported
as E1 results.

## Frozen benchmark snapshot intake

`sociodec.datasets.freeze_e1_benchmark_snapshot` is the fail-closed intake
boundary for the five E1 datasets. The operator supplies one local JSONL file
per dataset through `E1DatasetSource(path, source_version, split)`. The intake:

- requires exactly BREAK, StrategyQA, TaskBench, TravelPlanner and
  smart-administration;
- enforces the preregistered counts (100, 100, 100, 100 and 60);
- rejects duplicate or malformed IDs, non-string prompt text, malformed
  metadata and any row whose split differs from the declared split;
- records the source filename, exact source-file SHA-256, declared source
  version and split, prompt IDs, per-prompt hashes and total count;
- creates a canonical snapshot SHA-256 over the per-dataset provenance entries.

The resulting `E1FrozenSnapshot.examples` can be passed to the direct campaign
runner, and `e1_prompt_id_map(snapshot)` supplies the exact mapping accepted by
`build_e1_conditions`. The intake does not download, transform, infer, or
synthesize benchmark examples. Synthetic rows used by its unit tests are test
fixtures only and are not benchmark inputs.

The manifest records declared source versions and split names; it does not
independently establish upstream dataset authenticity, licensing permission,
or whether the declared split reproduces the paper's original selection.
Those remain operator/source-verification obligations. Public-dataset license
review is still required before any real campaign is frozen or run.

## S6 and S11 decision-semantics safeguards

The direct runtime now exposes and serializes an explicit `action_instruction`
in the provider request payload for S6's `counter-plan` action. It preserves the original prompt as the
authoritative problem statement while treating D1 as the proposal to challenge,
not as binding assumptions. The S6 runtime regression test verifies that the
counter-planner receives both the original prompt and D1 as distinct context
channels, together with the explicit negated-assumption instruction. This
verifies the instruction contract at the invoker boundary; it does not prove
that a language model obeys it.

For S11, the runtime records whether the latest party revisions met the paper's
stop condition (exact agreement or Definition 7 distance at most epsilon), the
round in which convergence occurred, and the measured distance when configured.
The typed decision decoder now applies Section 5.4.2's return rule and selects
party-1's latest draft D1 after convergence. If the configured round limit is
exhausted without convergence, a separately supplied negotiated joint
decomposition and rationale remain mandatory; the mediator is not allowed to
invent or select a party draft.

These are software-level semantics and test evidence. They do not establish
that the model follows the counter-plan instruction, that the distance matcher
is semantically adequate, or that the resulting decomposition is valid or
useful.

## Scientific boundary

This is an executable harness contract, not an E1 result. It does not supply
benchmark snapshots, model/provider implementations, smart-administration
annotations, human ratings, or empirical results. The dataset applicability
registry controls whether coverage is emitted.

The adaptive trial path remains available for adaptive-strategy research, but
is not a substitute for the direct E1 comparison.
