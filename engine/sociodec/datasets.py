"""Dataset registry and local JSONL adapter for licensed benchmark snapshots."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from sociodec.experiments import BenchmarkPrompt


DATASET_REGISTRY = {
    "BREAK": {"paper_source": "BREAK", "split_policy": "use the paper's selected split", "license_review_required": True},
    "StrategyQA": {"paper_source": "StrategyQA", "split_policy": "use the paper's selected split", "license_review_required": True},
    "TaskBench": {"paper_source": "TaskBench", "split_policy": "use the paper's selected split", "license_review_required": True},
    "TravelPlanner": {"paper_source": "TravelPlanner", "split_policy": "use the paper's selected split", "license_review_required": True},
    "smart-administration": {"paper_source": "author-curated 60-prompt set", "split_policy": "version and annotate the author-curated set", "license_review_required": False},
}


def load_jsonl_dataset(path: str | Path, *, dataset: str, source_version: str,
                       expected_count: int | None = None) -> tuple[BenchmarkPrompt, ...]:
    """Load a user-provided JSONL snapshot; never downloads or silently edits it."""
    if dataset not in DATASET_REGISTRY:
        raise ValueError(f"Unknown dataset: {dataset}")
    if not source_version.strip():
        raise ValueError("source_version must be non-empty")
    examples: list[BenchmarkPrompt] = []
    with Path(path).open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                examples.append(BenchmarkPrompt(
                    dataset=dataset,
                    example_id=str(item["example_id"]),
                    prompt_text=str(item["prompt_text"]),
                    split=str(item.get("split", "test")),
                    source_version=source_version,
                    metadata={str(k): str(v) for k, v in item.get("metadata", {}).items()},
                ))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid dataset row at line {line_number}: {exc}") from exc
    ids = [x.example_id for x in examples]
    if len(ids) != len(set(ids)):
        raise ValueError("dataset contains duplicate example_id values")
    if expected_count is not None and len(examples) != expected_count:
        raise ValueError(f"expected {expected_count} examples, found {len(examples)}")
    return tuple(examples)
