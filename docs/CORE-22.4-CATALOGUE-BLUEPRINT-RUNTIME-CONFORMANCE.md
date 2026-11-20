# Core 22.4 — Catalogue–Blueprint–Runtime Semantic Conformance

**Status:** PASS — current-main reintegration validated on exact PR head `a4a06a18b84cc576ee0b05905f2ab1d932b9ef37` (merge commit `09f978c6dfeb31f8c4490ba5c2d9978e33bfc348`). This is software conformance work, not scientific validation or an empirical strategy comparison.

## Source contract

The oracle is based on the paper's Definition 10, Table 4, strategy-specific protocol descriptions in Section 5, Definition 12 for sequential composition, and Algorithm 1 for execution. The thirteen established strategies are enumerated from the canonical catalogue. The five Table 5 candidates C1–C5 remain outside the established-strategy oracle.

The machine-readable profile is exposed by `sociodec.conformance.PROFILES`, `PROFILE_BY_ID`, and parameterized `profile_as_dict()`. The exported JSON-compatible object includes concrete ordered agents, role assignments, protocol steps (agent/action/input/round/stage), per-round visibility pairs, decision rule, Table 4 formulas, runtime formulas, expected calls/depth and anonymity.

## Table 4 and iterative execution distinction

The profile keeps paper-reported Table 4 cost separate from the concrete bounded runtime formula where the paper describes continuation rounds. S11 Mediation has a five-call, three-stage initial profile; Section 5.4.2 explicitly permits further rounds when revisions still differ. With T mediation rounds, the runtime maximum is therefore (2+3T) calls and (1+2T) stages. At T=1, this reduces to Table 4's five calls and three stages. This distinction is deliberate and tested.

## Blueprint conformance

`validate_blueprint()` compares the generated blueprint with an independent expected protocol signature. It checks:

- exact ordered agent roster and prompt-view coverage;
- exact declared role set and role assignment for every agent and round;
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

The accounting identity is `scheduled_steps = protocol_steps + skipped_steps`; executed protocol outputs are partitioned into provider, seeded and precomputed steps. The analogous depth identity is `scheduled_depth = depth_executed + skipped_stages`. The runtime's stage-snapshot behavior is regression-tested: peer outputs from the same stage are not visible to one another; step references must exist before the current stage and be permitted by visibility. S6 additionally passes an explicit counter-plan instruction to the invoker while preserving the original prompt and D1 in separate context channels. S11 records convergence and applies the paper's D1 return rule when the stop condition is met. Sequential composition tests protect the first-phase independence and second-phase seed placement contract. The first phase receives an empty draft tuple and no chain seed; only the designated second-phase author receives the preceding decomposition.

## Conformance test matrix

The test suite exercises all thirteen strategies at three parameter configurations:
- minimum: (n=1,k=1,T=1);
- typical: (n=3,k=3,T=2);
- larger: (n=5,k=4,T=3).

Negative mutations cover prompt-view roster, role assignment, visibility, decision rule, protocol/input references and model-call accounting. Existing runtime tests cover same-stage isolation, seed adoption, precomputed outputs, invalid references, and fail-closed behavior.

## Acceptance evidence

Current exact-head evidence: GitHub Actions run [44822306187](https://github.com/msellamiTN/socioweave-studio/actions/runs/44822306187) on `a4a06a18b84cc576ee0b05905f2ab1d932b9ef37` passed **524 tests**. The earlier 448-test run remains historical only. See [CORE-22.4-TEST-REPORT.md](CORE-22.4-TEST-REPORT.md).

## Evidence boundary

A passing report establishes agreement between the current catalogue, the independent oracle, generated blueprints and deterministic runtime accounting under the tested configurations. It does not prove the social strategy mechanisms, model-family independence, semantic anonymity, decomposition validity, V3 solvability, V4 faithfulness, or empirical utility. No live provider/model calls are made in this Core.
