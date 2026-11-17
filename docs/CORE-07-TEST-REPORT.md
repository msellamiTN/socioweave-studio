# Core 07 — Social Strategy Model Test Report

**Acceptance status:** PASS — formal strategy model software acceptance  
**Exact tested commit:** `610c372a3e9d147c9f6a60c4afd376c1d16e4c10`  
**CI run:** [44187108609](https://github.com/msellamiTN/socioweave-studio/actions/runs/44187108609)  
**Job:** `test` — completed successfully  
**Environment:** GitHub Actions, Ubuntu 26.04 runner, CPython 3.11.18, pytest 9.2.0  
**Install:** `python -m pip install -e ".[dev]"`  
**Test command:** `python -m pytest -q`  
**Result:** **123 passed in 0.17s; 0 failed; 0 skipped.**

## Verified scope

The full integrated suite passed, including:
- Definition 9 agent identity, model, context and optional memory;
- homogeneous versus heterogeneous model identity;
- all paper-listed roles, actions and decision rules;
- total role assignment α for every agent and round;
- per-round visibility relations and mandatory self-visibility;
- first-round independence detection;
- anonymity flag;
- protocol agent/action/input/round/stage contracts;
- explicit model-call accounting and sequential depth;
- role stability versus role rotation;
- negative tests for invalid agents, roles, assignments, visibility and protocol definitions;
- Core 01–06 regression and integration coverage.

## Scientific boundaries

The implementation models Definitions 9 and 10 and the paper's derived strategy descriptors. The `stage` and `invokes_model` fields are explicit software representation choices used to compute calls(σ) and depth(σ); they are not additional scientific claims.

This Core does not execute agents, enforce visibility at runtime, implement decision rules, estimate prompt features or select strategies. It does not claim that a strategy improves decomposition quality.

## Decision

Core 07 meets the software acceptance gate on the exact commit above. The complete integrated suite passed with no failures or skips. The model is ready to serve as the specification for the strategy execution core.
