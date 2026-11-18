# Core 22.4 — Test and Conformance Report

**Result:** PASS — deterministic software conformance tests on exact commit `a28f8a26a1a8739bcae9018d3c9370da11092bef`.  
**GitHub Actions:** [Run 44423563050](https://github.com/msellamiTN/socioweave-studio/actions/runs/44423563050).  
**Result:** 448 passed in 0.92s; 0 failed; 0 skipped.

## Coverage delivered

| Acceptance area | Evidence / test IDs | Result |
|---|---|---|
| Thirteen established strategy profiles | `PROFILES`, `PROFILE_BY_ID`, `profile_as_dict`; `test_profile_oracle_covers_only_thirteen_established_strategies` | PASS |
| Candidate strategies kept separate | C1–C5 excluded from established profiles and factory | PASS |
| Independent catalogue-to-blueprint oracle | `test_all_thirteen_profiles_conform_to_blueprints_at_boundary_configurations` | PASS |
| Agent roster and prompt views | `test_conformance_detects_prompt_view_roster_leak_or_omission` | PASS |
| Roles and rounds | `test_conformance_detects_role_assignment_drift`; `test_conformance_detects_unused_or_unexpected_declared_role`; `test_all_thirteen_profiles_conform_to_blueprints_at_boundary_configurations` | PASS |
| Action/input/stage sequence | `test_conformance_detects_protocol_input_reference_mutation` | PASS |
| Visibility relations | `test_conformance_detects_visibility_mutation`; `test_conformance_detects_step_reference_that_violates_visibility` | PASS |
| Decision semantics and anonymity | `test_conformance_detects_wrong_decision_rule`; all-strategy oracle test | PASS |
| Call/depth formulas | all-strategy oracle test; `test_conformance_detects_model_call_accounting_drift` | PASS |
| Step references | `test_conformance_detects_protocol_input_reference_mutation`; `test_conformance_detects_step_reference_that_violates_visibility` | PASS |
| Runtime accounting | `test_runtime_accounting_partitions_model_seeded_and_precomputed_steps`; `test_runtime_execution_reconciles_with_blueprint_and_actual_output_accounting` | PASS |
| Stage snapshot | `test_runtime_enforces_first_round_visibility_and_stage_snapshot`; `test_runtime_rejects_same_stage_peer_output_reference` | PASS |
| Sequential composition | `test_sequential_composition_discards_external_seeds_before_first_phase`; `test_sequential_composition_seeds_second_phase_and_accumulates_calls_and_evidence` | PASS |
| Negative mutation tests | Roster, roles, visibility, decision, references and call-count mutations | PASS |

## Parameter configurations

All thirteen strategies pass the independent blueprint oracle at:
- ((n,k,T)=(1,1,1)): minimum valid configuration;
- ((3,3,2)): typical configuration;
- ((5,4,3)): larger configuration.

A second parameterized test executes all thirteen blueprints through the deterministic mock runtime at ((2,2,1)), then reconciles provider calls, executed outputs and actual depth. S8's ACCEPT branch correctly skips its conditional author revision and is checked against the reduced actual call count.

## Formula oracle

A finite, reviewed expression evaluator checks each profile's agent-cardinality, round, runtime-call and runtime-depth formula against the independently generated expected roster and protocol. It does not use Python `eval`; unsupported formula strings fail closed.

## Runtime accounting identity

Every runtime-produced run reports scheduled and executed protocol steps, skipped steps, scheduled and executed stages, provider invocations, seeded steps and precomputed steps. The checks enforce both identities:

- scheduled steps = executed outputs + skipped steps;
- executed outputs = provider invocations + seeded outputs + precomputed outputs;
- scheduled stages = executed stages + skipped stages.

## Important correctness fix: Definition 12

The sequential composition executor previously forwarded external initial drafts and a chain seed to its first phase. This could seed first-phase authors and suppress calls that must be independent. The first phase now receives an empty draft tuple and `chain_seed=None`; the second phase receives the first phase's decomposition as its chain seed. A regression test supplies non-empty external drafts and a non-null external seed to prove neither reaches the first phase and that the exact first-phase result reaches the second.

## S11 accounting clarification

Table 4's initial mediation profile is five calls over three stages. Section 5.4.2 allows additional mediation rounds if revisions still differ. The profile therefore records Table 4's base cost separately from the bounded runtime maximum (2+3T) calls and (1+2T) stages. At (T=1), the values coincide with Table 4.

## Remaining limits

- Runtime stages are dispatched serially for deterministic reproducibility; stage metadata and snapshots preserve information-flow semantics but do not establish parallel latency.
- Mock invokers do not establish provider reliability, model-family independence, or strategy effectiveness.
- V3 solvability and V4 faithfulness remain execution-level checks; this conformance suite does not claim either has been scientifically validated.
- Semantic anonymity, authentic dissent, mediator neutrality, decomposition quality and task utility remain outside this software-conformance result.
- The report validates current code against the encoded paper-derived profile; it is not a new proof of the paper's propositions.

## Reproduction

From `engine/`:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```
