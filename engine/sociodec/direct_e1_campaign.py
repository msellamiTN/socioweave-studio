"""Resumable provider-backed runner for preregistered direct E1 conditions.

The runner is deliberately adapter-injected: it does not download datasets,
invent prompt interpretations, select strategies, or silently retry failed
trials. Every condition is executed independently through direct_e1.py.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping

from sociodec.direct_e1 import (
    DirectE1Result, DirectMethodAdapter, E1FixedExecutor, run_direct_e1_condition,
)
from sociodec.e1_protocol import BASELINES, E1Condition
from sociodec.experiments import BenchmarkPrompt, content_hash
from sociodec.datasets import DATASET_REGISTRY
from sociodec.extraction import AggregatedExtraction
from sociodec.models.prompt import Prompt


PromptFactory = Callable[[BenchmarkPrompt], Prompt]
ExtractionFactory = Callable[[Prompt], AggregatedExtraction]
MethodFactory = Callable[[E1Condition, Prompt, AggregatedExtraction], DirectMethodAdapter]
UtilityScorer = Callable[[Prompt, str], float]


def _contains_secret_key(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key).lower()
            if any(token in name for token in ("api_key", "secret", "password", "credential", "access_token")):
                return True
            if _contains_secret_key(item):
                return True
    elif isinstance(value, (tuple, list)):
        return any(_contains_secret_key(item) for item in value)
    return False


@dataclass(frozen=True, slots=True)
class DirectE1CampaignConfig:
    campaign_id: str
    code_commit: str
    executor_id: str
    protocol_profile: str = "paper-e1-direct-v1"
    retry_failed: bool = False
    provider_manifest_json: str = ""
    dataset_snapshot_manifest_json: str = ""

    def __post_init__(self) -> None:
        if not self.campaign_id.strip() or not self.code_commit.strip() or not self.executor_id.strip():
            raise ValueError("campaign_id, code_commit and executor_id must be non-empty")
        if self.retry_failed:
            raise ValueError("In-place retry is disabled; use a new campaign_id/configuration")
        if not isinstance(self.provider_manifest_json, str) or not self.provider_manifest_json.strip():
            raise ValueError("A complete frozen provider_manifest_json is required before E1 campaign execution")
        try:
            manifest = json.loads(self.provider_manifest_json)
        except json.JSONDecodeError as exc:
            raise ValueError("provider_manifest_json must be valid JSON") from exc
        if not isinstance(manifest, dict) or manifest.get("schema_version") != "e1-provider-manifest-v1":
            raise ValueError("provider manifest must use schema e1-provider-manifest-v1")
        modes = manifest.get("model_modes")
        if not isinstance(modes, dict) or set(modes) != {"homogeneous", "heterogeneous"}:
            raise ValueError("provider manifest must declare homogeneous and heterogeneous model modes")
        if any(not isinstance(roster, dict) or not roster for roster in modes.values()):
            raise ValueError("provider manifest model-mode rosters must be non-empty objects")
        for mode, roster in modes.items():
            for agent_id, assignment in roster.items():
                if not isinstance(assignment, dict) or not assignment.get("model_id") or not assignment.get("backend"):
                    raise ValueError(f"provider manifest has an incomplete {mode}/{agent_id} model assignment")
                provenance = assignment.get("provenance")
                if not isinstance(provenance, dict) or not provenance.get("family_id") or not provenance.get("model_revision") or not provenance.get("access_date"):
                    raise ValueError(f"provider manifest has incomplete {mode}/{agent_id} provenance")
        families = manifest.get("model_family_catalogue")
        if not isinstance(families, dict) or set(families) != {"MA", "MB", "MC"} or any(not isinstance(v, dict) for v in families.values()):
            raise ValueError("provider manifest must declare exactly MA, MB and MC with provenance")
        family_provenance = {
            family: data for family, data in families.items()
        }
        provider_orgs = [data.get("provider_org") for data in family_provenance.values()]
        if any(not org for org in provider_orgs) or len(set(provider_orgs)) != 3:
            raise ValueError("provider manifest families must declare three distinct provider organizations")
        access = [data.get("weight_access") for data in family_provenance.values()]
        if access.count("closed-weight") != 1 or access.count("open-weight") != 2:
            raise ValueError("provider manifest requires one closed-weight and two open-weight families")
        open_sizes = [
            data.get("model_size") for data in family_provenance.values()
            if data.get("weight_access") == "open-weight"
        ]
        if any(not size for size in open_sizes) or len(set(open_sizes)) != 2:
            raise ValueError("provider manifest open-weight families must have different size labels")
        homogeneous = modes["homogeneous"]
        if any(item["provenance"]["family_id"] != "MA" for item in homogeneous.values()) or len({
            item["model_id"] for item in homogeneous.values()
        }) != 1:
            raise ValueError("homogeneous provider manifest must assign the exact MA identity to every agent")
        heterogeneous_families = {
            item["provenance"]["family_id"] for item in modes["heterogeneous"].values()
        }
        if heterogeneous_families != {"MA", "MB", "MC"}:
            raise ValueError("heterogeneous provider manifest must cover MA, MB and MC")
        for mode, roster in modes.items():
            for agent_id, assignment in roster.items():
                family_id = assignment["provenance"]["family_id"]
                family = families.get(family_id)
                if not isinstance(family, dict):
                    raise ValueError(f"provider manifest references unknown family {family_id!r}")
                if (
                    assignment["model_id"] != family.get("model_id")
                    or assignment["backend"] != family.get("backend")
                    or assignment["provenance"]["model_revision"] != family.get("model_revision")
                    or assignment["provenance"]["access_date"] != family.get("access_date")
                ):
                    raise ValueError(f"provider manifest assignment {mode}/{agent_id} differs from its family catalogue")
        executor = manifest.get("executor")
        if not isinstance(executor, dict) or executor.get("executor_id") != self.executor_id:
            raise ValueError("provider manifest executor identity differs from campaign executor_id")
        if not executor.get("model_id") or not isinstance(executor.get("provenance"), dict):
            raise ValueError("provider manifest must include exact fixed executor model provenance")
        if _contains_secret_key(manifest):
            raise ValueError("provider manifest must not contain credentials or secret values")
        canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        object.__setattr__(self, "provider_manifest_json", canonical)
        if not isinstance(self.dataset_snapshot_manifest_json, str) or not self.dataset_snapshot_manifest_json.strip():
            raise ValueError("A complete frozen dataset_snapshot_manifest_json is required before E1 campaign execution")
        try:
            snapshot = json.loads(self.dataset_snapshot_manifest_json)
        except json.JSONDecodeError as exc:
            raise ValueError("dataset_snapshot_manifest_json must be valid JSON") from exc
        if not isinstance(snapshot, dict) or snapshot.get("schema_version") != "e1-frozen-benchmark-snapshot-v1":
            raise ValueError("dataset snapshot manifest must use schema e1-frozen-benchmark-snapshot-v1")
        datasets = snapshot.get("datasets")
        if not isinstance(datasets, dict) or not datasets:
            raise ValueError("dataset snapshot manifest must contain dataset provenance entries")
        if snapshot.get("dataset_order") != list(datasets):
            raise ValueError("dataset snapshot dataset_order must match its ordered dataset entries")
        if content_hash({"datasets": datasets}) != snapshot.get("snapshot_sha256"):
            raise ValueError("dataset snapshot SHA-256 does not match its provenance entries")
        prompt_total = 0
        for dataset, entry in datasets.items():
            if dataset not in DATASET_REGISTRY or not isinstance(entry, dict):
                raise ValueError(f"dataset snapshot contains unknown or malformed dataset entry: {dataset}")
            source_sha = entry.get("source_sha256")
            if not isinstance(source_sha, str) or len(source_sha) != 64 or any(ch not in "0123456789abcdef" for ch in source_sha):
                raise ValueError(f"dataset source_sha256 must be a lowercase SHA-256 digest for {dataset}")
            for field in ("source_file", "source_version", "split", "selection_protocol"):
                if not isinstance(entry.get(field), str) or not entry[field].strip():
                    raise ValueError(f"dataset snapshot {field} is required for {dataset}")
            if entry.get("license_review_status") != "approved":
                raise ValueError(f"dataset usage rights are not approved for {dataset}")
            for field in ("paper_source_url", "prompt_case", "reference_provided",
                          "metrics", "coverage_applicable", "source_release_status"):
                if entry.get(field) != DATASET_REGISTRY[dataset][field]:
                    raise ValueError(f"dataset Table 12 source metadata differs for {dataset}/{field}")
            ids = entry.get("prompt_ids")
            prompt_hashes = entry.get("prompt_sha256")
            reference_hashes = entry.get("reference_data_sha256")
            if (not isinstance(ids, list) or len(ids) != len(set(ids))
                    or not all(isinstance(item, str) and item for item in ids)):
                raise ValueError(f"dataset prompt_ids must be a unique string list for {dataset}")
            if entry.get("prompt_count") != len(ids):
                raise ValueError(f"dataset prompt_count differs from prompt_ids for {dataset}")
            if not isinstance(prompt_hashes, dict) or set(prompt_hashes) != set(ids):
                raise ValueError(f"dataset prompt hashes do not cover prompt_ids for {dataset}")
            if not isinstance(reference_hashes, dict) or set(reference_hashes) != set(ids):
                raise ValueError(f"dataset reference-data hashes do not cover prompt_ids for {dataset}")
            for digest in (*prompt_hashes.values(), *reference_hashes.values()):
                if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                    raise ValueError(f"dataset prompt/reference hashes must be SHA-256 digests for {dataset}")
            prompt_total += len(ids)
        if snapshot.get("total_prompt_count") != prompt_total:
            raise ValueError("dataset snapshot total_prompt_count differs from its prompt IDs")
        snapshot_canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        object.__setattr__(self, "dataset_snapshot_manifest_json", snapshot_canonical)

    @property
    def provider_manifest(self) -> dict[str, object]:
        return json.loads(self.provider_manifest_json)

    @property
    def provider_manifest_hash(self) -> str:
        return content_hash(self.provider_manifest)

    @property
    def dataset_snapshot_manifest(self) -> dict[str, object]:
        return json.loads(self.dataset_snapshot_manifest_json)

    @property
    def dataset_snapshot_hash(self) -> str:
        return str(self.dataset_snapshot_manifest["snapshot_sha256"])


def _condition_key(condition: E1Condition) -> tuple:
    return (
        condition.dataset, condition.method_id, condition.model_mode,
        condition.seed, condition.matched_strategy_id,
        condition.call_budget, tuple(condition.prompt_ids),
    )


def validate_budget_matched_pairs(conditions: Iterable[E1Condition]) -> None:
    """Check baseline call budgets against their matched strategy rows."""
    rows = tuple(conditions)
    strategies = {
        (x.dataset, x.method_id, x.model_mode, x.seed, tuple(x.prompt_ids)): x
        for x in rows if x.method_id not in BASELINES
    }
    for baseline in (x for x in rows if x.method_id in BASELINES):
        key = (
            baseline.dataset, baseline.matched_strategy_id, baseline.model_mode,
            baseline.seed, tuple(baseline.prompt_ids),
        )
        strategy = strategies.get(key)
        if strategy is None:
            raise ValueError(f"Missing matched strategy condition for baseline {baseline.method_id}: {key}")
        if baseline.call_budget != strategy.call_budget:
            raise ValueError(
                f"Budget mismatch for {baseline.method_id} vs {strategy.method_id}: "
                f"{baseline.call_budget} != {strategy.call_budget}"
            )


def _result_record(
    config: DirectE1CampaignConfig,
    condition: E1Condition,
    example: BenchmarkPrompt,
    result: DirectE1Result | None,
    error: str | None,
) -> dict[str, object]:
    if result is None:
        return {
            "campaign_id": config.campaign_id,
            "campaign_config_hash": content_hash({
                "campaign_id": config.campaign_id, "code_commit": config.code_commit,
                "executor_id": config.executor_id, "protocol_profile": config.protocol_profile,
                "provider_manifest_hash": config.provider_manifest_hash,
            }),
            "provider_manifest_hash": config.provider_manifest_hash,
            "code_commit": config.code_commit,
            "protocol_profile": config.protocol_profile,
            "dataset": condition.dataset, "example_id": example.example_id,
            "method_id": condition.method_id, "model_mode": condition.model_mode,
            "seed": condition.seed, "matched_strategy_id": condition.matched_strategy_id,
            "method_call_budget": condition.call_budget,
            "prompt_hash": example.prompt_hash,
            "reference_data_sha256": example.reference_data_hash,
            "status": "failed", "error": error,
        }
    return {
        "campaign_id": config.campaign_id,
        "campaign_config_hash": content_hash({
            "campaign_id": config.campaign_id, "code_commit": config.code_commit,
            "executor_id": config.executor_id, "protocol_profile": config.protocol_profile,
            "provider_manifest_hash": config.provider_manifest_hash,
        }),
        "provider_manifest_hash": config.provider_manifest_hash,
        "code_commit": config.code_commit,
        "protocol_profile": config.protocol_profile,
        "dataset": result.dataset, "example_id": result.example_id,
        "method_id": result.method_id, "model_mode": result.model_mode,
        "seed": result.seed, "matched_strategy_id": result.matched_strategy_id,
        "executor_id": result.executor_id,
        "method_call_budget": result.call_budget,
        "calls_method": result.calls_method, "calls_executor": result.calls_executor,
        "calls_total": result.calls_total,
        "reference_data_sha256": example.reference_data_hash,
        "metrics": dict(result.metrics),
        "validity": {
            "V1": result.structural.v1_coverage.status.value,
            "V2": result.structural.v2_acyclicity.status.value,
            "V5": result.structural.v5_composition.status.value,
        },
        "metadata": dict(result.metadata),
        "provider_trace": [dict(x) for x in result.provider_trace],
        "decomposition_sha256": result.decomposition_sha256,
        "composed_answer_sha256": result.composed_answer_sha256,
        "prompt_hash": example.prompt_hash, "status": "success", "error": None,
    }


class DirectE1CampaignRunner:
    """Run a frozen E1 condition set with fsync-per-trial JSONL checkpoints."""

    def __init__(
        self,
        *,
        config: DirectE1CampaignConfig,
        conditions: Iterable[E1Condition],
        examples: Iterable[BenchmarkPrompt],
        prompt_factory: PromptFactory,
        extraction_factory: ExtractionFactory,
        method_factory: MethodFactory,
        executor: E1FixedExecutor,
        utility_scorer: UtilityScorer | None = None,
    ) -> None:
        self.config = config
        self.conditions = tuple(conditions)
        self.examples = {(x.dataset, x.example_id): x for x in examples}
        self.prompt_factory = prompt_factory
        self.extraction_factory = extraction_factory
        self.method_factory = method_factory
        self.executor = executor
        self.utility_scorer = utility_scorer
        if not self.conditions:
            raise ValueError("At least one preregistered E1 condition is required")
        if len(self.examples) == 0:
            raise ValueError("At least one frozen benchmark prompt is required")
        missing_references = [
            key for key, example in self.examples.items() if not example.reference_data
        ]
        if missing_references:
            raise ValueError(
                "Every E1 campaign prompt must carry its structured Table 12 reference data; "
                f"missing={missing_references[:5]}"
            )
        if executor.executor_id != config.executor_id:
            raise ValueError("Executor instance does not match the preregistered fixed executor ID")
        snapshot_datasets = self.config.dataset_snapshot_manifest["datasets"]
        for (dataset, example_id), example in self.examples.items():
            entry = snapshot_datasets.get(dataset)
            if not isinstance(entry, dict):
                raise ValueError(f"dataset snapshot provenance is missing for {dataset}")
            if example.source_version != entry["source_version"] or example.split != entry["split"]:
                raise ValueError(f"frozen example source version/split differs from dataset snapshot: {dataset}/{example_id}")
            if example_id not in entry["prompt_ids"]:
                raise ValueError(f"frozen example is absent from dataset snapshot prompt IDs: {dataset}/{example_id}")
            if entry["prompt_sha256"].get(example_id) != example.prompt_hash:
                raise ValueError(f"frozen example prompt hash differs from dataset snapshot: {dataset}/{example_id}")
            if entry["reference_data_sha256"].get(example_id) != example.reference_data_hash:
                raise ValueError(f"frozen example reference-data hash differs from dataset snapshot: {dataset}/{example_id}")
        if len({_condition_key(x) for x in self.conditions}) != len(self.conditions):
            raise ValueError("Duplicate E1 condition keys")
        validate_budget_matched_pairs(self.conditions)
        for condition in self.conditions:
            missing = [
                prompt_id for prompt_id in condition.prompt_ids
                if (condition.dataset, prompt_id) not in self.examples
            ]
            if missing:
                raise ValueError(f"Missing frozen prompts for {condition.dataset}: {missing[:5]}")

    def run(self, checkpoint_path: str | Path) -> tuple[dict[str, object], ...]:
        target = Path(checkpoint_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        prompt_snapshot = sorted(
            (dataset, example_id, example.prompt_hash)
            for (dataset, example_id), example in self.examples.items()
            if any(
                condition.dataset == dataset and example_id in condition.prompt_ids
                for condition in self.conditions
            )
        )
        config_hash = content_hash({
            "campaign_id": self.config.campaign_id,
            "code_commit": self.config.code_commit,
            "executor_id": self.config.executor_id,
            "protocol_profile": self.config.protocol_profile,
            "provider_manifest_hash": self.config.provider_manifest_hash,
            "dataset_snapshot_hash": self.config.dataset_snapshot_hash,
            "conditions": [list(_condition_key(x)) for x in self.conditions],
            "prompt_snapshot": [list(item) for item in prompt_snapshot],
        })
        manifest_path = target.with_suffix(target.suffix + ".manifest.json")
        if target.exists() and not manifest_path.exists():
            raise ValueError("Existing checkpoint is missing its frozen campaign manifest")
        campaign_manifest = {
            "schema_version": "e1-campaign-execution-manifest-v1",
            "campaign_id": self.config.campaign_id,
            "campaign_config_hash": config_hash,
            "code_commit": self.config.code_commit,
            "protocol_profile": self.config.protocol_profile,
            "conditions": [list(_condition_key(x)) for x in self.conditions],
            "prompt_snapshot": [list(item) for item in prompt_snapshot],
            "provider_manifest_hash": self.config.provider_manifest_hash,
            "provider_manifest": self.config.provider_manifest,
            "dataset_snapshot_hash": self.config.dataset_snapshot_hash,
            "dataset_snapshot_manifest": self.config.dataset_snapshot_manifest,
        }
        encoded_manifest = json.dumps(
            campaign_manifest, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
        if manifest_path.exists():
            try:
                existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError("Existing campaign manifest is invalid JSON") from exc
            if existing_manifest != json.loads(encoded_manifest):
                raise ValueError("Existing campaign manifest differs from requested frozen campaign")
        else:
            with manifest_path.open("x", encoding="utf-8", newline="\n") as manifest_stream:
                manifest_stream.write(encoded_manifest + "\n")
                manifest_stream.flush()
                os.fsync(manifest_stream.fileno())
        expected_rows = {
            (
                condition.dataset, prompt_id, condition.method_id,
                condition.model_mode, condition.seed, condition.matched_strategy_id,
                condition.call_budget,
            )
            for condition in self.conditions
            for prompt_id in condition.prompt_ids
        }
        completed: set[tuple] = set()
        records: list[dict[str, object]] = []
        if target.exists():
            with target.open("r", encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"Invalid checkpoint JSON on line {line_number}") from exc
                    if not isinstance(row, dict):
                        raise ValueError(f"Checkpoint row on line {line_number} must be a JSON object")
                    if row.get("campaign_config_hash") != config_hash:
                        raise ValueError("Checkpoint campaign hash differs from requested campaign")
                    if row.get("provider_manifest_hash") != self.config.provider_manifest_hash:
                        raise ValueError("Checkpoint provider manifest hash differs from requested model configuration")
                    if row.get("dataset_snapshot_hash") != self.config.dataset_snapshot_hash:
                        raise ValueError("Checkpoint dataset snapshot hash differs from requested dataset provenance")
                    key = (
                        row.get("dataset"), row.get("example_id"), row.get("method_id"),
                        row.get("model_mode"), row.get("seed"), row.get("matched_strategy_id"),
                        row.get("method_call_budget"),
                    )
                    if key not in expected_rows:
                        raise ValueError(f"Checkpoint row is not part of the frozen campaign: {key}")
                    expected_prompt_hash = self.examples[(key[0], key[1])].prompt_hash
                    if row.get("prompt_hash") != expected_prompt_hash:
                        raise ValueError(f"Checkpoint prompt hash differs from frozen prompt snapshot: {key}")
                    if row.get("reference_data_sha256") != self.examples[(key[0], key[1])].reference_data_hash:
                        raise ValueError(f"Checkpoint reference-data hash differs from frozen dataset snapshot: {key}")
                    if row.get("status") not in {"success", "failed"}:
                        raise ValueError(f"Checkpoint row has invalid status: {key}")
                    if key in completed:
                        raise ValueError(f"Duplicate checkpoint row: {key}")
                    completed.add(key)
                    records.append(row)
        with target.open("a", encoding="utf-8", newline="\n") as stream:
            for condition in self.conditions:
                for prompt_id in condition.prompt_ids:
                    key = (
                        condition.dataset, prompt_id, condition.method_id,
                        condition.model_mode, condition.seed, condition.matched_strategy_id,
                        condition.call_budget,
                    )
                    if key in completed:
                        continue
                    example = self.examples[(condition.dataset, prompt_id)]
                    try:
                        prompt = self.prompt_factory(example)
                        if not isinstance(prompt, Prompt) or prompt.text != example.prompt_text:
                            raise ValueError("prompt_factory must return Prompt with exact frozen prompt text")
                        extraction = self.extraction_factory(prompt)
                        if not isinstance(extraction, AggregatedExtraction):
                            raise TypeError("extraction_factory must return AggregatedExtraction")
                        method = self.method_factory(condition, prompt, extraction)
                        result = run_direct_e1_condition(
                            condition=condition, example_id=prompt_id, prompt=prompt,
                            requirements=extraction.requirements,
                            hypotheses=extraction.hypotheses,
                            reference_data=example.reference_data,
                            method=method, executor=self.executor,
                            expected_executor_id=self.config.executor_id,
                            seed=condition.seed, utility_scorer=self.utility_scorer,
                        )
                        row = _result_record(self.config, condition, example, result, None)
                        row["campaign_config_hash"] = config_hash
                    except Exception as exc:
                        row = _result_record(
                            self.config, condition, example, None,
                            f"{type(exc).__name__}: {exc}",
                        )
                        row["campaign_config_hash"] = config_hash
                    encoded = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
                    stream.write(encoded + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                    records.append(row)
                    completed.add(key)
        return tuple(records)
