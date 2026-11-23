# T4 small-model execution profile

**Status:** engineering smoke implementation; not a scientific campaign  
**Default model:** `Qwen/Qwen2.5-1.5B-Instruct`, 4-bit NF4  
**Notebook:** `notebooks/colab/SOCIOWEAVE_T4_SmallModel_CoreSmoke.ipynb`

## Purpose

This profile provides a low-cost, single-GPU path for exercising the existing SocioDec core. It is intended to catch integration errors before any benchmark campaign or provider spend.

The runtime executes:

1. Load one local quantized Hugging Face model.
2. Run three requirement extractors (`q=3`) using distinct generation seeds but the same model family.
3. Parse typed requirements, implicit hypotheses, entities, ambiguities and conflicts.
4. Aggregate extractor outputs using the existing conservative union/deduplication implementation.
5. Construct the typed prompt interpretation.
6. Ask the model for a structured decomposition and parse it into `D=(S,E,κ)`.
7. Validate V1 coverage, V2 acyclicity, V5 composition and hypothesis verdict completeness.
8. Exercise metric calculation and the existing decision operators in the notebook.
9. Save a JSON engineering report with the model, runtime, call count and validation states.

V3 solvability and V4 faithfulness remain `NOT_EVALUATED` because this smoke profile does not configure a task executor or a faithfulness evaluator. Token usage in the current core report covers the decomposition call only; extraction-token accounting is not yet exposed by the ExtractionResult contract.

## What this does not claim

- It does not execute the paper's E1–E9 experiments.
- It does not reproduce the paper's MA/MB/MC model-family assignment or fixed ME executor.
- The three extractors are same-family calls, not independent model families.
- It does not use the paper's frozen 460-prompt benchmark snapshot.
- It does not provide benchmark-quality annotations, reference agreement, human ratings or inferential statistics.
- A structurally valid generated decomposition is not proof of semantic correctness.

All outputs are labelled `engineering_smoke_only` and `scientific_result=false`.

## E1–E9 readiness boundary

| Experiment | Small-model engineering support | Scientific execution status |
|---|---|---|
| E1 | Core extraction/decomposition and structural checks can be exercised on a supplied prompt | Blocked: five approved frozen datasets, all strategy/baseline runners, fixed executor and complete metrics are not connected |
| E2 | Prompt feature extraction fields can be inspected in the core output | Not run: paper prompt-case tagging, feature-stratified benchmark analysis and process-gain comparison are not implemented end to end |
| E3 | The same core can be invoked on domain-specific prompts | Not run: benchmark domain allocation and domain-level paired analysis are not frozen |
| E4 | Homogeneous single-model path is smoke-testable | Not run: a single small model cannot test heterogeneous versus homogeneous model-family effects or error correlation |
| E5 | T4 memory and call-count instrumentation can be smoke-tested | Not run: complete strategy execution across `n∈{2,3,5}`, `T∈{1,2,3}` and utility/cost/depth curves is not connected |
| E6 | Existing structural validators can detect selected structural defects | Not run: seeded defect corpus and critic/reviewer/judge recall and precision pipeline are not connected |
| E7 | Existing decision operators can be exercised by the notebook | Not run: controlled same-draft comparisons with paper-aligned coverage, redundancy and validity reporting are not connected |
| E8 | Strategy catalogue and decision operators can be smoke-tested | Not run: C1–C8 composition runners and equal-budget comparisons are not connected |
| E9 | Seeds and prompt paraphrases can be supplied to repeated core calls | Not run: agent-order permutations and stability analysis of the strategy outputs are not connected |

The table deliberately distinguishes a core code-path smoke test from the actual experiment described in Table 14.

## Reproducibility

The Colab notebook checks for an NVIDIA T4 and pins the source commit containing the small-model runtime. It installs the engine's `local` and `dev` extras. The generated report is saved under:

```text
/content/socioweave-t4-core-smoke/artifacts/t4_small_model_core_smoke.json
```

The model revision is currently left configurable rather than hard-coded to an unverified Hub commit. Before comparing runs, pin the exact model revision, Transformers/PyTorch/bitsandbytes versions, and record the downloaded model artifact identity.

## Next engineering gates

1. Complete strategy protocol executors for all thirteen Table 4 strategies; preserve role assignments, visibility and decision semantics.
2. Connect the six paper baselines with matched call budgets.
3. Add a fixed executor interface and explicit V3/V4 evaluation contracts.
4. Implement dataset-native semantic reference validators for all five datasets.
5. Implement E2–E9 runners against the exact factors in Table 14.
6. Add campaign checkpoint/resume, provider-call/token/cost accounting, and full extraction-token tracing.
7. Only then enable a benchmark-backed E1 campaign after the dataset rights and snapshot gates pass.

The small-model profile is an engineering aid. It must never be substituted for the paper's scientific model matrix or reported as evidence for the paper's hypotheses.
