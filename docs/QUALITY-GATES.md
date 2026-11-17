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
- Tested commit: `227df9591d4b1ca5df77e723f351fc51cff1272e`
- Environment: GitHub Actions, Ubuntu 26.04, CPython 3.11.18
- Command: `python -m pytest -q`
- Result: **85 passed in 0.09s; 0 failed; 0 skipped**
- CI: https://github.com/msellamiTN/socioweave-studio/actions/runs/44185641067
- Scope limitation: V1/V2/V5 and hypothesis verdict checks are structural; V3/V4 remain NOT_EVALUATED without executor evidence.

The next dependent unit may start only after the current Core's exact tested commit and acceptance report are published.