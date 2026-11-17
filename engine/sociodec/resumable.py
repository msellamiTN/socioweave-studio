"""Crash-safe JSONL checkpointing for real SocioWeave campaigns."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Iterable

from sociodec.experiments import (
    BenchmarkPrompt, ExperimentConfig, TrialContext, TrialOutcome, TrialRecord,
    trial_seed,
)


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def load_checkpoint(path: str | Path, config: ExperimentConfig,
                    examples: Iterable[BenchmarkPrompt]) -> tuple[TrialRecord, ...]:
    """Load records only when config, prompt identity and trial keys agree."""
    target = Path(path)
    if not target.exists():
        return ()
    expected = {(item.dataset, item.example_id): item for item in examples}
    records: list[TrialRecord] = []
    seen: set[tuple[str, str, int]] = set()
    with target.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                record = TrialRecord(**raw)
            except Exception as exc:
                raise ValueError(f"Invalid checkpoint line {line_number}: {exc}") from exc
            if record.config_hash != config.config_hash:
                raise ValueError("Checkpoint config_hash does not match requested campaign")
            key = (record.dataset, record.example_id)
            example = expected.get(key)
            if example is None or record.prompt_hash != example.prompt_hash:
                raise ValueError(f"Checkpoint contains unknown or changed prompt: {key}")
            trial_key = (*key, record.repeat_index)
            if trial_key in seen:
                raise ValueError(f"Duplicate checkpoint trial: {trial_key}")
            if not 0 <= record.repeat_index < config.repeats:
                raise ValueError(f"Invalid repeat index in checkpoint: {trial_key}")
            expected_seed = trial_seed(config.base_seed, record.dataset,
                                       record.example_id, record.repeat_index)
            if record.seed != expected_seed:
                raise ValueError(f"Checkpoint seed mismatch: {trial_key}")
            seen.add(trial_key)
            records.append(record)
    return tuple(records)


def run_resumable_campaign(
    config: ExperimentConfig,
    examples: Iterable[BenchmarkPrompt],
    adapter: Callable[[TrialContext], TrialOutcome],
    checkpoint_path: str | Path,
) -> tuple[TrialRecord, ...]:
    """Execute missing trials and fsync each record before advancing.

    Existing successful and failed trials are both considered completed.
    Re-run failures only by starting a new campaign/configuration explicitly;
    this prevents an unnoticed change in retry policy from biasing a campaign.
    """
    example_list = tuple(examples)
    if any(item.dataset != config.dataset for item in example_list):
        raise ValueError("Every benchmark example must match config.dataset")
    if len({(item.dataset, item.example_id) for item in example_list}) != len(example_list):
        raise ValueError("Benchmark examples must have unique dataset/example_id keys")
    target = Path(checkpoint_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = list(load_checkpoint(target, config, example_list))
    completed = {(r.dataset, r.example_id, r.repeat_index) for r in existing}
    with target.open("a", encoding="utf-8", newline="\n") as stream:
        for example in example_list:
            for repeat in range(config.repeats):
                key = (example.dataset, example.example_id, repeat)
                if key in completed:
                    continue
                seed = trial_seed(config.base_seed, example.dataset,
                                  example.example_id, repeat)
                context = TrialContext(config, example, repeat, seed)
                try:
                    outcome = adapter(context)
                    if not isinstance(outcome, TrialOutcome):
                        raise TypeError("adapter must return TrialOutcome")
                    record = TrialRecord(
                        config.experiment_id, config.config_hash, example.dataset,
                        example.example_id, example.prompt_hash, repeat, seed,
                        "success", dict(outcome.metrics),
                        tuple(dict(x) for x in outcome.provider_trace),
                        dict(outcome.metadata), None,
                    )
                except Exception as exc:
                    record = TrialRecord(
                        config.experiment_id, config.config_hash, example.dataset,
                        example.example_id, example.prompt_hash, repeat, seed,
                        "failed", error=f"{type(exc).__name__}: {exc}",
                    )
                stream.write(_canonical(asdict(record)) + "\n")
                stream.flush()
                import os
                os.fsync(stream.fileno())
                existing.append(record)
                completed.add(key)
    return tuple(existing)
