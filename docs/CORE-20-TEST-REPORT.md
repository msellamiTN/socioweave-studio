# Core 20 Test Report

## Scope
Fixed-executor identity contract, execution evidence integration with Core 15, V3/V4 propagation, decomposition metrics, optional utility scoring and trial outcome construction.

## Test coverage
- Executor identity mismatch fails before execution.
- Valid execution evidence yields V3/V4/full validity.
- Failed execution and violated hard constraint are reflected in metrics.
- Utility is omitted without an independent scorer and rejects invalid scores.
- Cyclic DAG depth fails closed.
- Provider trace and hashed composed-answer metadata are retained without raw answer text.

## Acceptance evidence

- Tested implementation commit: `14357f4f861da1022383325636d2aad03be18283`
- GitHub Actions run: [44202991480](https://github.com/msellamiTN/socioweave-studio/actions/runs/44202991480)
- Environment: GitHub Actions, Ubuntu latest, CPython 3.11.18, pytest 9.2.0
- Command: `python -m pytest -q` from `engine/`
- Result: **314 passed in 0.64s; 0 failed; 0 skipped.**

## Scientific boundary
Software tests do not establish semantic executor quality, verifier independence, benchmark performance or strategy effectiveness. No real benchmark campaign, utility result, strategy ranking or E1–E9 finding is claimed.
