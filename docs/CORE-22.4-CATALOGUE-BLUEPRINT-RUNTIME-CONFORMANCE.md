# Core 22.4 — Catalogue–Blueprint–Runtime Semantic Conformance

**Status:** PASS — deterministic software conformance on commit `39d16c623e23b9e8d7ee77cdcf27c87024bfbe23`. This is not scientific validation or an empirical strategy comparison.

## Source contract

The oracle is based on the paper's Definition 10, Table 4, strategy-specific protocol descriptions in Section 5, Definition 12 for sequential composition, and Algorithm 1 for execution. The thirteen established strategies are enumerated from the canonical catalogue. The five Table 5 candidates C1–C5 remain outside the established-strategy oracle.

The machine-readable profile is exposed by `sociodec.conformance.PROFILES`, `PROFILE_BY_ID`, and `profile_as_dict()`. It records agent cardinality, roles, rounds, action sequence, input references, visibility contract, decision rule, Table 4 call/depth formulas, runtime call/depth formulas, and anonymity.

## Table 4 and iterative execution distinction

The profile keeps paper-reported Table 4 cost separate from the concrete bounded runtime formula where the paper describes continuation rounds. S11 Mediation has a five-call, three-stage initial profile; Section 5.4.2 explicitly permits further rounds when revisions still differ. With T mediation rounds, the runtime maximum is therefore (2+3T) calls and (1+2T) stages. At T=1, this reduces to Table 4's five calls and three stages. This distinction is deliberate and tested.

## Blueprint conformance

`validate_blueprint()` compares the generated blueprint with an independent expected protocol signature. It checks:

- exact ordered agent roster and prompt-view coverage;
- role assignment for every agent and round;
- strategy round count and stage/action/input signature;
- decision rule and anonymity flag;
- exact visibility relation by round;
- Table 4 formula consistency with the canonical catalogue;
- model-call count and stage-depth formula;
- prior-step input references and the acting agent's visibility of referenced output.

The oracle uses independent expected signatures; it does not call the strategy factory to decide what the expected protocol should be.

## Runtime semantics and accounting

`StrategyRun` now exposes:
- `scheduled_steps` / `scheduled_depth`: total protocol steps and stages in the blueprint;
- `protocol_steps`: outputs actually produced;
- `model_invocations`: provider calls actually made;
- `seeded_steps`: outputs adopted from caller-supplied seeds;
- `precomputed_steps`: non-model outputs supplied by the caller;
- `skipped_steps` / `skipped_stages`: conditional or early-stop work not executed;
- `accounting_reconciles`: verifies that the three output classes partition all produced steps and that `calls_made == model_invocations`.

The accounting identity is `scheduled_steps = protocol_steps + skipped_steps`; executed protocol outputs are partitioned into provider, seeded and precomputed steps. The analogous depth identity is `scheduled_depth = depth_executed + skipped_stages`. The runtime's existing stage-snapshot behavior is regression-tested: peer outputs from the same stage are not visible to one another; step references must exist before the current stage and be permitted by visibility. Sequential composition tests protect the first-phase independence and second-phase seed placement contract. The first phase receives an empty draft tuple and no chain seed; only the designated second-phase author receives the preceding decomposition.

## Conformance test matrix

The test suite exercises all thirteen strategies at three parameter configurations:
- minimum: (n=1,k=1,T=1);
- typical: (n=3,k=3,T=2);
- larger: (n=5,k=4,T=3).

Negative mutations cover prompt-view roster, role assignment, visibility, decision rule, protocol/input references and model-call accounting. Existing runtime tests cover same-stage isolation, seed adoption, precomputed outputs, invalid references, and fail-closed behavior.

## Acceptance evidence

GitHub Actions run [44423378674](https://github.com/msellamiTN/socioweave-studio/actions/runs/44423378674) on exact commit `39d16c623e23b9e8d7ee77cdcf27c87024bfbe23`: **447 passed, 0 failed, 0 skipped**. See [CORE-22.4-TEST-REPORT.md](CORE-22.4-TEST-REPORT.md) for the conformance matrix and reproduction instructions.

## Evidence boundary

A passing report establishes agreement between the current catalogue, the independent oracle, generated blueprints and deterministic runtime accounting under the tested configurations. It does not prove the social strategy mechanisms, model-family independence, semantic anonymity, decomposition validity, V3 solvability, V4 faithfulness, or empirical utility. No live provider/model calls are made in this Core.
