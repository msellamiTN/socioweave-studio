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
from sociodec.e1_protocol import (
    ALL_DATASETS, BASELINES, MODEL_MODES, build_e1_conditions,
    e1_metric_obligations, validate_e1_manifest,
)
from sociodec.datasets import E1DatasetSource, freeze_e1_benchmark_snapshot


class ConfigPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: str
    datasets: list[str] = Field(min_length=1)
    model_mode: Literal["homogeneous", "heterogeneous"]
    n: int = Field(default=3, ge=1, le=12)
    k: int = Field(default=3, ge=1, le=12)
    T: int = Field(default=2, ge=1, le=10)
    seed_indices: list[int] = Field(default_factory=lambda: [0], min_length=1)


class E1PreflightRequest(BaseModel):
    """Operator-declared local inputs for a zero-call E1 preflight."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    sources: dict[str, dict[str, str | int | None]]
    n: int = Field(default=3, ge=1, le=12)
    k: int = Field(default=3, ge=1, le=12)
    T: int = Field(default=2, ge=1, le=10)


app = FastAPI(
    title="SOCIOWEAVE Studio API",
    version="0.1.0",
    description="Research configuration preview and zero-call E1 dataset/grid preflight; full campaign validation and execution remain disabled.",
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
        "e1_dataset_grid_preflight": True,
        "e1_preflight_mode": "dataset_snapshot_and_condition_grid_only_zero_live_calls",
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



@app.get("/api/v1/strategies")
def strategies() -> dict[str, object]:
    return {
        "strategies": [
            {
                "id": item.identifier.value,
                "name": item.name,
                "call_formula": item.call_formula,
                "depth_formula": item.depth_formula,
                "decision_rule": item.decision_rule,
                "protocol_summary": item.protocol_summary,
            }
            for item in STRATEGIES
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


@app.post("/api/v1/preflights/e1")
def create_e1_preflight(request: E1PreflightRequest) -> dict[str, object]:
    """Freeze operator-supplied local inputs and validate the paper E1 grid.

    This is configuration validation only: no provider/model calls are made.
    """
    if set(request.sources) != set(ALL_DATASETS):
        raise HTTPException(status_code=422, detail="sources must declare exactly the five E1 datasets")

    parsed_sources: dict[str, E1DatasetSource] = {}
    try:
        for dataset_id, raw in request.sources.items():
            allowed = {
                "path", "source_version", "split", "selection_protocol",
                "license_review_status", "selection_seed",
            }
            if set(raw) != allowed:
                raise ValueError(f"{dataset_id} source must provide exactly: {sorted(allowed)}")
            parsed_sources[dataset_id] = E1DatasetSource(**raw)
        snapshot = freeze_e1_benchmark_snapshot(parsed_sources)
        conditions = build_e1_conditions(
            expected_prompt_ids=snapshot.expected_prompt_ids,
            n=request.n, k=request.k, T=request.T,
        )
        errors = validate_e1_manifest(
            conditions, expected_prompt_ids=snapshot.expected_prompt_ids,
            require_complete_grid=True,
        )
    except (TypeError, ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    method_count = sum(1 for row in conditions if row.method_id not in BASELINES)
    return {
        "schema_version": "e1-dataset-grid-preflight-report-v1",
        "preflight_scope": "dataset_snapshot_and_condition_grid_only",
        "readiness": "DATASET_GRID_PREFLIGHT_PASS",
        "evidence_state": "DATASET_GRID_PREFLIGHT_PASS",
        "snapshot_sha256": snapshot.manifest["snapshot_sha256"],
        "snapshot_manifest": snapshot.manifest,
        "dataset_prompt_counts": {
            dataset_id: len(snapshot.expected_prompt_ids[dataset_id])
            for dataset_id in ALL_DATASETS
        },
        "condition_count": len(conditions),
        "method_condition_count": method_count,
        "matched_baseline_condition_count": len(conditions) - method_count,
        "model_modes": list(MODEL_MODES),
        "seed_indices": list(range(5)),
        "strategy_count": len(STRATEGIES),
        "baseline_count": len(BASELINES),
        "metric_obligations": {
            dataset_id: sorted(e1_metric_obligations(dataset_id))
            for dataset_id in ALL_DATASETS
        },
        "grid_errors": list(errors),
        "live_provider_calls": 0,
        "run_launch_enabled": False,
        "blocking_requirements": [
            "complete provider manifest: 38 method/model-mode rosters and immutable model revisions",
            "verified MA/MB/MC family and provider-organization declarations for heterogeneous mode",
            "fixed executor identity and execution protocol",
            "S12 explicit facet prompt-view factory",
            "extractor/human audit evidence and reference annotation review",
            "token/cost ceiling and explicit operator authorization",
            "T4 infrastructure smoke and provider smoke, where required",
        ],
        "note": (
            "The preflight validates local files, declared provenance and license approval, "
            "paper prompt counts, reference-data presence, frozen hashes and the complete "
            "budget-matched E1 condition grid. It does not verify the truth of license or "
            "provider-family declarations, annotation quality, model connectivity, or execution."
        ),
    }


# Serve the operator interface from the same-origin API process. API routes
# are registered first so the static mount cannot shadow versioned endpoints.
from pathlib import Path
from fastapi.staticfiles import StaticFiles

_web_root = Path(__file__).resolve().parents[2] / "web"
if _web_root.is_dir():
    app.mount("/", StaticFiles(directory=_web_root, html=True), name="studio-web")
