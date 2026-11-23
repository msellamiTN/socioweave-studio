"""Reproducible experiment campaign primitives (no model/dataset downloads).

The harness records configuration, input identity, deterministic per-trial seeds,
adapter metadata, metrics and failures. It does not claim deterministic LLM output.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from math import isfinite
from typing import Callable, Iterable, Mapping


PAPER_DATASETS = ("BREAK", "StrategyQA", "TaskBench", "TravelPlanner", "smart-administration")
PAPER_EXPERIMENTS = tuple(f"E{i}" for i in range(1, 10))


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class BenchmarkPrompt:
    dataset: str
    example_id: str
    prompt_text: str
    split: str = "test"
    source_version: str = "unspecified"
    metadata: Mapping[str, str | int | float | bool] = field(default_factory=dict)
    reference_data: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.dataset.strip() or not self.example_id.strip() or not self.prompt_text.strip():
            raise ValueError("dataset, example_id and prompt_text must be non-empty")
        if not self.split.strip() or not self.source_version.strip():
            raise ValueError("split and source_version must be non-empty")
        if not isinstance(self.metadata, Mapping):
            raise ValueError("metadata must be a JSON object")
        for key, value in self.metadata.items():
            if not isinstance(key, str):
                raise ValueError("metadata keys must be strings")
            if type(value) not in (str, int, float, bool):
                raise ValueError("metadata values must be scalar strings, integers, finite floats or booleans")
            if isinstance(value, float) and not isfinite(value):
                raise ValueError("metadata floating-point values must be finite")
        if not isinstance(self.reference_data, Mapping):
            raise ValueError("reference_data must be a JSON object")
        try:
            content_hash(dict(self.reference_data))
        except (TypeError, ValueError) as exc:
            raise ValueError("reference_data must contain finite JSON-compatible values") from exc

    @property
    def reference_data_hash(self) -> str:
        return content_hash(dict(self.reference_data))

    @property
    def prompt_hash(self) -> str:
        """Hash the full frozen example, including references and metadata."""
        return content_hash({
            "dataset": self.dataset, "id": self.example_id,
            "prompt": self.prompt_text, "split": self.split,
            "source_version": self.source_version,
            "metadata": dict(self.metadata),
            "reference_data": dict(self.reference_data),
        })


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    experiment_id: str
    dataset: str
    model_families: tuple[str, ...]
    executor_model: str
    strategy_ids: tuple[str, ...]
    n_agents: int = 3
    k_experts: int = 3
    max_rounds: int = 2
    repeats: int = 5
    base_seed: int = 17
    temperature_draft: float = 0.7
    temperature_critique: float = 0.2
    temperature_decision: float = 0.0
    max_tokens_decomposition: int = 1024
    max_tokens_other: int = 512
    config_version: str = "1"

    def __post_init__(self) -> None:
        if self.experiment_id not in PAPER_EXPERIMENTS:
            raise ValueError(f"experiment_id must be one of {PAPER_EXPERIMENTS}")
        if not self.dataset.strip() or not self.executor_model.strip():
            raise ValueError("dataset and executor_model must be non-empty")
        if not self.model_families or not self.strategy_ids:
            raise ValueError("model_families and strategy_ids must be non-empty")
        for name in ("n_agents", "k_experts", "max_rounds", "repeats",
                     "max_tokens_decomposition", "max_tokens_other"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be an integer >= 1")
        for name in ("temperature_draft", "temperature_critique", "temperature_decision"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"{name} must be non-negative")
        if len(set(self.model_families)) != len(self.model_families):
            raise ValueError("model_families must be unique")
        if len(set(self.strategy_ids)) != len(self.strategy_ids):
            raise ValueError("strategy_ids must be unique")

    @property
    def config_hash(self) -> str:
        return content_hash(asdict(self))


@dataclass(frozen=True, slots=True)
class TrialContext:
    config: ExperimentConfig
    example: BenchmarkPrompt
    repeat_index: int
    seed: int


@dataclass(frozen=True, slots=True)
class TrialOutcome:
    metrics: Mapping[str, float]
    provider_trace: tuple[Mapping[str, object], ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in self.metrics.items():
            if not isinstance(name, str) or not name:
                raise ValueError("metric names must be non-empty strings")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"metric {name!r} must be numeric")
            if not float("-inf") < float(value) < float("inf"):
                raise ValueError(f"metric {name!r} must be finite")


@dataclass(frozen=True, slots=True)
class TrialRecord:
    experiment_id: str
    config_hash: str
    dataset: str
    example_id: str
    prompt_hash: str
    repeat_index: int
    seed: int
    status: str
    metrics: Mapping[str, float] = field(default_factory=dict)
    provider_trace: tuple[Mapping[str, object], ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)
    error: str | None = None


def trial_seed(base_seed: int, dataset: str, example_id: str, repeat_index: int) -> int:
    if isinstance(base_seed, bool) or not isinstance(base_seed, int):
        raise TypeError("base_seed must be an integer")
    if repeat_index < 0:
        raise ValueError("repeat_index must be non-negative")
    digest = hashlib.sha256(
        f"{base_seed}\0{dataset}\0{example_id}\0{repeat_index}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big") % (2**31)


class ExperimentRunner:
    """Runs an injected trial adapter and records every success/failure."""

    def __init__(self, config: ExperimentConfig,
                 adapter: Callable[[TrialContext], TrialOutcome]) -> None:
        self.config = config
        self.adapter = adapter

    def run(self, examples: Iterable[BenchmarkPrompt]) -> tuple[TrialRecord, ...]:
        records: list[TrialRecord] = []
        seen: set[tuple[str, str]] = set()
        for example in examples:
            if example.dataset != self.config.dataset:
                raise ValueError(f"example dataset {example.dataset!r} does not match config {self.config.dataset!r}")
            key = (example.dataset, example.example_id)
            if key in seen:
                raise ValueError(f"duplicate benchmark example: {key}")
            seen.add(key)
            for repeat in range(self.config.repeats):
                seed = trial_seed(self.config.base_seed, example.dataset, example.example_id, repeat)
                context = TrialContext(self.config, example, repeat, seed)
                try:
                    outcome = self.adapter(context)
                    if not isinstance(outcome, TrialOutcome):
                        raise TypeError("experiment adapter must return TrialOutcome")
                    records.append(TrialRecord(
                        self.config.experiment_id, self.config.config_hash,
                        example.dataset, example.example_id, example.prompt_hash,
                        repeat, seed, "success", dict(outcome.metrics),
                        tuple(dict(x) for x in outcome.provider_trace),
                        dict(outcome.metadata), None,
                    ))
                except Exception as exc:  # failures are data; campaign continues
                    records.append(TrialRecord(
                        self.config.experiment_id, self.config.config_hash,
                        example.dataset, example.example_id, example.prompt_hash,
                        repeat, seed, "failed", error=f"{type(exc).__name__}: {exc}",
                    ))
        return tuple(records)


def write_jsonl(records: Iterable[TrialRecord], path: str | Path) -> int:
    """Write records as canonical JSONL; overwrite is deliberate and explicit."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(_canonical(asdict(record)) + "\n")
            count += 1
    return count


@dataclass(frozen=True, slots=True)
class CampaignManifest:
    """Environment and immutable input fingerprints for a campaign."""
    config_hash: str
    dataset_sha256: str
    code_commit: str
    python_version: str
    dependency_lock_sha256: str
    seed_derivation: str = "sha256(base_seed, dataset, example_id, repeat_index)"

    def __post_init__(self) -> None:
        for name in ("config_hash", "dataset_sha256", "dependency_lock_sha256"):
            value = getattr(self, name)
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value.lower()):
                raise ValueError(f"{name} must be a SHA-256 hex digest")
        if not self.code_commit.strip() or not self.python_version.strip():
            raise ValueError("code_commit and python_version must be non-empty")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_campaign_manifest(config: ExperimentConfig, dataset_path: str | Path,
                            *, code_commit: str, dependency_lock_path: str | Path) -> CampaignManifest:
    """Fingerprint the exact local dataset and dependency lockfile bytes."""
    return CampaignManifest(
        config_hash=config.config_hash,
        dataset_sha256=sha256_file(dataset_path),
        code_commit=code_commit,
        python_version=sys.version.split()[0],
        dependency_lock_sha256=sha256_file(dependency_lock_path),
    )
