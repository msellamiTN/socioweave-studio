# Core 16 — Reproducible Experiment Harness

**Status:** IN PROGRESS — software acceptance pending.  
**Scientific basis:** Section 8 experimental protocol and E1–E9; supplementary engineering telemetry is recorded separately from paper metrics.

## Objective

Provide a reproducible campaign substrate without downloading data or invoking models implicitly. Dataset snapshots and trial execution are injected and explicit.

## Components

- `sociodec.experiments`: typed experiment configuration, canonical SHA-256 config/prompt fingerprints, stable per-example/per-repeat seeds, trial contexts/outcomes/records, failure capture and JSONL export.
- `sociodec.datasets`: registry for BREAK, StrategyQA, TaskBench, TravelPlanner and the author-curated smart-administration set; strict local JSONL loader with version, split, count and duplicate checks.
- `tests/test_experiments.py`, `tests/test_datasets.py`: validation, determinism, provenance, failure isolation and export contracts.

## Paper defaults represented

- Five repeats per configuration.
- n=3 agents, k=3 experts, T<=2 rounds.
- Draft temperature 0.7; critique/review 0.2; decision 0.0.
- 1024 decomposition tokens; 512 other-stage tokens.
- Executor model is a separately named fixed configuration field.

These are defaults/configuration fields, not proof that an actual campaign used them. Dataset sample counts, annotator protocol and statistical tests must be explicitly configured in subsequent evaluation tooling; no benchmark results are fabricated here.

## Reproducibility contract

Each trial records experiment/config hash, dataset and source version via prompt hash, example ID, repeat index, derived seed, status, metrics, provider trace, metadata and failure text. The campaign continues after per-trial failures. Provider traces should include model/provider, role/stage, token counts, latency, request IDs and generation settings when available.

A seed makes seed assignment reproducible; it does not guarantee deterministic hosted inference. A config hash identifies the recorded config; it does not freeze external model revisions, dataset contents, provider behavior or runtime libraries. Preserve dataset snapshot hashes and environment/lockfile information alongside exports.

## Dataset governance

No benchmark content is redistributed by this Core. Users must obtain each dataset under its own terms, record its exact snapshot/version and selected split, and review licensing/usage restrictions before running. The smart-administration set is identified as author-curated and must be versioned separately.

## Out of scope

No actual E1–E9 runs, human gold annotations, metric computation, significance tests, effect-size estimates, model downloads or provider calls are performed by this Core. Those belong to subsequent evaluation implementation and campaign execution.
