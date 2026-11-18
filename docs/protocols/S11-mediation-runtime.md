# S11 — Mediation protocol runtime

The paper defines mediation as a bounded iterative exchange between two parties and a non-partisan mediator.

## Round structure

Each round contains five model calls in three parallelism stages:

1. **Stage A — independent drafts:** party-1 and party-2 draft independently and in parallel.
2. **Stage B — mediator summary:** the mediator identifies agreements and disagreements. The mediator is a facilitator, not a judge, and must not select a winning party draft.
3. **Stage C — revisions:** both parties revise in parallel using the preceding drafts and mediator summary.

For round (t), the engine records the five calls at three sequential depth stages. Across (T) rounds, the maximum profile is (5T) calls and (3T) stages.

## Stopping

After both revisions in a complete round, the runtime compares the two revised decompositions:

- exact canonical candidate equality; or
- an explicitly configured decomposition-distance evaluator returns a value at most (epsilon); or
- the configured maximum round count (T) is reached.

The epsilon evaluator is injected by the caller. The runtime does not invent a distance metric. Its inputs are canonical JSON candidate payloads; callers should bind the evaluator to the paper's decomposition-distance definition.

## Decision boundary

The mediator summary is trace evidence, not a decision. The final negotiated joint decomposition remains an explicit artifact supplied by the negotiation controller and is passed to the compromise decision operator. The decoder never silently selects party-1 or party-2's draft as the negotiated result.

## Evidence boundary

Trace validation and deterministic runtime tests establish protocol ordering, round completeness, parallel-stage metadata, bounded execution, and stopping behavior. They do not establish semantic neutrality of a mediator, genuine party acceptance, or the correctness of the negotiated decomposition; those require separate evaluation.
