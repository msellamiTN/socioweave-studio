"""SOCIOWEAVE Studio API for research preview and no-call E1 validation.

The service exposes a dataset/grid preflight and a separate engine-backed
campaign configuration preflight. Neither endpoint launches providers or
experiments, and neither establishes E1_READY.
"""
from __future__ import annotations

from typing import Any, Literal
import re
import os
import secrets

from fastapi import FastAPI, HTTPException, Request, Header
from pydantic import BaseModel, ConfigDict, Field

from sociodec.catalogue import STRATEGIES, get_strategy
from sociodec.datasets import DATASET_REGISTRY
from sociodec.e1_protocol import (
    ALL_DATASETS, BASELINES, EXPECTED_PROMPTS, MODEL_MODES, build_e1_conditions,
    e1_metric_obligations, validate_e1_manifest,
)
from sociodec.datasets import E1DatasetSource, freeze_e1_benchmark_snapshot
from sociodec.e1_runtime import build_direct_e1_runtime
from sociodec.provider_factory import E1ProviderRegistry, ProviderSpec
from sociodec.experiments import content_hash
from sociodec.jigsaw import (
    PAPER_S12_POLICY_ID, PAPER_S12_POLICY_MANIFEST,
    PAPER_S12_POLICY_SHA256,
)


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


class SnapshotManifestVerificationRequest(BaseModel):
    """Verify an exported snapshot manifest's internal hash and structural consistency."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_manifest: dict[str, Any]


class E1CampaignPreflightRequest(BaseModel):
    """Full no-call campaign configuration inputs; no credentials are accepted."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    sources: dict[str, dict[str, str | int | None]]
    provider_manifest: dict[str, Any]
    s12_prompt_view_factory_id: str = Field(min_length=1, max_length=200)
    s12_prompt_view_factory_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    n: int = Field(default=3, ge=1, le=12)
    k: int = Field(default=3, ge=1, le=12)
    T: int = Field(default=2, ge=1, le=10)


class _NoCallProvider:
    """Identity-only placeholder: deliberately has no generate method."""
    def __init__(self, spec: ProviderSpec) -> None:
        self.model_name = spec.model_id
        self.provider_name = spec.provider_name


def _reject_secret_fields(value: object, path: str = "provider_manifest") -> None:
    forbidden = {"api_key", "secret", "password", "credential", "access_token", "token"}
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in forbidden:
                raise ValueError(f"{path}.{key} is forbidden; supply only a secret environment-variable name")
            _reject_secret_fields(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_secret_fields(item, f"{path}[{index}]")


def _provider_spec_from_manifest(item: dict[str, Any], label: str) -> ProviderSpec:
    if set(item) != {"model_id", "backend", "connection", "provenance"}:
        raise ValueError(f"{label} must contain model_id, backend, connection and provenance")
    connection = item["connection"]
    provenance = item["provenance"]
    connection_fields = {
        "provider_name", "base_url", "api_key_env", "load_in_4bit",
        "max_input_tokens", "timeout_seconds",
    }
    if not isinstance(connection, dict) or set(connection) != connection_fields:
        raise ValueError(f"{label} connection settings are incomplete or contain unsupported fields")
    if not isinstance(connection["provider_name"], str) or not connection["provider_name"].strip():
        raise ValueError(f"{label} provider_name must be non-empty")
    if connection["base_url"] is not None and not isinstance(connection["base_url"], str):
        raise ValueError(f"{label} base_url must be a string or null")
    if connection["api_key_env"] is not None and not isinstance(connection["api_key_env"], str):
        raise ValueError(f"{label} api_key_env must be a string or null")
    if not isinstance(connection["load_in_4bit"], bool):
        raise ValueError(f"{label} load_in_4bit must be boolean")
    if type(connection["max_input_tokens"]) is not int or connection["max_input_tokens"] < 1:
        raise ValueError(f"{label} max_input_tokens must be a positive integer")
    if isinstance(connection["timeout_seconds"], bool) or not isinstance(connection["timeout_seconds"], (int, float)) or connection["timeout_seconds"] <= 0:
        raise ValueError(f"{label} timeout_seconds must be positive")
    if not isinstance(provenance, dict):
        raise ValueError(f"{label} provenance must be an object")
    return ProviderSpec(
        backend=item["backend"],
        model_id=item["model_id"],
        provider_name=connection["provider_name"],
        base_url=connection["base_url"],
        api_key_env=connection["api_key_env"],
        load_in_4bit=connection["load_in_4bit"],
        max_input_tokens=connection["max_input_tokens"],
        timeout_seconds=connection["timeout_seconds"],
        family_id=provenance.get("family_id"),
        provider_org=provenance.get("provider_org"),
        weight_access=provenance.get("weight_access"),
        model_size=provenance.get("model_size"),
        model_revision=provenance.get("model_revision"),
        access_date=provenance.get("access_date"),
    )


def _build_preflight_runtime(manifest: dict[str, Any], *, n: int, k: int, T: int):
    _reject_secret_fields(manifest)
    if set(manifest) != {"schema_version", "model_modes", "model_family_catalogue", "executor"}:
        raise ValueError("provider manifest must contain exactly schema_version, model_modes, model_family_catalogue and executor")
    if manifest.get("schema_version") != "e1-provider-manifest-v1":
        raise ValueError("provider manifest must use schema e1-provider-manifest-v1")
    modes = manifest.get("model_modes")
    if not isinstance(modes, dict) or set(modes) != {"homogeneous", "heterogeneous"}:
        raise ValueError("provider manifest must declare homogeneous and heterogeneous model modes")
    assignments: dict[str, dict[str, ProviderSpec]] = {}
    for mode, roster in modes.items():
        if not isinstance(roster, dict) or not roster:
            raise ValueError(f"{mode} provider roster must be a non-empty object")
        assignments[mode] = {
            agent_id: _provider_spec_from_manifest(item, f"{mode}/{agent_id}")
            for agent_id, item in roster.items()
            if isinstance(item, dict)
        }
        if len(assignments[mode]) != len(roster):
            raise ValueError(f"{mode} provider roster contains a malformed assignment")
    executor_data = manifest.get("executor")
    if not isinstance(executor_data, dict) or set(executor_data) != {
        "executor_id", "model_id", "backend", "connection", "provenance"
    }:
        raise ValueError("provider manifest executor entry is incomplete or contains unsupported fields")
    executor_spec = _provider_spec_from_manifest({
        "model_id": executor_data["model_id"],
        "backend": executor_data["backend"],
        "connection": executor_data["connection"],
        "provenance": executor_data["provenance"],
    }, "executor")
    registry = E1ProviderRegistry(
        assignments=assignments,
        executor=executor_spec,
        provider_builder=_NoCallProvider,
    )
    executor_id = executor_data["executor_id"]
    if not isinstance(executor_id, str) or not executor_id.strip():
        raise ValueError("provider manifest executor_id must be non-empty")
    runtime = build_direct_e1_runtime(
        registry=registry,
        executor_id=executor_id,
        n=n, k=k, T=T,
    )
    # The submitted manifest is the provider-registry manifest. The runtime
    # campaign manifest intentionally adds hash-bound runtime policy metadata
    # (including S12 Jigsaw), so comparing those two different schemas rejects
    # every otherwise canonical provider manifest.
    generated_provider_manifest = registry.campaign_manifest(executor_id=executor_id)
    if generated_provider_manifest != manifest:
        raise ValueError("provider manifest is not canonical for the declared provider roster and connection settings")
    return runtime


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
        "engine_campaign_preflight": True,
        "registered_s12_policy": PAPER_S12_POLICY_ID,
        "e1_dataset_grid_preflight": True,
        "e1_preflight_mode": "dataset_snapshot_and_condition_grid_only_zero_live_calls",
        "engine_campaign_preflight_mode": "direct_e1_runtime_configuration_only_zero_live_calls",
        "run_launch": False,
        "provider_execution": False,
        "live_provider_calls_enabled": False,
        "evidence_state": "CODE_CI_ONLY",
    }


@app.get("/api/v1/datasets")
def datasets() -> dict[str, object]:
    """Return the engine-owned dataset contracts and the Studio evidence boundary.

    This is a catalogue, not a persisted dataset registry: source declarations
    are supplied to preflight requests and are not retained by this service.
    """
    rows = []
    for dataset_id, expected in (
        ("BREAK", 100),
        ("StrategyQA", 100),
        ("TaskBench", 100),
        ("TravelPlanner", 100),
        ("smart-administration", 60),
    ):
        metadata = DATASET_REGISTRY[dataset_id]
        rows.append({
            "id": dataset_id,
            "expected_prompts": expected,
            "metadata": metadata,
            "evidence_contract": {
                "source_identity_required": True,
                "immutable_revision_required": True,
                "split_and_selection_required": True,
                "license_review_required": bool(metadata["license_review_required"]),
                "reference_data_required": bool(metadata["reference_provided"]),
                "evidence_state": "NOT_PERSISTED",
            },
        })
    return {
        "datasets": rows,
        "registry_mode": "engine_catalogue_read_only",
        "evidence_persistence": False,
        "evidence_boundary": (
            "Source declarations are submitted per preflight request and are not persisted "
            "as registry records by Studio. Catalogue metadata is not evidence of source "
            "availability, legal approval, annotation quality or snapshot freeze."
        ),
    }



@app.get("/api/v1/jigsaw/policy")
def jigsaw_policy() -> dict[str, object]:
    """Expose the registered, versioned paper S12 facet policy."""
    return {
        "factory_id": PAPER_S12_POLICY_ID,
        "policy_sha256": PAPER_S12_POLICY_SHA256,
        "policy_manifest": PAPER_S12_POLICY_MANIFEST,
        "source_boundary": (
            "The three-facet grouping follows the paper's goals, constraints and actors example. "
            "Grouping target and deliverable requirements together is an explicit operationalization."
        ),
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


def _verify_snapshot_manifest(manifest: dict[str, Any]) -> dict[str, object]:
    """Check manifest structure and its content-addressed dataset-entry digest.

    This does not access source files or establish source authenticity, rights,
    selection correctness, annotation quality or scientific readiness.
    """
    required_top = {
        "schema_version", "dataset_order", "datasets",
        "total_prompt_count", "snapshot_sha256",
    }
    if set(manifest) != required_top:
        raise ValueError("snapshot manifest must contain exactly the required top-level fields")
    if manifest["schema_version"] != "e1-frozen-benchmark-snapshot-v1":
        raise ValueError("unsupported snapshot manifest schema_version")
    if manifest["dataset_order"] != list(ALL_DATASETS):
        raise ValueError("dataset_order must match the registered E1 dataset order")
    entries = manifest["datasets"]
    if not isinstance(entries, dict) or set(entries) != set(ALL_DATASETS):
        raise ValueError("datasets must contain exactly the five registered E1 datasets")

    total = 0
    for dataset_id in ALL_DATASETS:
        entry = entries[dataset_id]
        if not isinstance(entry, dict):
            raise ValueError(f"{dataset_id} manifest entry must be an object")
        ids = entry.get("prompt_ids")
        prompt_hashes = entry.get("prompt_sha256")
        reference_hashes = entry.get("reference_data_sha256")
        expected = EXPECTED_PROMPTS[dataset_id]
        if not isinstance(ids, list) or len(ids) != expected:
            raise ValueError(f"{dataset_id} must contain exactly {expected} selected prompt IDs")
        if any(not isinstance(item, str) or not item.strip() for item in ids):
            raise ValueError(f"{dataset_id} prompt_ids must be non-empty strings")
        if len(ids) != len(set(ids)):
            raise ValueError(f"{dataset_id} prompt_ids must be unique")
        if not isinstance(prompt_hashes, dict) or set(prompt_hashes) != set(ids):
            raise ValueError(f"{dataset_id} prompt_sha256 keys must match prompt_ids")
        if not isinstance(reference_hashes, dict) or set(reference_hashes) != set(ids):
            raise ValueError(f"{dataset_id} reference_data_sha256 keys must match prompt_ids")
        for label, values in (("prompt_sha256", prompt_hashes), ("reference_data_sha256", reference_hashes)):
            if any(not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None for value in values.values()):
                raise ValueError(f"{dataset_id} {label} values must be lowercase SHA-256 digests")
        if re.fullmatch(r"[0-9a-f]{64}", str(entry.get("source_sha256", ""))) is None:
            raise ValueError(f"{dataset_id} source_sha256 must be a lowercase SHA-256 digest")
        total += len(ids)

    if type(manifest["total_prompt_count"]) is not int or manifest["total_prompt_count"] != total:
        raise ValueError("total_prompt_count does not match the selected prompt IDs")
    declared = manifest["snapshot_sha256"]
    if not isinstance(declared, str) or re.fullmatch(r"[0-9a-f]{64}", declared) is None:
        raise ValueError("snapshot_sha256 must be a lowercase SHA-256 digest")
    computed = content_hash({"datasets": entries})
    if declared != computed:
        raise ValueError("snapshot_sha256 does not match the manifest dataset entries")

    return {
        "schema_version": "studio-snapshot-manifest-verification-v1",
        "verification": "MANIFEST_INTEGRITY_VALID",
        "evidence_state": "HASH_CONSISTENCY_ONLY",
        "snapshot_sha256": computed,
        "dataset_count": len(ALL_DATASETS),
        "total_prompt_count": total,
        "source_files_rechecked": False,
        "live_provider_calls": 0,
        "e1_ready": False,
        "limitations": [
            "This verifies internal manifest structure and its declared content hash only.",
            "It does not re-read source files or independently verify their SHA-256 values.",
            "It does not verify source authenticity, legal permission, selection correctness or annotation quality.",
            "It does not establish E1 readiness or authorize experiment execution.",
        ],
    }


@app.post("/api/v1/snapshots/verify")
def verify_snapshot_manifest(request: SnapshotManifestVerificationRequest) -> dict[str, object]:
    try:
        return _verify_snapshot_manifest(request.snapshot_manifest)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
                "license_review_status", "selection_seed", "source_url",
                "source_revision", "license_url", "license_identifier",
                "license_review_evidence", "license_reviewed_by",
                "license_reviewed_at", "eligible_population_count",
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



@app.post("/api/v1/preflights/e1/campaign")
def create_e1_campaign_preflight(request: E1CampaignPreflightRequest) -> dict[str, object]:
    """Run the engine's complete no-call E1 design/provider preflight.

    This validates frozen inputs, all 4,550 condition rows, all 38 method/mode
    rosters, model-family routing, judge separation, executor identity and the
    declared S12 facet-factory metadata. It never invokes a provider.
    """
    if set(request.sources) != set(ALL_DATASETS):
        raise HTTPException(status_code=422, detail="sources must declare exactly the five E1 datasets")
    parsed_sources: dict[str, E1DatasetSource] = {}
    try:
        for dataset_id, raw in request.sources.items():
            allowed = {
                "path", "source_version", "split", "selection_protocol",
                "license_review_status", "selection_seed", "source_url",
                "source_revision", "license_url", "license_identifier",
                "license_review_evidence", "license_reviewed_by",
                "license_reviewed_at", "eligible_population_count",
            }
            if set(raw) != allowed:
                raise ValueError(f"{dataset_id} source must provide exactly: {sorted(allowed)}")
            parsed_sources[dataset_id] = E1DatasetSource(**raw)
        snapshot = freeze_e1_benchmark_snapshot(parsed_sources)
        conditions = build_e1_conditions(
            expected_prompt_ids=snapshot.expected_prompt_ids,
            n=request.n, k=request.k, T=request.T,
        )
        runtime = _build_preflight_runtime(
            request.provider_manifest, n=request.n, k=request.k, T=request.T,
        )
        if request.s12_prompt_view_factory_id != runtime.jigsaw_policy_id:
            raise ValueError("S12 factory ID does not match the registered engine policy")
        if request.s12_prompt_view_factory_sha256 != runtime.jigsaw_policy_sha256:
            raise ValueError("S12 factory SHA-256 does not match the registered engine policy")
        report = runtime.preflight_campaign(snapshot=snapshot, conditions=conditions)
    except (TypeError, ValueError, OSError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    runtime_campaign_manifest = runtime.campaign_manifest()
    return {
        "schema_version": "e1-campaign-configuration-preflight-v1",
        "runtime_campaign_manifest": runtime_campaign_manifest,
        "runtime_campaign_manifest_sha256": content_hash(runtime_campaign_manifest),
        "readiness": "CAMPAIGN_CONFIGURATION_PREFLIGHT_PASS",
        "evidence_state": "CAMPAIGN_CONFIGURATION_PREFLIGHT_PASS",
        "e1_ready": False,
        "preflight_scope": "engine_dataset_grid_provider_roster_model_family_judge_executor_s12_declaration",
        "engine_report": report.as_dict(),
        "dataset_prompt_counts": {
            dataset_id: len(snapshot.expected_prompt_ids[dataset_id])
            for dataset_id in ALL_DATASETS
        },
        "condition_count": report.condition_count,
        "provider_rosters_validated": report.provider_rosters_validated,
        "model_modes": list(report.model_modes),
        "s12_prompt_view_factory": {
            "factory_id": report.jigsaw_policy_id,
            "policy_sha256": report.jigsaw_policy_sha256,
            "registered_builtin": report.jigsaw_policy_id == PAPER_S12_POLICY_ID,
            "callback_executed_during_preflight": False,
            "policy_manifest": PAPER_S12_POLICY_MANIFEST,
        },
        "live_provider_calls": 0,
        "run_launch_enabled": False,
        "remaining_evidence_gates": [
            "Independent verification of upstream dataset authenticity, licensing rights and prompt selection",
            "S12 per-prompt facet-generation audit against the frozen extraction bundles; policy unit tests do not replace the required 20% human extraction audit",
            "Extractor quality audit and practitioner/human review of reference annotations",
            "Operator-approved token, cost and concurrency ceilings",
            "Actual Colab T4 infrastructure smoke and separately authorized provider smoke",
            "Preregistered paired statistical analysis and failure-accounting protocol",
            "Production security, filesystem sandboxing, authentication and worker isolation",
        ],
        "note": (
            "The engine campaign preflight validates configuration and routing consistency with zero live calls. "
            "The registered S12 policy is hash-bound, but the prompt-specific facet callback is not executed during preflight. "
            "It does not verify the external truth of provider-family declarations, validate annotation quality, "
            "run a model, authorize a campaign, or establish E1_READY."
        ),
    }


class EvidenceAttestationRequest(BaseModel):
    """A self-reported operator claim; not an approval or authenticated identity."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    actor_claim: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=500)
    payload: dict[str, Any]


def _require_evidence_write_token(authorization: str | None) -> None:
    configured = os.environ.get("SOCIOWEAVE_EVIDENCE_WRITE_TOKEN")
    if not configured:
        raise HTTPException(status_code=503, detail="Evidence writes are disabled: configure a per-instance write token before use")
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not secrets.compare_digest(supplied, configured):
        raise HTTPException(status_code=401, detail="Evidence write authorization failed")


def _reject_evidence_secrets(value: object, path: str = "payload") -> None:
    forbidden = {"api_key", "secret", "password", "credential", "access_token", "token"}
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in forbidden:
                raise HTTPException(status_code=422, detail=f"{path}.{key} is not accepted")
            _reject_evidence_secrets(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_evidence_secrets(item, f"{path}[{index}]")


@app.get("/api/v1/evidence/status")
def evidence_status() -> dict[str, object]:
    return {
        "schema_version": "studio-evidence-capabilities-v1",
        "ledger": "local_sqlite_hash_chain",
        "blob_archive": "local_content_addressed_sha256",
        "write_enabled": bool(os.environ.get("SOCIOWEAVE_EVIDENCE_WRITE_TOKEN")),
        "authentication": "single_shared_bearer_token" if os.environ.get("SOCIOWEAVE_EVIDENCE_WRITE_TOKEN") else "not_configured",
        "multi_user_authorization": False,
        "external_trusted_checkpoint": False,
        "operator_attestations": "self_reported_not_independently_verified",
        "source_blob_max_bytes": 10485760,
        "execution_enabled": False,
    }


@app.post("/api/v1/evidence/events")
def append_evidence_event(
    request: EvidenceAttestationRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    _require_evidence_write_token(authorization)
    _reject_evidence_secrets(request.payload)
    from socioweave_studio.api.evidence_store import append_event
    try:
        event = append_event(
            actor_claim=request.actor_claim,
            event_type="operator_attestation",
            subject=request.subject,
            payload=request.payload,
        )
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "event": event,
        "interpretation": "self-reported operator attestation; identity and truth were not independently verified",
    }


@app.get("/api/v1/evidence/ledger/verify")
def verify_evidence_ledger() -> dict[str, object]:
    from socioweave_studio.api.evidence_store import verify_ledger
    return verify_ledger()


@app.put("/api/v1/evidence/blobs/{expected_sha256}")
async def archive_evidence_blob(
    expected_sha256: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    _require_evidence_write_token(authorization)
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="source blob exceeds 10 MiB limit")
        chunks.append(chunk)
    content = b"".join(chunks)
    from socioweave_studio.api.evidence_store import store_blob
    try:
        return store_blob(expected_sha256, content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/evidence/blobs/{expected_sha256}/verify")
def verify_evidence_blob(expected_sha256: str) -> dict[str, object]:
    from socioweave_studio.api.evidence_store import verify_blob
    try:
        return verify_blob(expected_sha256)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# Serve the operator interface from the same-origin API process. API routes
# are registered first so the static mount cannot shadow versioned endpoints.
from pathlib import Path
from fastapi.staticfiles import StaticFiles

_web_root = Path(__file__).resolve().parents[2] / "web"
if _web_root.is_dir():
    app.mount("/", StaticFiles(directory=_web_root, html=True), name="studio-web")
