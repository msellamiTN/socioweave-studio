# SOCIOWEAVE Engineering Quality Gates

**Policy:** No Core feature is accepted and no dependent Core starts until the current Core's complete test suite passes.

## 1. Definition of a complete Core test

Each Core must provide and pass all applicable layers below. A test layer may be marked not applicable only with a written technical reason in that Core's acceptance report.

| Layer | Required evidence |
|---|---|
| Static and import checks | Package installs; modules import; syntax/type/lint checks configured for the language pass |
| Unit tests | Every public domain type, constructor invariant, algorithm branch and error path is tested |
| Boundary tests | Empty, singleton, maximum/minimum, malformed, Unicode and adversarial inputs as relevant |
| Negative tests | Invalid states are rejected; errors are typed and actionable |
| Integration tests | Core works with adjacent domain models and provider/protocol interfaces |
| Property/invariant tests | Mathematical and structural invariants are tested over generated cases where practical |
| Regression tests | Every defect found during implementation becomes a permanent test |
| Contract tests | Observable behavior matches the paper-derived specification and documented software contracts |
| Reproducibility | Test command, Python/runtime version, dependencies and commit SHA are recorded |

## 2. Acceptance gate

A Core is **PASS** only when:
1. All required test layers have evidence.
2. CI is green on the exact commit proposed for acceptance.
3. No known failing or skipped test is hidden; every skip is explained.
4. Paper-derived properties are distinguished from implementation choices.
5. The Core specification and test report are updated.
6. Any remaining limitation is documented and does not invalidate the claimed contract.

A green unit-test job alone is not proof of scientific correctness, semantic validity, LLM quality or production readiness. Those require separate evaluations and experiments.

## 3. Required per-Core delivery bundle

Each Core must contain:
- implementation;
- focused unit and boundary tests;
- integration/contract tests with its dependencies;
- negative and regression tests;
- a Core specification linked to the paper sections/definitions;
- a test report recording commit SHA, environment, exact command, test count, result and known limitations.

## 4. Execution sequence

1. Implement one Core.
2. Review it against the paper and the Core specification.
3. Add the full test suite before moving on.
4. Run the full suite locally or in CI.
5. Inspect failures, fix the implementation and retain regression tests.
6. Re-run the complete suite on the final commit.
7. Publish the test report and mark PASS or BLOCKED.
8. Only then begin the next dependent Core.

## 5. Current acceptance baseline

### Core 01 — Prompt & Requirement Model
- Status: **PASS**
- Tested commit: `fe9b606e2c7fa013f86c6842fc2245d2cc414500`
- Environment: GitHub Actions, Ubuntu 26.04, CPython 3.11.18
- Command: `python -m pytest -q`
- Result: **39 passed in 0.06s; 0 failed; 0 skipped**
- CI: https://github.com/msellamiTN/socioweave-studio/actions/runs/44180942457
- Scope limitation: software model acceptance only; no semantic requirement-entailment claim.

### Core 02 — Requirement Extraction
- Status: **PASS — software acceptance; scientific quality evaluation pending**
- Tested commit: `4b4d0b29eb1f6b963662e9f115e67a4db65fd851`
- Environment: GitHub Actions, Ubuntu 26.04, CPython 3.11.18
- Command: `python -m pytest -q`
- Result: **55 passed in 0.07s; 0 failed; 0 skipped**
- CI: https://github.com/msellamiTN/socioweave-studio/actions/runs/44181085215
- Scope limitation: no benchmark precision/recall/F1, span entailment, hypothesis quality, extractor correlation or T4 profiling has been established.

### Core 03 — Decomposition Model
- Status: **PASS — software model acceptance**
- Tested commit: `d8160ed2f2211c964d51a4ef5ec08beecac7bd0a`
- Environment: GitHub Actions, Ubuntu 26.04, CPython 3.11.18
- Command: `python -m pytest -q`
- Result: **75 passed in 0.12s; 0 failed; 0 skipped**
- CI: https://github.com/msellamiTN/socioweave-studio/actions/runs/44185214955
- Scope limitation: representation and reference integrity only; V1/V2/V5 validity and V3/V4 execution-dependent correctness are handled by Core 04.

### Core 04 — Decomposition Validity Checks
- Status: **PASS — structural validation software acceptance**
- Tested commit: `346946bdee8bad31bbddbc23f82df36dc00900f6`
- Environment: GitHub Actions, Ubuntu 26.04, CPython 3.11.18
- Command: `python -m pytest -q`
- Result: **86 passed in 0.12s; 0 failed; 0 skipped**
- CI: https://github.com/msellamiTN/socioweave-studio/actions/runs/44185812190
- Scope limitation: V1/V2/V5 and hypothesis verdict checks are structural; V3/V4 remain NOT_EVALUATED without executor evidence.

### Core 05 — Algorithm 1 Structural Repair
- Status: **PASS — software repair-policy acceptance**
- Tested commit: `b9efe9d40d85ed44d356a6bc312283ddf82d3aa7`
- Environment: GitHub Actions, Ubuntu 26.04, CPython 3.11.18
- Command: `python -m pytest -q`
- Result: **96 passed in 0.09s; 0 failed; 0 skipped**
- CI: https://github.com/msellamiTN/socioweave-studio/actions/runs/44186324292
- Scope limitation: cycle repair and one injected repair callback only; no empirical effectiveness or execution-dependent V3/V4 validation.

### Core 06 — Execution Evidence for V3/V4
- Status: **PASS — execution evidence contract acceptance**
- Tested commit: `0194fb0efc7d696de99527c6d61b41bd098a70a0`
- Environment: GitHub Actions, Ubuntu 26.04, CPython 3.11.18
- Command: `python -m pytest -q`
- Result: **108 passed in 0.14s; 0 failed; 0 skipped**
- CI: https://github.com/msellamiTN/socioweave-studio/actions/runs/44186672952
- Scope limitation: validates supplied executor/verifier evidence consistency; it does not independently prove actual execution or semantic truth.

### Core 07 — Social Strategy Model
- Status: **PASS — formal strategy model software acceptance**
- Tested commit: `610c372a3e9d147c9f6a60c4afd376c1d16e4c10`
- Environment: GitHub Actions, Ubuntu 26.04, CPython 3.11.18
- Command: `python -m pytest -q`
- Result: **123 passed in 0.17s; 0 failed; 0 skipped**
- CI: https://github.com/msellamiTN/socioweave-studio/actions/runs/44187108609
- Scope limitation: strategy specification only; runtime execution, visibility enforcement, decision rules and strategy selection remain future work.

### Core 08 — Strategy Runtime
- Status: **PASS — visibility-aware protocol runtime acceptance**
- Tested commit: `23045d97814994c7f448db97b6c86eeb5c75052f`
- Environment: GitHub Actions, Ubuntu 26.04, CPython 3.11.18
- Command: `python -m pytest -q`
- Result: **134 passed in 0.22s; 0 failed; 0 skipped**
- CI: https://github.com/msellamiTN/socioweave-studio/actions/runs/44187520064
- Scope limitation: serial protocol dispatch with stage visibility snapshots; no parallel latency claim, decision-rule implementation or strategy effectiveness result.

### Core 09 — Decision Operators and Strategy Catalogue
- Status: **PASS — decision operators and catalogue software acceptance**
- Tested commit: `724ab490169c453f09e18765e814014ae386f950`
- Environment: GitHub Actions, Ubuntu 26.04, CPython 3.11.18
- Command: `python -m pytest -q`
- Result: **148 passed in 0.21s; 0 failed; 0 skipped**
- CI: https://github.com/msellamiTN/socioweave-studio/actions/runs/44188545307
- Scope limitation: pure operators/catalogue; LLM-mediated synthesis, compromise and authority are explicit injected outcomes; no end-to-end strategy effectiveness claim.

The next dependent unit may start only after the current Core's exact tested commit and acceptance report are published.

### Core 10 — Adaptive Strategy Selector
- Status: **PASS — software acceptance**
- Implementation: `engine/sociodec/selector.py`
- Tests: `engine/tests/test_selector.py`
- Specification: `docs/CORE-10-ADAPTIVE-STRATEGY-SELECTOR.md`
- Scope: Table 8 decision list, feature diagnosis from extraction and two supplied drafts, budget-aware chain planning and failure-based escalation planning.
- Tested commit: `b57a0c89b8e0bd11948300794e4d567f16b81f1d`
- Environment: GitHub Actions, Ubuntu latest runner, CPython 3.11
- Command: `python -m pytest -q`
- Result: **176 passed in 0.27s; 0 failed; 0 skipped**
- CI: https://github.com/msellamiTN/socioweave-studio/actions/runs/44189680999
- Scope limitation: deterministic planner acceptance only; semantic flags, seed-adjusted cost accounting and full dynamic Algorithm 2 orchestration remain documented limitations.


### Core 11 — End-to-End Adaptive Orchestrator
- Status: **PASS — software orchestration acceptance**
- Implementation: `engine/sociodec/orchestrator.py`
- Tests: `engine/tests/test_orchestrator.py`
- Specification: `docs/CORE-11-ADAPTIVE-ORCHESTRATOR.md`
- Scope: extraction-once, two initial drafts, feature diagnosis, checked union, sequential strategy adapters, initial/chain seeds, Algorithm 1 repair, budget checks, escalation, best-result comparison and trace.
- Exact tested code commit: `87ef835854c11bdc5574bcb54cd88091b321fd61`
- Environment: GitHub Actions, Ubuntu latest runner, CPython 3.11
- Command: `python -m pytest -q`
- Result: **186 passed in 0.36s; 0 failed; 0 skipped**
- CI: https://github.com/msellamiTN/socioweave-studio/actions/runs/44192309216
- Scope limitation: adapter-backed orchestration is accepted; provider-backed concrete strategy adapters and executor-backed V3/V4 evidence remain separate integration and scientific-validation gates.


### Core 12 — Concrete Strategy Adapter Layer
- Status: **PASS — software protocol-adapter acceptance**
- Protocol blueprints: `engine/sociodec/strategy_protocols.py` (all 13 established strategies; C1–C5 excluded)
- Runtime bridge: `engine/sociodec/strategy_adapter.py`
- Runtime visibility enforcement: `engine/sociodec/runtime.py`
- Tests: `engine/tests/test_strategy_protocols.py`, `engine/tests/test_strategy_adapter.py`
- Specification: `docs/CORE-12-STRATEGY-ADAPTERS.md`
- Exact tested code commit: `3f846916f5074440961734b51ae47cb48b5d4f76`
- Environment: GitHub Actions, Ubuntu latest runner, CPython 3.11
- Command: `python -m pytest -q`
- Result: **230 passed in 0.26s; 0 failed; 0 skipped**
- CI: https://github.com/msellamiTN/socioweave-studio/actions/runs/44193875908
- Boundaries: provider-specific structured decoding, bounded early stopping, composition executors and the scientific benchmark campaign remain separate gates.


### Core 13 — Typed Protocol Output Decoding
- Status: **PASS — software decoding acceptance**
- Implementation: `engine/sociodec/protocol_decoding.py`
- Tests: `engine/tests/test_protocol_decoding.py`
- Specification: `docs/CORE-13-TYPED-PROTOCOL-DECODING.md`
- Scope: strict JSON decoding for candidate decompositions, requirement/constraint references, dependencies, kappa, objections, rankings, ballots, judge outputs, summaries, partitions and hypothesis verdicts.
- Exact tested code commit: `64c6cd323d95c6f2d9506469536c1e1c0fb7f3b5`
- Environment: GitHub Actions, Ubuntu latest runner, CPython 3.11
- Command: `python -m pytest -q`
- Result: **241 passed in 0.43s; 0 failed; 0 skipped**
- CI: https://github.com/msellamiTN/socioweave-studio/actions/runs/44194445943
- Boundary: decision application, structural validity and execution evidence remain separate gates.


### Core 14 — Strategy Decision Assembly
- Status: **IMPLEMENTED — acceptance pending exact-commit CI**
- Implementation: `engine/sociodec/strategy_decoding.py`; default-wired in `engine/sociodec/strategy_adapter.py`
- Tests: `engine/tests/test_strategy_decoding.py`
- Specification: `docs/CORE-14-STRATEGY-DECISION-ASSEMBLY.md`
- Scope: typed decision resolution for all established strategies; S11 and S13 require explicit adjudication because the current protocol outputs do not encode a negotiated decomposition or final authority selection.
- Acceptance gate: full integrated suite, zero skipped tests, exact-commit CI. No semantic correctness claim follows from software conformance.
