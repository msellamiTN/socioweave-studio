import pytest
from sociodec.e1_protocol import E1Condition
from sociodec.extraction import AggregatedExtraction, aggregate_extractions
from sociodec.models.prompt import Interpretation, Prompt
from sociodec.provider_factory import E1ProviderRegistry, ProviderSpec
from sociodec.e1_runtime import build_direct_e1_runtime
from sociodec.direct_baselines import DirectBaselineAdapter
from sociodec.direct_protocol import DirectProtocolStrategyAdapter

class FakeProvider:
    def __init__(self, spec): self.model_name = spec.model_id; self.provider_name = "fake"

def spec(name):
    if name == "m1":
        return ProviderSpec(
            backend="openai-compatible", model_id=name,
            base_url="https://ma.example.invalid/v1", api_key_env="MA_API_KEY",
            provider_name="provider-a", family_id="MA", provider_org="Provider-A",
            weight_access="closed-weight", model_revision="ma-revision-2026-11",
            access_date="2026-11-20",
        )
    if name == "m2":
        return ProviderSpec(
            backend="huggingface-local", model_id=name,
            family_id="MB", provider_org="Provider-B", weight_access="open-weight",
            model_size="small", model_revision="mb-commit-abc123", access_date="2026-11-20",
        )
    if name == "m3":
        return ProviderSpec(
            backend="huggingface-local", model_id=name,
            family_id="MC", provider_org="Provider-C", weight_access="open-weight",
            model_size="large", model_revision="mc-commit-def456", access_date="2026-11-20",
        )
    if name == "executor":
        return ProviderSpec(
            backend="openai-compatible", model_id=name,
            base_url="https://me.example.invalid/v1", api_key_env="ME_API_KEY",
            provider_name="executor-provider", family_id="ME", provider_org="Executor-Provider",
            weight_access="closed-weight", model_revision="me-revision-2026-11",
            access_date="2026-11-20",
        )
    raise ValueError(name)

def registry():
    assignments = {
        "homogeneous": {
            "single-decomposer":spec("m1"), "self-refiner":spec("m1"),
            "self-consistency-sampler":spec("m1"), "decomposer":spec("m1"),
            "separate-evaluator":spec("m1"), "debater-1":spec("m1"),
            "debater-2":spec("m1"), "independent-judge":spec("m1"),
            **{f"nominal-member-{i}":spec("m1") for i in range(1,4)},
            "coordinator":spec("m1"), **{f"specialist-{i}":spec("m1") for i in range(1,4)},
            **{f"expert-{i}":spec("m1") for i in range(1,4)}, "integrator":spec("m1"),
        },
        "heterogeneous": {
            "single-decomposer":spec("m1"), "self-refiner":spec("m2"),
            "self-consistency-sampler":spec("m1"), "decomposer":spec("m2"),
            "separate-evaluator":spec("m3"), "debater-1":spec("m1"),
            "debater-2":spec("m2"), "independent-judge":spec("m3"),
            **{f"nominal-member-{i}":spec(f"m{i}") for i in range(1,4)},
            "coordinator":spec("m1"), **{f"specialist-{i}":spec(f"m{i%2+1}") for i in range(1,4)},
            **{f"expert-{i}":spec(f"m{i%2+1}") for i in range(1,4)}, "integrator":spec("m3"),
        },
    }
    return E1ProviderRegistry(assignments=assignments, executor=spec("executor"),
        provider_builder=FakeProvider)

def condition(method, mode="homogeneous"):
    return E1Condition(dataset="BREAK", method_id=method, model_mode=mode,
        seed=0, prompt_ids=("p1",), call_budget=5,
        matched_strategy_id="S1" if method not in {"S1", "S12"} else None)

def test_runtime_builds_separate_shared_executor_and_baseline_adapter():
    runtime = build_direct_e1_runtime(registry=registry(), executor_id="executor-fixed")
    prompt = Prompt("Make a plan.", Interpretation("Make a plan"))
    extraction = aggregate_extractions(())
    method = runtime.build_method(condition("single_plan_and_solve"), prompt, extraction)
    assert isinstance(method, DirectBaselineAdapter)
    assert runtime.executor.executor_id == "executor-fixed"
    assert runtime.executor.provider.model_name == "executor"
    manifest = runtime.assignment_manifest(
        condition("S1", "homogeneous"),
        ("coordinator", "specialist-1", "specialist-2", "specialist-3"),
    )
    assert manifest["executor_id"] == "executor-fixed"
    assert manifest["executor_model_id"] == "executor"
    assert manifest["agent_model_ids"] == {
        "coordinator": "m1", "specialist-1": "m1",
        "specialist-2": "m1", "specialist-3": "m1",
    }
    assert manifest["agent_model_families"] == {
        "coordinator": "MA", "specialist-1": "MA",
        "specialist-2": "MA", "specialist-3": "MA",
    }
    assert manifest["executor_provenance"]["model_revision"] == "me-revision-2026-11"

def test_runtime_builds_direct_strategy_adapter_without_adaptive_selector():
    runtime = build_direct_e1_runtime(registry=registry(), executor_id="executor-fixed")
    prompt = Prompt("Make a plan.", Interpretation("Make a plan"))
    extraction = aggregate_extractions(())
    method = runtime.build_method(condition("S1", "heterogeneous"), prompt, extraction)
    assert isinstance(method, DirectProtocolStrategyAdapter)

def test_runtime_refuses_to_invent_jigsaw_facets():
    runtime = build_direct_e1_runtime(registry=registry(), executor_id="executor-fixed")
    prompt = Prompt("Make a plan.", Interpretation("Make a plan"))
    extraction = aggregate_extractions(())
    with pytest.raises(ValueError, match="explicit prompt_view_factory"):
        runtime.build_method(condition("S12"), prompt, extraction)


def test_runtime_rejects_debate_judge_from_an_author_family_before_adapter_creation():
    providers = registry()
    providers.assignments["heterogeneous"]["independent-judge"] = spec("m1")
    runtime = build_direct_e1_runtime(registry=providers, executor_id="executor-fixed")
    prompt = Prompt("Debate this plan.", Interpretation("Debate this plan"))
    extraction = aggregate_extractions(())
    with pytest.raises(ValueError, match="distinct from both authors"):
        runtime.build_method(condition("multi_agent_debate", "heterogeneous"), prompt, extraction)
