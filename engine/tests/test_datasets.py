import json
import pytest

from sociodec.datasets import DATASET_REGISTRY, load_jsonl_dataset


def test_registry_covers_paper_benchmarks_and_marks_license_review():
    assert {"BREAK", "StrategyQA", "TaskBench", "TravelPlanner", "smart-administration"} <= set(DATASET_REGISTRY)
    assert all(DATASET_REGISTRY[name]["license_review_required"] for name in ("BREAK", "StrategyQA", "TaskBench", "TravelPlanner"))


def test_jsonl_loader_preserves_ids_splits_and_source_version(tmp_path):
    path = tmp_path / "break.jsonl"
    path.write_text(json.dumps({"example_id": "q1", "prompt_text": "Do task", "split": "test"}) + "\n", encoding="utf-8")
    rows = load_jsonl_dataset(path, dataset="BREAK", source_version="break-2026-01", expected_count=1)
    assert rows[0].example_id == "q1"
    assert rows[0].source_version == "break-2026-01"
    assert rows[0].split == "test"


def test_jsonl_loader_rejects_unknown_dataset_duplicate_and_bad_rows(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown dataset"):
        load_jsonl_dataset(path, dataset="unknown", source_version="v1")
    with pytest.raises(ValueError, match="line 1"):
        load_jsonl_dataset(path, dataset="BREAK", source_version="v1")
    path.write_text(
        '{"example_id":"x","prompt_text":"A"}\n{"example_id":"x","prompt_text":"B"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_jsonl_dataset(path, dataset="BREAK", source_version="v1")
    path.write_text(json.dumps({"example_id": "y", "prompt_text": "A"}) + chr(10), encoding="utf-8")
    with pytest.raises(ValueError, match="expected"):
        load_jsonl_dataset(path, dataset="BREAK", source_version="v1", expected_count=3)
