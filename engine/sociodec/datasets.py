"""Dataset registry and fail-closed local JSONL intake for E1 snapshots.

No dataset is downloaded, rewritten, normalized, or synthesized here. The
operator supplies the exact licensed source files and declares their versions
and selected splits before the E1 condition grid can be built.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from sociodec.experiments import (
    BenchmarkPrompt, content_hash, sha256_file,
)
from sociodec.e1_protocol import ALL_DATASETS, EXPECTED_PROMPTS


DATASET_REGISTRY = {
    "BREAK": {"paper_source": "BREAK", "split_policy": "use the paper's selected split", "license_review_required": True},
    "StrategyQA": {"paper_source": "StrategyQA", "split_policy": "use the paper's selected split", "license_review_required": True},
    "TaskBench": {"paper_source": "TaskBench", "split_policy": "use the paper's selected split", "license_review_required": True},
    "TravelPlanner": {"paper_source": "TravelPlanner", "split_policy": "use the paper's selected split", "license_review_required": True},
    "smart-administration": {"paper_source": "author-curated 60-prompt set", "split_policy": "version and annotate the author-curated set", "license_review_required": False},
}


@dataclass(frozen=True, slots=True)
class E1DatasetSource:
    """Operator declaration for one exact local benchmark source file."""
    path: str | Path
    source_version: str
    split: str

    def __post_init__(self) -> None:
        if not str(self.path).strip():
            raise ValueError("dataset source path must be non-empty")
        if not self.source_version.strip() or not self.split.strip():
            raise ValueError("source_version and split must be non-empty")


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
                split = item.get("split", "test")
                metadata = item.get("metadata", {})
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
        ids = tuple(x.example_id for x in examples)
        prompt_ids[dataset] = ids
        all_examples.extend(examples)
        dataset_entries[dataset] = {
            "source_file": path.name,
            "source_sha256": sha256_file(path),
            "source_version": source.source_version,
            "split": source.split,
            "prompt_count": len(examples),
            "prompt_ids": list(ids),
            "prompt_sha256": {x.example_id: x.prompt_hash for x in examples},
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
