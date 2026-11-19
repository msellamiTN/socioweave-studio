from pathlib import Path

import pytest

from sociodec.direct_e1 import ExecutorRun, MethodRun
from sociodec.direct_e1_campaign import (
    DirectE1CampaignConfig, DirectE1CampaignRunner,
)
from sociodec.e1_protocol import E1Condition
from sociodec.execution import ExecutionRun, ExecutionStatus, SubproblemExecution
from sociodec.experiments import BenchmarkPrompt
from sociodec.extraction import ExtractionResult, aggregate_extractions
from sociodec.models.decomposition import Decomposition, DeliverableComposition, Subproblem
from sociodec.models.prompt import Interpretation, Prompt, Requirement, RequirementType, SourceSpan


REQ = Requirement("Create a report", RequirementType.DELIVERABLE, "report", SourceSpan(0, 16))
PROMPT = Prompt("Create a report.", Interpretation("Create a report", deliverables=("Report",)))
DECOMPOSITION = Decomposition(
    (Subproblem("s1", "Create a report", (), "Report", (), (REQ,)),),
    (), (DeliverableComposition("Report", ("s1",)),),
)
EXTRACTION = aggregate_extractions((
    ExtractionResult(requirements=(REQ,), extractor_id="extractor-1"),
))


class Method:
    def __init__(self, calls):
        self.calls = calls
    def run(self, *, condition, prompt, seed):
        return MethodRun(DECOMPOSITION, self.calls)


class FixedExecutor:
    executor_id = "ME-fixed-v1"
    def execute(self, *, prompt, decomposition, seed):
        return ExecutorRun(
            ExecutionRun(
                self.executor_id,
                (SubproblemExecution("s1", ExecutionStatus.SOLVED, "Report completed"),),
                "Report completed", (),
            ),
            1,
        )


def test_direct_campaign_is_resumable_and_preserves_method_executor_accounting(tmp_path: Path):
    examples = (BenchmarkPrompt(
        "smart-administration", "p1", PROMPT.text, source_version="frozen-v1",
    ),)
    conditions = (
        E1Condition("smart-administration", "S2", "homogeneous", 0, ("p1",), 4),
        E1Condition(
            "smart-administration", "single_plan_and_solve", "homogeneous",
            0, ("p1",), 4, matched_strategy_id="S2",
        ),
    )
    factory_calls = []

    def method_factory(condition, prompt, extraction):
        factory_calls.append(condition.method_id)
        return Method(2 if condition.method_id == "S2" else 1)

    runner = DirectE1CampaignRunner(
        config=DirectE1CampaignConfig("campaign-test", "abc123", "ME-fixed-v1"),
        conditions=conditions, examples=examples,
        prompt_factory=lambda _example: PROMPT,
        extraction_factory=lambda _prompt: EXTRACTION,
        method_factory=method_factory,
        executor=FixedExecutor(),
    )
    checkpoint = tmp_path / "e1.jsonl"
    first = runner.run(checkpoint)
    assert len(first) == 2
    assert {row["status"] for row in first} == {"success"}
    assert all(row["calls_total"] == row["calls_method"] + row["calls_executor"] for row in first)
    assert factory_calls == ["S2", "single_plan_and_solve"]

    second = runner.run(checkpoint)
    assert len(second) == 2
    assert factory_calls == ["S2", "single_plan_and_solve"]


def test_direct_campaign_rejects_unmatched_baseline_budget():
    example = BenchmarkPrompt("smart-administration", "p1", PROMPT.text)
    conditions = (
        E1Condition("smart-administration", "S2", "homogeneous", 0, ("p1",), 4),
        E1Condition(
            "smart-administration", "single_plan_and_solve", "homogeneous",
            0, ("p1",), 3, matched_strategy_id="S2",
        ),
    )
    with pytest.raises(ValueError, match="Budget mismatch"):
        DirectE1CampaignRunner(
            config=DirectE1CampaignConfig("campaign-test", "abc123", "ME-fixed-v1"),
            conditions=conditions, examples=(example,),
            prompt_factory=lambda _example: PROMPT,
            extraction_factory=lambda _prompt: EXTRACTION,
            method_factory=lambda *_args: Method(1),
            executor=FixedExecutor(),
        )


def test_direct_campaign_rejects_changed_checkpoint_config(tmp_path: Path):
    example = BenchmarkPrompt("smart-administration", "p1", PROMPT.text)
    condition = E1Condition("smart-administration", "S2", "homogeneous", 0, ("p1",), 4)
    checkpoint = tmp_path / "changed.jsonl"
    first = DirectE1CampaignRunner(
        config=DirectE1CampaignConfig("campaign-one", "abc123", "ME-fixed-v1"),
        conditions=(condition,), examples=(example,),
        prompt_factory=lambda _example: PROMPT,
        extraction_factory=lambda _prompt: EXTRACTION,
        method_factory=lambda *_args: Method(2), executor=FixedExecutor(),
    )
    first.run(checkpoint)
    second = DirectE1CampaignRunner(
        config=DirectE1CampaignConfig("campaign-two", "abc123", "ME-fixed-v1"),
        conditions=(condition,), examples=(example,),
        prompt_factory=lambda _example: PROMPT,
        extraction_factory=lambda _prompt: EXTRACTION,
        method_factory=lambda *_args: Method(2), executor=FixedExecutor(),
    )
    with pytest.raises(ValueError, match="campaign hash differs"):
        second.run(checkpoint)
