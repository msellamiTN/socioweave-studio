import json
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

PROVIDER_MANIFEST = {
    "schema_version": "e1-provider-manifest-v1",
    "model_modes": {
        "homogeneous": {
            "agent-1": {"model_id": "MA-v1", "backend": "openai-compatible",
                        "provenance": {"family_id": "MA", "model_revision": "MA-v1",
                                       "access_date": "2026-11-20"}},
        },
        "heterogeneous": {
            "agent-1": {"model_id": "MA-v1", "backend": "openai-compatible",
                        "provenance": {"family_id": "MA", "model_revision": "MA-v1",
                                       "access_date": "2026-11-20"}},
            "agent-2": {"model_id": "MB-v1", "backend": "huggingface-local",
                        "provenance": {"family_id": "MB", "model_revision": "a" * 40,
                                       "access_date": "2026-11-20"}},
            "agent-3": {"model_id": "MC-v1", "backend": "huggingface-local",
                        "provenance": {"family_id": "MC", "model_revision": "b" * 40,
                                       "access_date": "2026-11-20"}},
        },
    },
    "model_family_catalogue": {
        "MA": {"family_id": "MA", "provider_org": "Provider-A",
               "weight_access": "closed-weight", "model_revision": "MA-v1",
               "model_id": "MA-v1", "backend": "openai-compatible",
               "access_date": "2026-11-20"},
        "MB": {"family_id": "MB", "provider_org": "Provider-B",
               "weight_access": "open-weight", "model_size": "small",
               "model_revision": "a" * 40, "model_id": "MB-v1",
               "backend": "huggingface-local", "access_date": "2026-11-20"},
        "MC": {"family_id": "MC", "provider_org": "Provider-C",
               "weight_access": "open-weight", "model_size": "large",
               "model_revision": "b" * 40, "model_id": "MC-v1",
               "backend": "huggingface-local", "access_date": "2026-11-20"},
    },
    "executor": {
        "executor_id": "ME-fixed-v1", "model_id": "ME-v1",
        "backend": "openai-compatible",
        "provenance": {"family_id": "ME", "model_revision": "ME-v1",
                       "access_date": "2026-11-20"},
    },
}


def campaign_config(campaign_id, code_commit="abc123", manifest=None):
    return DirectE1CampaignConfig(
        campaign_id, code_commit, "ME-fixed-v1",
        provider_manifest_json=json.dumps(manifest or PROVIDER_MANIFEST),
    )


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
        reference_data={"fixture_annotation": "synthetic test fixture only"},
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
        config=campaign_config("campaign-test"),
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
    manifest_path = checkpoint.with_suffix(checkpoint.suffix + ".manifest.json")
    saved_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert saved_manifest["schema_version"] == "e1-campaign-execution-manifest-v1"
    assert saved_manifest["provider_manifest_hash"] == runner.config.provider_manifest_hash
    assert saved_manifest["provider_manifest"] == PROVIDER_MANIFEST
    assert all(row["provider_manifest_hash"] == runner.config.provider_manifest_hash for row in first)

    second = runner.run(checkpoint)
    assert len(second) == 2
    assert factory_calls == ["S2", "single_plan_and_solve"]


def test_direct_campaign_rejects_unmatched_baseline_budget():
    example = BenchmarkPrompt(
        "smart-administration", "p1", PROMPT.text,
        reference_data={"fixture_annotation": "synthetic test fixture only"},
    )
    conditions = (
        E1Condition("smart-administration", "S2", "homogeneous", 0, ("p1",), 4),
        E1Condition(
            "smart-administration", "single_plan_and_solve", "homogeneous",
            0, ("p1",), 3, matched_strategy_id="S2",
        ),
    )
    with pytest.raises(ValueError, match="Budget mismatch"):
        DirectE1CampaignRunner(
            config=campaign_config("campaign-test"),
            conditions=conditions, examples=(example,),
            prompt_factory=lambda _example: PROMPT,
            extraction_factory=lambda _prompt: EXTRACTION,
            method_factory=lambda *_args: Method(1),
            executor=FixedExecutor(),
        )


def test_direct_campaign_rejects_changed_checkpoint_config(tmp_path: Path):
    example = BenchmarkPrompt(
        "smart-administration", "p1", PROMPT.text,
        reference_data={"fixture_annotation": "synthetic test fixture only"},
    )
    condition = E1Condition("smart-administration", "S2", "homogeneous", 0, ("p1",), 4)
    checkpoint = tmp_path / "changed.jsonl"
    first = DirectE1CampaignRunner(
        config=campaign_config("campaign-one"),
        conditions=(condition,), examples=(example,),
        prompt_factory=lambda _example: PROMPT,
        extraction_factory=lambda _prompt: EXTRACTION,
        method_factory=lambda *_args: Method(2), executor=FixedExecutor(),
    )
    first.run(checkpoint)
    second = DirectE1CampaignRunner(
        config=campaign_config("campaign-two"),
        conditions=(condition,), examples=(example,),
        prompt_factory=lambda _example: PROMPT,
        extraction_factory=lambda _prompt: EXTRACTION,
        method_factory=lambda *_args: Method(2), executor=FixedExecutor(),
    )
    with pytest.raises(ValueError, match="campaign manifest differs"):
        second.run(checkpoint)


@pytest.mark.parametrize("mutation,match", [
    ("foreign_row", "not part of the frozen campaign"),
    ("prompt_hash", "prompt hash differs"),
    ("provider_manifest_hash", "provider manifest hash differs"),
])
def test_direct_campaign_rejects_tampered_checkpoint_rows(tmp_path: Path, mutation, match):
    example = BenchmarkPrompt(
        "smart-administration", "p1", PROMPT.text,
        reference_data={"fixture_annotation": "synthetic test fixture only"},
    )
    condition = E1Condition("smart-administration", "S2", "homogeneous", 0, ("p1",), 4)
    checkpoint = tmp_path / "tampered.jsonl"
    runner = DirectE1CampaignRunner(
        config=campaign_config("campaign-integrity"),
        conditions=(condition,), examples=(example,),
        prompt_factory=lambda _example: PROMPT,
        extraction_factory=lambda _prompt: EXTRACTION,
        method_factory=lambda *_args: Method(2), executor=FixedExecutor(),
    )
    runner.run(checkpoint)
    row = json.loads(checkpoint.read_text(encoding="utf-8"))
    if mutation == "foreign_row":
        row["example_id"] = "not-in-campaign"
    elif mutation == "prompt_hash":
        row["prompt_hash"] = "0" * 64
    else:
        row["provider_manifest_hash"] = "0" * 64
    checkpoint.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        runner.run(checkpoint)


def test_direct_campaign_row_identity_distinguishes_model_modes(tmp_path: Path):
    example = BenchmarkPrompt(
        "smart-administration", "p1", PROMPT.text,
        reference_data={"fixture_annotation": "synthetic test fixture only"},
    )
    conditions = (
        E1Condition("smart-administration", "S2", "homogeneous", 0, ("p1",), 4),
        E1Condition("smart-administration", "S2", "heterogeneous", 0, ("p1",), 4),
    )
    calls = []
    runner = DirectE1CampaignRunner(
        config=campaign_config("campaign-modes"),
        conditions=conditions, examples=(example,),
        prompt_factory=lambda _example: PROMPT,
        extraction_factory=lambda _prompt: EXTRACTION,
        method_factory=lambda condition, *_args: (calls.append(condition.model_mode) or Method(2)),
        executor=FixedExecutor(),
    )
    checkpoint = tmp_path / "modes.jsonl"
    rows = runner.run(checkpoint)
    assert len(rows) == 2
    assert {row["model_mode"] for row in rows} == {"homogeneous", "heterogeneous"}
    assert calls == ["homogeneous", "heterogeneous"]
    assert len(runner.run(checkpoint)) == 2
    assert calls == ["homogeneous", "heterogeneous"]


def test_campaign_config_requires_a_complete_secret_free_provider_manifest():
    with pytest.raises(ValueError, match="provider_manifest_json is required"):
        DirectE1CampaignConfig("missing-manifest", "abc123", "ME-fixed-v1")
    with pytest.raises(ValueError, match="must not contain credentials"):
        campaign_config("secret-manifest", manifest={
            **PROVIDER_MANIFEST,
            "credentials": {"api_key": "do-not-store"},
        })


def test_changed_provider_manifest_cannot_resume_existing_checkpoint(tmp_path: Path):
    example = BenchmarkPrompt(
        "smart-administration", "p1", PROMPT.text,
        reference_data={"fixture_annotation": "synthetic test fixture only"},
    )
    condition = E1Condition("smart-administration", "S2", "homogeneous", 0, ("p1",), 4)
    checkpoint = tmp_path / "provider-change.jsonl"
    first = DirectE1CampaignRunner(
        config=campaign_config("same-campaign"),
        conditions=(condition,), examples=(example,),
        prompt_factory=lambda _example: PROMPT,
        extraction_factory=lambda _prompt: EXTRACTION,
        method_factory=lambda *_args: Method(2), executor=FixedExecutor(),
    )
    first.run(checkpoint)
    changed_manifest = json.loads(json.dumps(PROVIDER_MANIFEST))
    changed_manifest["model_modes"]["heterogeneous"]["agent-2"]["model_id"] = "MB-rotated"
    changed_manifest["model_family_catalogue"]["MB"]["model_id"] = "MB-rotated"
    second = DirectE1CampaignRunner(
        config=campaign_config("same-campaign", manifest=changed_manifest),
        conditions=(condition,), examples=(example,),
        prompt_factory=lambda _example: PROMPT,
        extraction_factory=lambda _prompt: EXTRACTION,
        method_factory=lambda *_args: Method(2), executor=FixedExecutor(),
    )
    with pytest.raises(ValueError, match="campaign manifest differs"):
        second.run(checkpoint)


def test_campaign_rejects_prompt_without_structured_reference_data():
    example = BenchmarkPrompt("smart-administration", "p1", PROMPT.text)
    condition = E1Condition("smart-administration", "S2", "homogeneous", 0, ("p1",), 4)
    with pytest.raises(ValueError, match="structured Table 12 reference data"):
        DirectE1CampaignRunner(
            config=campaign_config("missing-reference"),
            conditions=(condition,), examples=(example,),
            prompt_factory=lambda _example: PROMPT,
            extraction_factory=lambda _prompt: EXTRACTION,
            method_factory=lambda *_args: Method(2), executor=FixedExecutor(),
        )


def test_changed_reference_data_cannot_resume_existing_checkpoint(tmp_path: Path):
    condition = E1Condition("smart-administration", "S2", "homogeneous", 0, ("p1",), 4)
    checkpoint = tmp_path / "reference-change.jsonl"
    first_example = BenchmarkPrompt(
        "smart-administration", "p1", PROMPT.text,
        reference_data={"gold_decomposition": {"steps": ["A", "B"]}},
    )
    first = DirectE1CampaignRunner(
        config=campaign_config("same-reference-campaign"),
        conditions=(condition,), examples=(first_example,),
        prompt_factory=lambda _example: PROMPT,
        extraction_factory=lambda _prompt: EXTRACTION,
        method_factory=lambda *_args: Method(2), executor=FixedExecutor(),
    )
    first.run(checkpoint)
    changed_example = BenchmarkPrompt(
        "smart-administration", "p1", PROMPT.text,
        reference_data={"gold_decomposition": {"steps": ["A", "C"]}},
    )
    second = DirectE1CampaignRunner(
        config=campaign_config("same-reference-campaign"),
        conditions=(condition,), examples=(changed_example,),
        prompt_factory=lambda _example: PROMPT,
        extraction_factory=lambda _prompt: EXTRACTION,
        method_factory=lambda *_args: Method(2), executor=FixedExecutor(),
    )
    with pytest.raises(ValueError, match="campaign manifest differs"):
        second.run(checkpoint)
