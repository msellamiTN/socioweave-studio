# Core 21 Test Report

## Scope
Provider-backed initial draft decoding, q-extractor aggregation, PromptFactory boundary, Core 11 orchestration composition, Core 20 fixed-executor evaluation and trial outcome metadata.

## Test coverage
- Two independent provider instances receive one initial-draft request each.
- Typed candidate output is decoded against extracted requirements and prompt constraints.
- Invalid provider JSON fails closed.
- q extractors aggregate through the paper-aligned union/dedup path.
- End-to-end trial adapter runs orchestration and fixed-executor evaluation.
- PromptFactory cannot mutate the benchmark prompt text.
- Campaign policy validates minimum call budget.

## Acceptance evidence

- Tested implementation commit: `7df05b583c20a304f35985cdd452476ee4412565`
- GitHub Actions run: [44203533011](https://github.com/msellamiTN/socioweave-studio/actions/runs/44203533011)
- Environment: GitHub Actions, Ubuntu latest, CPython 3.11.18, pytest 9.2.0
- Command: `python -m pytest -q` from `engine/`
- Result: **320 passed in 0.57s; 0 failed; 0 skipped.**

## Scientific boundary
Unit tests use fake providers and executor fixtures. They establish integration behavior only; they do not establish hosted-model output quality, model independence, verifier correctness or strategy effectiveness. No real benchmark campaign, utility result, strategy ranking or E1–E9 finding is claimed.
