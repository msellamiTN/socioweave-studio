"""Dataset registry and fail-closed local JSONL intake for E1 snapshots.

No dataset is downloaded, rewritten, normalized, or synthesized here. The
operator supplies the exact licensed source files and declares their versions
and selected splits before the E1 condition grid can be built.
"""
from __future__ import annotations

import json
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from sociodec.experiments import (
    BenchmarkPrompt, content_hash, sha256_file,
)
from sociodec.e1_protocol import ALL_DATASETS, EXPECTED_PROMPTS


DATASET_REGISTRY = {
    "BREAK": {
        "paper_source_url": "https://allenai.github.io/Break/",
        "prompt_case": "well-structured prompts; granularity",
        "reference_provided": "gold decomposition of each question into ordered steps",
        "metrics": [
            "reference agreement", "redundancy", "coupling", "validity V2/V5",
            "stability", "cost",
        ],
        "coverage_applicable": False,
        "source_release_status": "public_source",
        "selection_protocol": "not specified by paper; operator must declare exact 100-prompt selection",
        "license_review_required": True,
    },
    "StrategyQA": {
        "paper_source_url": "https://allenai.org/data/strategyqa",
        "prompt_case": "implicit prerequisites; omission",
        "reference_provided": "annotated decomposition, evidence and answer",
        "metrics": [
            "reference agreement/implicit-step recall", "utility/answer accuracy",
            "process gain", "stability", "cost",
        ],
        "coverage_applicable": False,
        "source_release_status": "public_source",
        "selection_protocol": "not specified by paper; operator must declare exact 100-prompt selection",
        "license_review_required": True,
    },
    "TaskBench": {
        "paper_source_url": "https://github.com/microsoft/JARVIS/tree/main/taskbench",
        "prompt_case": "dependencies between sub-tasks; several domains",
        "reference_provided": "reference graph of sub-tasks",
        "metrics": [
            "reference agreement on sub-tasks/dependencies", "validity V2/V5",
            "coupling", "stability", "cost",
        ],
        "coverage_applicable": False,
        "source_release_status": "public_source",
        "selection_protocol": "not specified by paper; operator must declare exact 100-prompt selection",
        "license_review_required": True,
    },
    "TravelPlanner": {
        "paper_source_url": "https://osu-nlp-group.github.io/TravelPlanner",
        "prompt_case": "many constraints; utility by execution",
        "reference_provided": "annotated constraints and checks on the final plan",
        "metrics": [
            "utility", "solvability", "process gain", "validity V2/V5",
            "coverage restricted to annotated constraints", "stability", "cost",
        ],
        "coverage_applicable": "annotated_constraints_only",
        "source_release_status": "public_source",
        "selection_protocol": "not specified by paper; operator must declare exact 100-prompt selection",
        "license_review_required": True,
    },
    "smart-administration": {
        "paper_source_url": None,
        "prompt_case": "ambiguity, conflicting objectives, several institutions",
        "reference_provided": "requirement lists, hypotheses and reference decompositions reviewed by practitioners",
        "metrics": ["all Table 9 metrics, including V1 coverage and hypothesis verdicts"],
        "coverage_applicable": True,
        "source_release_status": "to_be_released_with_code",
        "selection_protocol": "author-curated 60-prompt set; exact version and IDs must be supplied",
        "license_review_required": True,
    },
}


@dataclass(frozen=True, slots=True)
class E1DatasetSource:
    """Operator declaration for one exact local benchmark source file."""
    path: str | Path
    source_version: str
    split: str
    selection_protocol: str
    license_review_status: str
    selection_seed: int | None = None
    source_url: str = ""
    source_revision: str = ""
    license_url: str = ""
    license_identifier: str = ""
    license_review_evidence: str = ""
    license_reviewed_by: str = ""
    license_reviewed_at: str = ""
    eligible_population_count: int = 0

    def __post_init__(self) -> None:
        if not str(self.path).strip():
            raise ValueError("dataset source path must be non-empty")
        if not self.source_version.strip() or not self.split.strip():
            raise ValueError("source_version and split must be non-empty")
        if not self.selection_protocol.strip():
            raise ValueError("selection_protocol must record the exact prompt-selection procedure")
        for name in (
            "source_url", "source_revision", "license_url", "license_identifier",
            "license_review_evidence", "license_reviewed_by", "license_reviewed_at",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be explicitly declared before snapshot freezing")
        try:
            reviewed_at = datetime.fromisoformat(self.license_reviewed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("license_reviewed_at must be an ISO-8601 timestamp") from exc
        if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
            raise ValueError("license_reviewed_at must include a timezone")
        if (
            isinstance(self.eligible_population_count, bool)
            or not isinstance(self.eligible_population_count, int)
            or self.eligible_population_count < 1
        ):
            raise ValueError("eligible_population_count must be an integer >= 1")
        if self.license_review_status != "approved":
            raise ValueError("dataset usage must be explicitly approved before snapshot freezing")
        if self.selection_seed is not None and (
            isinstance(self.selection_seed, bool)
            or not isinstance(self.selection_seed, int)
            or self.selection_seed < 0
        ):
            raise ValueError("selection_seed must be a non-negative integer when supplied")


@dataclass(frozen=True, slots=True)
class E1FrozenSnapshot:
    """Validated prompt records and a serializable, content-addressed manifest."""
    examples: tuple[BenchmarkPrompt, ...]
    expected_prompt_ids: Mapping[str, tuple[str, ...]]
    manifest: Mapping[str, object]

    def manifest_json(self) -> str:
        return json.dumps(self.manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def load_jsonl_dataset(
    path: str | Path,
    *,
    dataset: str,
    source_version: str,
    expected_count: int | None = None,
    expected_split: str | None = None,
) -> tuple[BenchmarkPrompt, ...]:
    """Load a user-provided JSONL snapshot; never downloads or silently edits it."""
    if dataset not in DATASET_REGISTRY:
        raise ValueError(f"Unknown dataset: {dataset}")
    if not isinstance(source_version, str) or not source_version.strip():
        raise ValueError("source_version must be non-empty")
    if expected_split is not None and (not isinstance(expected_split, str) or not expected_split.strip()):
        raise ValueError("expected_split must be non-empty when supplied")
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"dataset source is not a regular file: {source}")

    examples: list[BenchmarkPrompt] = []
    with source.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError("row must be a JSON object")
                example_id = item.get("example_id")
                prompt_text = item.get("prompt_text")
                split = item.get("split")
                if split is None:
                    raise ValueError("split must be explicitly present on every row; implicit defaults are forbidden")
                metadata = item.get("metadata", {})
                reference_data = item.get("reference_data", {})
                if not isinstance(example_id, str) or not example_id.strip():
                    raise ValueError("example_id must be a non-empty string")
                if not isinstance(prompt_text, str) or not prompt_text.strip():
                    raise ValueError("prompt_text must be a non-empty string")
                if not isinstance(split, str) or not split.strip():
                    raise ValueError("split must be a non-empty string")
                if not isinstance(metadata, dict):
                    raise ValueError("metadata must be a JSON object")
                if any(not isinstance(k, str) or not isinstance(v, (str, int, float, bool)) for k, v in metadata.items()):
                    raise ValueError("metadata values must be scalar strings, numbers or booleans")
                if not isinstance(reference_data, dict):
                    raise ValueError("reference_data must be a JSON object")
                if DATASET_REGISTRY[dataset]["reference_provided"] and not reference_data:
                    raise ValueError("reference_data is required by the paper's Table 12 for this dataset")
                try:
                    content_hash(reference_data)
                except (TypeError, ValueError) as exc:
                    raise ValueError("reference_data must contain finite JSON-compatible values") from exc
                if expected_split is not None and split != expected_split:
                    raise ValueError(
                        f"row split {split!r} differs from declared split {expected_split!r}"
                    )
                examples.append(BenchmarkPrompt(
                    dataset=dataset,
                    example_id=example_id,
                    prompt_text=prompt_text,
                    split=split,
                    source_version=source_version,
                    metadata={k: str(v) for k, v in metadata.items()},
                    reference_data=reference_data,
                ))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid dataset row at line {line_number}: {exc}") from exc

    ids = [x.example_id for x in examples]
    if len(ids) != len(set(ids)):
        raise ValueError("dataset contains duplicate example_id values")
    if expected_count is not None and len(examples) != expected_count:
        raise ValueError(f"expected {expected_count} examples, found {len(examples)}")
    return tuple(examples)


def freeze_e1_benchmark_snapshot(
    sources: Mapping[str, E1DatasetSource],
) -> E1FrozenSnapshot:
    """Validate all five operator-supplied E1 files and create a hash manifest.

    The paper's registered prompt counts are enforced. The declared split must
    match every row. File hashes bind the manifest to the exact source bytes;
    per-prompt hashes bind it to the exact prompt text and provenance. No
    prompt IDs or benchmark examples are generated by this function.
    """
    if set(sources) != set(ALL_DATASETS):
        raise ValueError("sources must declare exactly the five E1 paper datasets")

    all_examples: list[BenchmarkPrompt] = []
    prompt_ids: dict[str, tuple[str, ...]] = {}
    dataset_entries: dict[str, object] = {}
    for dataset in ALL_DATASETS:
        source = sources[dataset]
        if not isinstance(source, E1DatasetSource):
            raise TypeError(f"{dataset} source must be an E1DatasetSource")
        path = Path(source.path)
        examples = load_jsonl_dataset(
            path,
            dataset=dataset,
            source_version=source.source_version,
            expected_count=EXPECTED_PROMPTS[dataset],
            expected_split=source.split,
        )
        if source.eligible_population_count < EXPECTED_PROMPTS[dataset]:
            raise ValueError(
                f"{dataset} eligible_population_count cannot be smaller than selected prompt count"
            )
        ids = tuple(x.example_id for x in examples)
        prompt_ids[dataset] = ids
        all_examples.extend(examples)
        dataset_entries[dataset] = {
            "source_file": path.name,
            "source_sha256": sha256_file(path),
            "source_url": source.source_url,
            "source_revision": source.source_revision,
            "source_version": source.source_version,
            "split": source.split,
            "eligible_population_count": source.eligible_population_count,
            "selection_protocol": source.selection_protocol,
            "selection_method": "operator-declared; exact selected IDs are recorded below",
            "selection_seed": source.selection_seed,
            "license_review_status": source.license_review_status,
            "license_url": source.license_url,
            "license_identifier": source.license_identifier,
            "license_review_evidence": source.license_review_evidence,
            "license_reviewed_by": source.license_reviewed_by,
            "license_reviewed_at": source.license_reviewed_at,
            "paper_source_url": DATASET_REGISTRY[dataset]["paper_source_url"],
            "prompt_case": DATASET_REGISTRY[dataset]["prompt_case"],
            "reference_provided": DATASET_REGISTRY[dataset]["reference_provided"],
            "metrics": list(DATASET_REGISTRY[dataset]["metrics"]),
            "coverage_applicable": DATASET_REGISTRY[dataset]["coverage_applicable"],
            "source_release_status": DATASET_REGISTRY[dataset]["source_release_status"],
            "prompt_count": len(examples),
            "prompt_ids": list(ids),
            "prompt_sha256": {x.example_id: x.prompt_hash for x in examples},
            "reference_data_sha256": {x.example_id: x.reference_data_hash for x in examples},
        }

    snapshot_sha256 = content_hash({"datasets": dataset_entries})
    manifest: dict[str, object] = {
        "schema_version": "e1-frozen-benchmark-snapshot-v1",
        "dataset_order": list(ALL_DATASETS),
        "datasets": dataset_entries,
        "total_prompt_count": len(all_examples),
        "snapshot_sha256": snapshot_sha256,
    }
    return E1FrozenSnapshot(
        examples=tuple(all_examples),
        expected_prompt_ids=prompt_ids,
        manifest=manifest,
    )


def e1_prompt_id_map(snapshot: E1FrozenSnapshot) -> dict[str, tuple[str, ...]]:
    """Return the exact prompt-ID map accepted by build_e1_conditions()."""
    return {dataset: tuple(snapshot.expected_prompt_ids[dataset]) for dataset in ALL_DATASETS}
