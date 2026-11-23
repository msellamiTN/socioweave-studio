"""First Web Studio API slice: read-only catalogue and safe config preview.

This service deliberately does not launch provider calls or experiments. Its
preview is a budget/configuration calculation, not the engine's full E1
campaign preflight and not evidence that a dataset snapshot is valid.
"""
from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from sociodec.catalogue import STRATEGIES, get_strategy
from sociodec.datasets import DATASET_REGISTRY
from sociodec.e1_protocol import ALL_DATASETS, BASELINES, MODEL_MODES


class ConfigPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: str
    datasets: list[str] = Field(min_length=1)
    model_mode: Literal["homogeneous", "heterogeneous"]
    n: int = Field(default=3, ge=1, le=12)
    k: int = Field(default=3, ge=1, le=12)
    T: int = Field(default=2, ge=1, le=10)
    seed_indices: list[int] = Field(default_factory=lambda: [0], min_length=1)


app = FastAPI(
    title="SOCIOWEAVE Studio API",
    version="0.1.0",
    description="Research configuration preview; execution remains disabled.",
)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "socioweave-studio-api"}


@app.get("/api/v1/capabilities")
def capabilities() -> dict[str, object]:
    return {
        "api_version": "v1",
        "configuration_preview": True,
        "dataset_catalogue": True,
        "full_e1_preflight": False,
        "run_launch": False,
        "provider_execution": False,
        "live_provider_calls_enabled": False,
        "evidence_state": "CODE_CI_ONLY",
    }


@app.get("/api/v1/datasets")
def datasets() -> dict[str, object]:
    return {
        "datasets": [
            {
                "id": dataset_id,
                "expected_prompts": expected,
                "metadata": DATASET_REGISTRY[dataset_id],
            }
            for dataset_id, expected in (
                ("BREAK", 100),
                ("StrategyQA", 100),
                ("TaskBench", 100),
                ("TravelPlanner", 100),
                ("smart-administration", 60),
            )
        ]
    }


@app.post("/api/v1/config-previews")
def create_config_preview(request: ConfigPreviewRequest) -> dict[str, object]:
    if request.strategy_id not in {item.identifier.value for item in STRATEGIES}:
        raise HTTPException(status_code=422, detail="strategy_id must identify a registered paper strategy")
    if len(request.datasets) != len(set(request.datasets)):
        raise HTTPException(status_code=422, detail="datasets must not contain duplicates")
    unknown = sorted(set(request.datasets) - set(ALL_DATASETS))
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown datasets: {unknown}")
    if any(isinstance(seed, bool) or seed < 0 or seed > 4 for seed in request.seed_indices):
        raise HTTPException(status_code=422, detail="seed_indices must be selected from the E1 indices 0 through 4")
    if len(request.seed_indices) != len(set(request.seed_indices)):
        raise HTTPException(status_code=422, detail="seed_indices must not contain duplicates")

    strategy = get_strategy(request.strategy_id)
    method_calls_per_prompt = strategy.calls(n=request.n, k=request.k, T=request.T)
    expected_prompts = {
        "BREAK": 100,
        "StrategyQA": 100,
        "TaskBench": 100,
        "TravelPlanner": 100,
        "smart-administration": 60,
    }
    prompt_count = sum(expected_prompts[item] for item in request.datasets)
    condition_count = len(request.datasets) * len(request.seed_indices)
    return {
        "schema_version": "studio-config-preview-v1",
        "readiness": "configuration_preview_only",
        "strategy_id": request.strategy_id,
        "model_mode": request.model_mode,
        "datasets": request.datasets,
        "seed_indices": request.seed_indices,
        "n": request.n,
        "k": request.k,
        "T": request.T,
        "expected_prompt_count": prompt_count,
        "condition_count": condition_count,
        "method_calls_per_prompt": method_calls_per_prompt,
        "estimated_method_calls": prompt_count * method_calls_per_prompt * len(request.seed_indices),
        "fixed_executor_calls": None,
        "note": "Preview only. Dataset snapshot, provider roster, complete matched-baseline grid, fixed executor, token ceiling and full engine preflight are not validated.",
        "blocking_requirements": [
            "operator-supplied frozen five-dataset snapshot and provenance",
            "complete E1 condition grid and matched-baseline budgets",
            "provider roster and immutable model revisions",
            "fixed executor identity and execution protocol",
            "token/cost ceiling and explicit operator authorization",
        ],
        "live_provider_calls": 0,
        "run_launch_enabled": False,
    }
