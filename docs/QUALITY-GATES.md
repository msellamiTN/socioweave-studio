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

## 5. Current baseline

Core 01 — Prompt & Requirement Model: previously committed tests exist; a separate full acceptance run still needs to be recorded against its final integrated commit.

Core 02 — Requirement Extraction:
- Commit tested: `72f965bb99b47972d72d89bb4da20b2a2b96ee98`
- Environment: GitHub Actions, Ubuntu 26.04, CPython 3.11.18
- Command: `python -m pytest -q`
- Result: **15 passed in 0.04s**
- CI run: https://github.com/msellamiTN/socioweave-studio/actions/runs/44179656788
- Scope: currently includes the prompt-model and extraction tests present at that commit.
- Limitation: this is a passing automated test baseline, not yet a full semantic evaluation of LLM extraction accuracy, source-span entailment, extractor independence or benchmark performance.

Core 02 is therefore **unit-test green**, but its broader scientific evaluation remains pending. Future Core work is gated by the complete test suite defined above.
