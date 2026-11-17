# Core 20 — Fixed-executor evaluation and end-to-end trial adapter

## Objective

Connect an adaptive decomposition result to a predeclared fixed executor, validate V3/V4 with Core 06 evidence, and produce a typed experiment outcome suitable for Core 16/18 persistence and evaluation.

## Contract

`evaluate_adaptive_trial(result, executor, seed, expected_executor_id, ...)`:

1. Checks executor identity before execution and checks the returned `ExecutionRun.executor_id`.
2. Executes the selected decomposition using the supplied seed.
3. Calls Core 15 `finalize_adaptive_result` with the executor's evidence.
4. Computes coverage, redundancy, coupling, DAG depth, structural validity, V3, V4, full validity and subproblem solvability.
5. Computes utility only when an independent utility scorer is supplied.
6. Returns `TrialOutcome` with provider trace and metadata; stores only a hash of the composed answer, not its raw text.

## Scientific safeguards

- The same `expected_executor_id` must be fixed across all strategies in a comparison.
- A model's own assertion that its answer is correct is not an independent V4 proof. The executor/verifier must provide evidence-bearing `ConstraintAssessment` records.
- Missing execution evidence is not treated as passing. This adapter requires an `ExecutionRun`.
- Utility is not inferred from coverage or validity; it is omitted unless an external scorer is supplied.
- Cyclic decompositions have undefined DAG depth and fail closed.
- The existing Core 06 validator checks evidence consistency, not semantic truth of an answer or verifier judgment.

## Integration

Use this adapter as the final stage of a campaign trial callback after Core 11 `run_adaptive` has returned an `AdaptiveResult`. Supply the exact same fixed executor implementation/model version for every compared strategy and persist `TrialOutcome.provider_trace` alongside metadata via Core 19 resumable checkpoints.

## Tests and acceptance

Tests cover fixed identity, valid and failed executor evidence, V3/V4 propagation, utility omission/range checking, trace metadata and cycle handling. Full engine CI must pass on the exact commit before software acceptance.

## Limitations

- This core does not implement a provider-backed executor or a semantic verifier. They remain explicit injected dependencies.
- It does not prove the fixed executor's model/version or verifier independence beyond the caller-supplied identity contract.
- No real benchmark run, utility result, strategy ranking or E1–E9 finding is claimed.
