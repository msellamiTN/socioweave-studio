# Direct E1 condition runner

This increment adds the missing execution seam between the E1 preregistration
manifest and actual condition runs.

## Execution contract

For each frozen prompt/seed/condition, the runner executes exactly:

1. The explicitly selected strategy or baseline adapter.
2. The same predeclared fixed executor adapter (ME).
3. Structural V1/V2/V5 and hypothesis-verdict checks.
4. Execution-evidence V3/V4 checks.
5. Dataset-aware metrics, call-budget enforcement, output hashes and provider traces.

It does **not** invoke Algorithm 2, `run_adaptive`, plan a strategy chain, compare
candidate decompositions, or select a winner. Each row evaluates the decomposition
returned by its own method adapter.

## Adapter obligations

- A method adapter must implement `run(condition, prompt, seed)` and return
  `MethodRun` with the actual model invocation count and provider trace.
- An executor adapter must implement `execute(prompt, decomposition, seed)`
  and return `ExecutorRun` containing an `ExecutionRun`, actual executor call
  count and provider trace.
- The executor identity is checked before and after execution.
- Combined method + executor calls may not exceed the condition's registered
  call budget. A missing/incomplete provider trace is marked, never fabricated.
- Utility is recorded only when an independent scorer is explicitly supplied.

## Scientific boundary

This is an executable harness contract, not an E1 result. It does not supply
benchmark snapshots, model/provider implementations, smart-administration
annotations, human ratings, or empirical results. The lexical default matcher
remains an approximation for equivalence-dependent redundancy. The E1 dataset
applicability registry controls whether coverage is emitted.

The existing adaptive trial path remains available for its own purpose, but is
not used here as a substitute for direct E1 comparisons.
