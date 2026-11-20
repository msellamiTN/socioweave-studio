import json
import pytest

from sociodec.datasets import (
    DATASET_REGISTRY, E1DatasetSource, e1_prompt_id_map,
    freeze_e1_benchmark_snapshot, load_jsonl_dataset,
)
from sociodec.e1_protocol import ALL_DATASETS, EXPECTED_PROMPTS


def test_registry_covers_paper_benchmarks_and_marks_license_review():
    assert {"BREAK", "StrategyQA", "TaskBench", "TravelPlanner", "smart-administration"} <= set(DATASET_REGISTRY)
    assert all(DATASET_REGISTRY[name]["license_review_required"] for name in ("BREAK", "StrategyQA", "TaskBench", "TravelPlanner"))


def test_jsonl_loader_preserves_ids_splits_and_source_version(tmp_path):
    path = tmp_path / "break.jsonl"
    path.write_text(json.dumps({"example_id": "q1", "prompt_text": "Do task", "split": "test"}) + "\n", encoding="utf-8")
    rows = load_jsonl_dataset(path, dataset="BREAK", source_version="break-2026-01", expected_count=1, expected_split="test")
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


def _write_fixture(path, dataset, count, split="test"):
    # Synthetic rows are test fixtures only; never used as benchmark evidence.
    path.write_text("".join(
        json.dumps({"example_id": f"{dataset}-{i:03d}", "prompt_text": f"fixture prompt {i}", "split": split}) + "\n"
        for i in range(count)
    ), encoding="utf-8")


def _sources(tmp_path, *, split="test"):
    sources = {}
    for dataset in ALL_DATASETS:
        path = tmp_path / f"{dataset}.jsonl"
        _write_fixture(path, dataset, EXPECTED_PROMPTS[dataset], split=split)
        sources[dataset] = E1DatasetSource(path, f"{dataset}-fixture-v1", split, "synthetic test fixture only", "approved")
    return sources


def test_freeze_e1_snapshot_validates_all_five_files_and_exports_grid_ids(tmp_path):
    snapshot = freeze_e1_benchmark_snapshot(_sources(tmp_path))
    assert len(snapshot.examples) == sum(EXPECTED_PROMPTS.values()) == 460
    assert set(snapshot.expected_prompt_ids) == set(ALL_DATASETS)
    assert {name: len(ids) for name, ids in e1_prompt_id_map(snapshot).items()} == EXPECTED_PROMPTS
    assert snapshot.manifest["schema_version"] == "e1-frozen-benchmark-snapshot-v1"
    assert len(snapshot.manifest["snapshot_sha256"]) == 64
    for dataset in ALL_DATASETS:
        entry = snapshot.manifest["datasets"][dataset]
        assert entry["prompt_count"] == EXPECTED_PROMPTS[dataset]
        assert len(entry["source_sha256"]) == 64
        assert len(entry["prompt_sha256"]) == EXPECTED_PROMPTS[dataset]


def test_freeze_e1_snapshot_rejects_missing_dataset_and_wrong_count(tmp_path):
    sources = _sources(tmp_path)
    with pytest.raises(ValueError, match="exactly the five"):
        freeze_e1_benchmark_snapshot({k: v for k, v in sources.items() if k != "BREAK"})
    path = tmp_path / "BREAK.jsonl"
    _write_fixture(path, "BREAK", EXPECTED_PROMPTS["BREAK"] - 1)
    sources["BREAK"] = E1DatasetSource(path, "BREAK-v1", "test", "synthetic test fixture only", "approved")
    with pytest.raises(ValueError, match="expected 100 examples"):
        freeze_e1_benchmark_snapshot(sources)


def test_freeze_e1_snapshot_rejects_mixed_or_wrong_split(tmp_path):
    sources = _sources(tmp_path)
    path = tmp_path / "BREAK.jsonl"
    _write_fixture(path, "BREAK", EXPECTED_PROMPTS["BREAK"], split="validation")
    sources["BREAK"] = E1DatasetSource(path, "BREAK-v1", "test", "synthetic test fixture only", "approved")
    with pytest.raises(ValueError, match="differs from declared split"):
        freeze_e1_benchmark_snapshot(sources)


def test_snapshot_manifest_binds_exact_source_bytes_and_prompt_content(tmp_path):
    sources = _sources(tmp_path)
    first = freeze_e1_benchmark_snapshot(sources)
    path = tmp_path / "BREAK.jsonl"
    # Change one prompt while retaining row count and IDs.
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["prompt_text"] = "changed fixture prompt"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    second = freeze_e1_benchmark_snapshot(sources)
    assert first.manifest["snapshot_sha256"] != second.manifest["snapshot_sha256"]
    assert first.manifest["datasets"]["BREAK"]["source_sha256"] != second.manifest["datasets"]["BREAK"]["source_sha256"]
    assert first.manifest["datasets"]["BREAK"]["prompt_sha256"]["BREAK-000"] != second.manifest["datasets"]["BREAK"]["prompt_sha256"]["BREAK-000"]


@pytest.mark.parametrize("row", [
    [],
    {"example_id": 1, "prompt_text": "not a string"},
    {"example_id": "x", "prompt_text": "p", "metadata": []},
])
def test_jsonl_loader_rejects_non_object_or_malformed_rows(tmp_path, row):
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        load_jsonl_dataset(path, dataset="BREAK", source_version="v1")


def test_dataset_registry_matches_paper_table12_sources_and_metric_scope():
    assert DATASET_REGISTRY["BREAK"]["paper_source_url"] == "https://allenai.github.io/Break/"
    assert DATASET_REGISTRY["StrategyQA"]["paper_source_url"] == "https://allenai.org/data/strategyqa"
    assert DATASET_REGISTRY["TaskBench"]["paper_source_url"] == "https://github.com/microsoft/JARVIS/tree/main/taskbench"
    assert DATASET_REGISTRY["TravelPlanner"]["paper_source_url"] == "https://osu-nlp-group.github.io/TravelPlanner"
    assert DATASET_REGISTRY["smart-administration"]["source_release_status"] == "to_be_released_with_code"
    assert DATASET_REGISTRY["BREAK"]["coverage_applicable"] is False
    assert DATASET_REGISTRY["TravelPlanner"]["coverage_applicable"] == "annotated_constraints_only"
    assert DATASET_REGISTRY["smart-administration"]["coverage_applicable"] is True


def test_dataset_source_requires_explicit_selection_and_usage_approval(tmp_path):
    path = tmp_path / "break.jsonl"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="selection_protocol"):
        E1DatasetSource(path, "v1", "test", "", "approved")
    with pytest.raises(ValueError, match="explicitly approved"):
        E1DatasetSource(path, "v1", "test", "first 100 rows", "not-reviewed")
