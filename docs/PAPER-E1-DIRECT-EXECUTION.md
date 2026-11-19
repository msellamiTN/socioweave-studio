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

## Baseline path: not yet implemented

The E1 manifest defines the six baseline IDs, and `run_direct_e1_condition`
accepts a baseline adapter through the same method interface. However, this
repository does **not yet contain executable implementations** for those six
baseline IDs. The baseline specifications and source ambiguities are tracked in
[the E1 baseline operationalization audit](PAPER-E1-BASELINE-OPERATIONALIZATION.md).
Do not describe the direct E1 path as complete until those adapters exist and
are tested.

## Adapter obligations

- A method adapter must implement `run(condition, prompt, seed)` and return
  `MethodRun` with actual model invocation count and provider trace.
- An executor adapter must implement `execute(prompt, decomposition, seed)`
  and return `ExecutorRun` containing an `ExecutionRun`, actual executor call
  count and provider trace.
- The executor identity is checked before and after execution.
- Combined method + executor calls may not exceed the condition's registered
  call budget.
- Utility is recorded only when an independent scorer is explicitly supplied.
- Cross-condition metrics (stability, reference agreement and process gain)
  are not imputed by a single-condition run; they belong to the paired analysis
  layer.

## Scientific boundary

This is an executable harness contract, not an E1 result. It does not supply
benchmark snapshots, model/provider implementations, smart-administration
annotations, human ratings, or empirical results. The dataset applicability
registry controls whether coverage is emitted.

The adaptive trial path remains available for adaptive-strategy research, but
is not a substitute for the direct E1 comparison.
