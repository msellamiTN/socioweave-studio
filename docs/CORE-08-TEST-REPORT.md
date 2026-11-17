# Core 08 — Strategy Runtime Test Report

**Acceptance status:** PASS — visibility-aware protocol runtime software acceptance  
**Exact tested commit:** `23045d97814994c7f448db97b6c86eeb5c75052f`  
**CI run:** [44187520064](https://github.com/msellamiTN/socioweave-studio/actions/runs/44187520064)  
**Job:** `test` — completed successfully  
**Environment:** GitHub Actions, Ubuntu 26.04 runner, CPython 3.11.18, pytest 9.2.0  
**Install:** `python -m pip install -e ".[dev]"`  
**Test command:** `python -m pytest -q`  
**Result:** **134 passed in 0.22s; 0 failed; 0 skipped.**

## Verified scope

The full integrated suite passed, including:
- protocol dispatch through an injected invoker;
- per-agent prompt views and initial input resolution;
- round-specific visibility filtering;
- stage snapshots preventing peer-output leakage within the same stage;
- own-output visibility;
- author anonymisation;
- hypothesis propagation into every protocol context;
- seed adoption for one agent's first round-1 draft without a model call;
- non-model steps using caller-supplied precomputed outputs;
- exact model-call and stage-depth accounting;
- rejection of unknown agents, seeds, prompt views and input references;
- rejection of same-stage peer output references;
- empty invoker response handling;
- Core 01–07 regression and integration coverage.

## Scientific boundaries

The runtime follows Definition 10 and Algorithm 1's protocol loop. The injected invoker is the boundary to model/provider calls. Stage snapshots preserve the visibility semantics for steps that the paper treats as parallel.

For deterministic reproducibility, this implementation dispatches steps serially even within the same stage. It preserves stage information and information-flow isolation but does not claim parallel execution or latency equal to depth(σ). It does not apply decision rule ω, build the final decomposition, repair failures or select strategies.

## Decision

Core 08 meets the software acceptance gate on the exact commit above. The complete integrated suite passed with no failures or skips. It is accepted as a visibility-aware protocol dispatcher, not as evidence of strategy effectiveness or runtime parallel performance.
