# Core 22.4 — Test and Conformance Report

**Result:** PASS — deterministic software conformance tests on exact commit `39d16c623e23b9e8d7ee77cdcf27c87024bfbe23`.  
**GitHub Actions:** [Run 44423378674](https://github.com/msellamiTN/socioweave-studio/actions/runs/44423378674).  
**Result:** 447 passed in 0.49s; 0 failed; 0 skipped.

## Coverage delivered

| Acceptance area | Evidence | Result |
|---|---|---|
| Thirteen established strategy profiles | `PROFILES`, `PROFILE_BY_ID`, `profile_as_dict` | PASS |
| Candidate strategies kept separate | C1–C5 excluded from established profiles and factory | PASS |
| Independent catalogue-to-blueprint oracle | Expected ordered signatures compared to generated blueprints | PASS |
| Agent roster and prompt views | Exact roster/cardinality and prompt-view coverage | PASS |
| Roles and rounds | Exact agent/round role map and strategy round bounds | PASS |
| Action/input/stage sequence | Ordered protocol signature including `input_ref` | PASS |
| Visibility relations | Exact per-round observer/author relation | PASS |
| Decision semantics and anonymity | Rule and anonymity compared to profile | PASS |
| Call/depth formulas | Formula compared with generated protocol | PASS |
| Step references | Prior-step existence, stage precedence and visibility | PASS |
| Runtime accounting | Scheduled, executed, skipped, provider, seeded and precomputed steps reconcile; scheduled/executed depth reconciles | PASS |
| Stage snapshot | Existing runtime regression confirms same-stage peer isolation | PASS |
| Sequential composition | First phase receives no inherited drafts/seed; second phase receives first decomposition as chain seed | PASS |
| Negative mutation tests | Roster, roles, visibility, decision, references and call-count mutations | PASS |

## Parameter configurations

All thirteen strategies pass the independent blueprint oracle at:
- ((n,k,T)=(1,1,1)): minimum valid configuration;
- ((3,3,2)): typical configuration;
- ((5,4,3)): larger configuration.

A second parameterized test executes all thirteen blueprints through the deterministic mock runtime at ((2,2,1)), then reconciles provider calls, executed outputs and actual depth. S8's ACCEPT branch correctly skips its conditional author revision and is checked against the reduced actual call count.

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
