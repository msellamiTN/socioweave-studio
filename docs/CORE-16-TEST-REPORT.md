# Core 16 — Test Report

**Status:** PASS — experiment-harness software acceptance. No scientific experiment results are claimed.

## Tested implementation

- Commit: `deb34f2cb9fc0e99078b384352ddca149ece98e5`
- CI run: https://github.com/msellamiTN/socioweave-studio/actions/runs/44198780523
- Environment: GitHub Actions, Ubuntu latest runner, CPython 3.11.18, pytest 9.2.0
- Install: `python -m pip install -e ".[dev]"`
- Command: `python -m pytest -q`
- Result: **282 passed in 0.30s; 0 failed; 0 skipped.**

## Tested contracts

- Stable canonical configuration and prompt fingerprints.
- Stable, distinct per-example/per-repeat seed derivation.
- Trial records preserve configuration identity, dataset/example identity, trace, metrics and metadata.
- Individual adapter failures are recorded and do not abort remaining repeats.
- Dataset mismatch, duplicate examples, malformed rows, missing identifiers and expected-count mismatch are rejected.
- Dataset snapshot and dependency-lock byte fingerprints are recorded in CampaignManifest.
- JSONL export is parseable and row-counted.

## Limitations

- No real LLM provider, executor, or benchmark dataset snapshot was invoked.
- No extraction precision/recall/F1, decomposition metrics, utility, cost, latency or statistical significance values were measured.
- Dataset acquisition and license review remain user-controlled; no benchmark data is redistributed.
- Hosted model inference may remain nondeterministic despite recorded seeds and config hashes.
