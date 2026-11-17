import json

import pytest

from sociodec.experiments import BenchmarkPrompt, ExperimentConfig, TrialOutcome
from sociodec.resumable import load_checkpoint, run_resumable_campaign


def _config():
    return ExperimentConfig("E1", "demo", ("family-a",), "executor",
                            ("S2",), repeats=2)


def _examples():
    return (BenchmarkPrompt("demo", "p1", "Explain a simple process."),
            BenchmarkPrompt("demo", "p2", "Explain another process."))


def test_resumable_campaign_writes_every_trial_and_skips_completed(tmp_path):
    calls = []
    def adapter(context):
        calls.append((context.example.example_id, context.repeat_index))
        return TrialOutcome({"coverage": 1.0}, metadata={"seed": context.seed})
    path = tmp_path / "checkpoint.jsonl"
    first = run_resumable_campaign(_config(), _examples(), adapter, path)
    assert len(first) == 4 and len(calls) == 4
    second = run_resumable_campaign(_config(), _examples(), adapter, path)
    assert len(second) == 4 and len(calls) == 4
    assert len(path.read_text().splitlines()) == 4


def test_checkpoint_rejects_changed_config_or_prompt(tmp_path):
    path = tmp_path / "checkpoint.jsonl"
    run_resumable_campaign(_config(), _examples(),
        lambda _: TrialOutcome({"coverage": 1.0}), path)
    changed = ExperimentConfig("E1", "demo", ("family-b",), "executor",
                               ("S2",), repeats=2)
    with pytest.raises(ValueError, match="config_hash"):
        load_checkpoint(path, changed, _examples())
    changed_prompt = (BenchmarkPrompt("demo", "p1", "changed"),
                      _examples()[1])
    with pytest.raises(ValueError, match="unknown or changed prompt"):
        load_checkpoint(path, _config(), changed_prompt)


def test_checkpoint_rejects_duplicate_trial_keys(tmp_path):
    path = tmp_path / "checkpoint.jsonl"
    run_resumable_campaign(_config(), _examples(),
        lambda _: TrialOutcome({"coverage": 1.0}), path)
    rows = path.read_text().splitlines()
    path.write_text("\n".join(rows + [rows[0]]) + "\n")
    with pytest.raises(ValueError, match="Duplicate checkpoint trial"):
        load_checkpoint(path, _config(), _examples())


def test_failed_trial_is_checkpointed_and_not_silently_retried(tmp_path):
    path = tmp_path / "checkpoint.jsonl"
    calls = []
    def adapter(_):
        calls.append(1)
        raise RuntimeError("provider unavailable")
    records = run_resumable_campaign(_config(), _examples(), adapter, path)
    assert all(item.status == "failed" for item in records)
    run_resumable_campaign(_config(), _examples(), adapter, path)
    assert len(calls) == 4
