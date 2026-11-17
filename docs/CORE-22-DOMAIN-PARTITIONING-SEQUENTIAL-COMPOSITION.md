# Core 22 — Domain partitioning and sequential strategy composition

## Source-aligned scope

This Core implements two paper-defined requirements:

- S1 Division of Labour and S12 Jigsaw require partitioned author views.
- C2 (Jigsaw → Devil's Advocate) and C8 (Brainstorming → Peer Review) are sequential chains under Definition 12, where the preceding decomposition seeds one author of the second strategy only.

C1 is explicitly excluded from sequential chaining. The paper defines it as phase composition under Definition 11 and Algorithm 3.

## Implementation

- `engine/sociodec/strategy_composition.py`
  - `DomainPartition`: explicit domain-to-agent mapping; no inferred assignment.
  - `build_domain_prompt_views`: creates evidence-bounded views from the declared goal, global constraints, deliverables, extracted explicit requirements and hypotheses. The coordinator/integrator receives the full prompt.
  - `SequentialCompositionExecutor`: executes C2/C8 through the concrete atomic adapter; passes first result as the seed to the second phase; accumulates calls, findings and hypothesis verdicts; conflicting verdicts fail closed.
- `engine/tests/test_strategy_composition.py`
- `docs/CORE-22-TEST-REPORT.md`

## Important distinction

The domain mapping is an explicit engineering input. The paper requires partitioned authors but does not prescribe an automated domain clustering algorithm. This Core does not silently infer a partition. Every extracted domain must be assigned exactly once.

## Exclusions and limitations

- C1 is Algorithm 3 phase composition, not four complete strategy runs. It is deferred to a dedicated Core.
- The second strategy receives a seed through the existing ConcreteStrategyAdapter; other authors do not receive that seed as a draft.
- Real provider behavior, model-family independence, and semantic correctness of the chosen partitions remain unvalidated.
- No benchmark experiment or E1–E9 result is claimed.
