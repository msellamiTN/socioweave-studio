# Social Strategy Execution Kernel — CORE 08

**Status:** merged implementation; validation scope limited to kernel contracts  
**Scientific basis:** Definitions 9–10 and the visibility/protocol representation documented in CORE 07.

## Purpose

CORE 07 represents a social strategy as a formal object. CORE 08 introduces a generic executor for an already specified `SocialStrategy`. It deliberately does not synthesize missing protocol steps or infer visibility from strategy names.

## Execution semantics

1. Protocol steps are grouped by ordered `(round, stage)`.
2. Every stage uses a snapshot of outputs committed before that stage begins.
3. Outputs produced in the same stage are unavailable to every peer in that stage. This models independent parallel actions without accidental sequential leakage.
4. For a step authored by agent `a`, only prior outputs authored by agents `b` for which `(a,b) ∈ V_round` are placed in its visible-output context.
5. An `output:<output_id>` input reference must resolve to an earlier output and must pass the visibility check. `prompt` is the only built-in initial input reference.
6. Steps marked `invokes_model=True` use the model executor. Steps marked false require a separately supplied local executor and do not increment model-call accounting.
7. For `anonymous=True`, executor-facing agent IDs, output IDs, and input references are replaced by deterministic opaque aliases; visibility is enforced against internal identities before aliases are exposed. The internal audit trace retains real identities.\n8. The final trace is checked against the strategy's declared `calls(σ)` and `depth(σ)`.

## Trace contract

Each internal step record retains output identity, agent, action, round, stage, input reference, model-call flag, visible output IDs and output text. In anonymous mode this internal trace is not passed to the executor: the executor receives a sanitized step object, opaque visible-output keys, and opaque author aliases. The kernel does not currently persist traces to a database or implement a decision-rule adjudicator.

## Explicit limitations

- The kernel executes a supplied protocol; it does not yet compile all thirteen Table 4 strategies into their protocol schedules.
- It does not automatically invoke the seven decision operators at the terminal state.
- It does not add prompt/decomposition schemas for critique, defense, revision, rank, vote, mediation or synthesis actions. Those are action-handler responsibilities to be specified.
- It does not claim a quality improvement or reproduce an experiment.
- A provider call may still fail; no retry policy is applied here because retries must not silently change the paper's call budget.

## Validation scope

Tests cover:
- no same-stage information leakage;
- visibility-permitted prior-stage output access;
- rejection of visibility violations;
- rejection of forward/same-stage references;
- separation of model and local steps;
- exact call and depth accounting;
- rejection of empty executor outputs;\n- anonymous-context regression: no original agent identifier or identity-bearing output key is exposed to the executor.

Run:

```bash
cd engine
python -m pip install -e '.[dev]'
python -m pytest -q
```

Passing these tests validates the execution-kernel contract only. Strategy-specific schedules and scientific execution remain separate milestones.
