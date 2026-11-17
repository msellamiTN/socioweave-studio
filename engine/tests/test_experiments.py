import json

import pytest

from sociodec.experiments import (
    BenchmarkPrompt, ExperimentConfig, ExperimentRunner, TrialOutcome,
    content_hash, trial_seed, write_jsonl,
)


def config(**overrides):
    values = dict(
        experiment_id="E1", dataset="BREAK", model_families=("model-a", "model-b"),
        executor_model="executor-v1", strategy_ids=("S1", "S2"),
        repeats=3, base_seed=41,
    )
    values.update(overrides)
    return ExperimentConfig(**values)


def example(**overrides):
    values = dict(dataset="BREAK", example_id="ex-001",
                  prompt_text="Decompose this task.", source_version="break-v1")
    values.update(overrides)
    return BenchmarkPrompt(**values)


def test_config_hash_is_stable_and_sensitive_to_settings():
    assert config().config_hash == config().config_hash
    assert config().config_hash != config(base_seed=42).config_hash
    assert content_hash({"b": 2, "a": 1}) == content_hash({"a": 1, "b": 2})


def test_trial_seed_is_stable_and_separated_by_repeat_and_example():
    assert trial_seed(7, "BREAK", "x", 0) == trial_seed(7, "BREAK", "x", 0)
    assert trial_seed(7, "BREAK", "x", 0) != trial_seed(7, "BREAK", "x", 1)
    assert trial_seed(7, "BREAK", "x", 0) != trial_seed(7, "BREAK", "y", 0)


def test_runner_records_all_repeats_with_provenance_and_trace():
    runner = ExperimentRunner(config(), lambda ctx: TrialOutcome(
        {"coverage": 0.9}, ({"model": "model-a", "tokens": 12},),
        {"temperature": 0.7},
    ))
    records = runner.run([example()])
    assert len(records) == 3
    assert {x.status for x in records} == {"success"}
    assert len({x.seed for x in records}) == 3
    assert all(x.config_hash == config().config_hash for x in records)
    assert all(x.prompt_hash == example().prompt_hash for x in records)
    assert records[0].provider_trace[0]["tokens"] == 12


def test_runner_captures_failures_and_continues_campaign():
    def adapter(ctx):
        if ctx.repeat_index == 1:
            raise RuntimeError("simulated provider outage")
        return TrialOutcome({"utility": 0.5})
    records = ExperimentRunner(config(), adapter).run([example()])
    assert [x.status for x in records] == ["success", "failed", "success"]
    assert "simulated provider outage" in records[1].error


def test_runner_rejects_duplicate_examples_and_dataset_mismatch():
    runner = ExperimentRunner(config(), lambda _: TrialOutcome({"x": 1.0}))
    with pytest.raises(ValueError, match="duplicate"):
        runner.run([example(), example()])
    with pytest.raises(ValueError, match="does not match"):
        runner.run([example(dataset="StrategyQA")])


@pytest.mark.parametrize("kwargs", [
    {"repeats": 0}, {"n_agents": 0}, {"max_rounds": 0},
    {"temperature_draft": -0.1}, {"experiment_id": "E10"},
    {"model_families": ()}, {"strategy_ids": ()},
])
def test_config_rejects_invalid_settings(kwargs):
    with pytest.raises((ValueError, TypeError)):
        config(**kwargs)


@pytest.mark.parametrize("kwargs", [
    {"dataset": ""}, {"example_id": ""}, {"prompt_text": ""},
    {"source_version": ""},
])
def test_benchmark_prompt_rejects_missing_identity(kwargs):
    with pytest.raises(ValueError):
        example(**kwargs)


def test_trial_outcome_rejects_non_finite_metrics():
    with pytest.raises(ValueError, match="finite"):
        TrialOutcome({"bad": float("nan")})


def test_jsonl_export_is_machine_readable_and_counts_rows(tmp_path):
    records = ExperimentRunner(config(repeats=1),
        lambda _: TrialOutcome({"coverage": 1.0})).run([example()])
    path = tmp_path / "runs" / "campaign.jsonl"
    assert write_jsonl(records, path) == 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert payload["config_hash"] == config(repeats=1).config_hash
