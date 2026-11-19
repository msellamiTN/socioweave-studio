# Fixed E1 executor

`ProviderFixedExecutor` is a provider-backed implementation of the shared
executor interface consumed by `run_direct_e1_condition`.

## Execution contract

For each decomposition it:
1. Computes a deterministic topological order and rejects cycles.
2. Executes each runnable subproblem once, supplying only its declared direct
   predecessor answers and the subproblem's local inputs/constraints.
3. Marks failed subproblems explicitly and blocks their descendants.
4. Requests one composed answer from the declared deliverable contributors.
5. Requests a separate assessment for each hard constraint.
6. Returns `ExecutorRun` with execution evidence, per-attempt telemetry, and an
   executor call-attempt count separate from the strategy/baseline method budget.

All executor calls use temperature 0 and the configured output-token limit.
The executor ID must be preregistered and checked by the direct E1 runner.

## Evidence semantics and limitations

V3 is assessed from recorded solved/failed results, exact predecessor-answer
provenance, and topological execution order. V4 uses explicit model-generated
constraint assessments with evidence text. A V4 PASS therefore means that
all hard constraints received affirmative assessments; it is not an
independent proof that a natural-language answer is factually correct.
Malformed or missing assessments fail closed. Provider exceptions are retained as
failed call-attempt trace records and counted conservatively. If composition
fails, every hard-constraint assessment is marked failed without a follow-on
judge call.

This implementation is an operational executor profile, not an algorithm
specified in detail by the paper. Its model, prompt template, decoding limits,
and executor identity must be frozen and reported in the experiment manifest.
