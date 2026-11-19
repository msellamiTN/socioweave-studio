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
from typing import Callable, Iterable

from sociodec.direct_e1 import (
    DirectE1Result, DirectMethodAdapter, E1FixedExecutor, run_direct_e1_condition,
)
from sociodec.e1_protocol import BASELINES, E1Condition
from sociodec.experiments import BenchmarkPrompt, content_hash
from sociodec.extraction import AggregatedExtraction
from sociodec.models.prompt import Prompt


PromptFactory = Callable[[BenchmarkPrompt], Prompt]
ExtractionFactory = Callable[[Prompt], AggregatedExtraction]
MethodFactory = Callable[[E1Condition, Prompt, AggregatedExtraction], DirectMethodAdapter]
UtilityScorer = Callable[[Prompt, str], float]


@dataclass(frozen=True, slots=True)
class DirectE1CampaignConfig:
    campaign_id: str
    code_commit: str
    executor_id: str
    protocol_profile: str = "paper-e1-direct-v1"
    retry_failed: bool = False

    def __post_init__(self) -> None:
        if not self.campaign_id.strip() or not self.code_commit.strip() or not self.executor_id.strip():
            raise ValueError("campaign_id, code_commit and executor_id must be non-empty")
        if self.retry_failed:
            raise ValueError("In-place retry is disabled; use a new campaign_id/configuration")


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
            "campaign_config_hash": content_hash(config.__dict__ if hasattr(config, "__dict__") else {
                "campaign_id": config.campaign_id, "code_commit": config.code_commit,
                "executor_id": config.executor_id, "protocol_profile": config.protocol_profile,
            }),
            "code_commit": config.code_commit,
            "protocol_profile": config.protocol_profile,
            "dataset": condition.dataset, "example_id": example.example_id,
            "method_id": condition.method_id, "model_mode": condition.model_mode,
            "seed": condition.seed, "matched_strategy_id": condition.matched_strategy_id,
            "method_call_budget": condition.call_budget,
            "prompt_hash": example.prompt_hash, "status": "failed", "error": error,
        }
    return {
        "campaign_id": config.campaign_id,
        "campaign_config_hash": content_hash({
            "campaign_id": config.campaign_id, "code_commit": config.code_commit,
            "executor_id": config.executor_id, "protocol_profile": config.protocol_profile,
        }),
        "code_commit": config.code_commit,
        "protocol_profile": config.protocol_profile,
        "dataset": result.dataset, "example_id": result.example_id,
        "method_id": result.method_id, "model_mode": result.model_mode,
        "seed": result.seed, "matched_strategy_id": result.matched_strategy_id,
        "executor_id": result.executor_id,
        "method_call_budget": result.call_budget,
        "calls_method": result.calls_method, "calls_executor": result.calls_executor,
        "calls_total": result.calls_total,
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
        if executor.executor_id != config.executor_id:
            raise ValueError("Executor instance does not match the preregistered fixed executor ID")
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
        config_hash = content_hash({
            "campaign_id": self.config.campaign_id,
            "code_commit": self.config.code_commit,
            "executor_id": self.config.executor_id,
            "protocol_profile": self.config.protocol_profile,
            "conditions": [_condition_key(x) for x in self.conditions],
            # Prompt IDs alone do not freeze benchmark content. Bind the
            # checkpoint to the exact prompt snapshots used by this campaign.
            "prompt_snapshot": sorted(
                (dataset, example_id, example.prompt_hash)
                for (dataset, example_id), example in self.examples.items()
                if any(
                    condition.dataset == dataset and example_id in condition.prompt_ids
                    for condition in self.conditions
                )
            ),
        })
        expected_rows = {
            (
                condition.dataset, prompt_id, condition.method_id,
                condition.seed, condition.matched_strategy_id,
            )
            for condition in self.conditions
            for prompt_id in condition.prompt_ids
        }
        completed: set[tuple[str, str, str, int, str | None]] = set()
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
                    key = (
                        row.get("dataset"), row.get("example_id"), row.get("method_id"),
                        row.get("seed"), row.get("matched_strategy_id"),
                    )
                    if key not in expected_rows:
                        raise ValueError(f"Checkpoint row is not part of the frozen campaign: {key}")
                    expected_prompt_hash = self.examples[(key[0], key[1])].prompt_hash
                    if row.get("prompt_hash") != expected_prompt_hash:
                        raise ValueError(f"Checkpoint prompt hash differs from frozen prompt snapshot: {key}")
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
                        condition.seed, condition.matched_strategy_id,
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
