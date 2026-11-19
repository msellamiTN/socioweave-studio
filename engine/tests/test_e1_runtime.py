import pytest
from sociodec.e1_protocol import E1Condition
from sociodec.extraction import aggregate_extractions
from sociodec.models.prompt import Interpretation, Prompt
from sociodec.provider_factory import E1ProviderRegistry, ProviderSpec
from sociodec.e1_runtime import build_direct_e1_runtime
from sociodec.direct_baselines import DirectBaselineAdapter
from sociodec.direct_protocol import DirectProtocolStrategyAdapter

class FakeProvider:
    def __init__(self, spec): self.model_name = spec.model_id; self.provider_name = "fake"

def spec(name): return ProviderSpec(backend="huggingface-local", model_id=name)

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
        matched_strategy_id="S1" if method == "nominal_multi_agent" else None)

def test_runtime_builds_separate_shared_executor_and_baseline_adapter():
    runtime = build_direct_e1_runtime(registry=registry(), executor_id="executor-fixed")
    prompt = Prompt("Make a plan.", Interpretation("Make a plan"))
    extraction = aggregate_extractions(())
    method = runtime.build_method(condition("single_plan_and_solve"), prompt, extraction)
    assert isinstance(method, DirectBaselineAdapter)
    assert runtime.executor.executor_id == "executor-fixed"
    assert runtime.executor.provider.model_name == "executor"

def test_runtime_builds_direct_strategy_adapter_without_adaptive_selector():
    runtime = build_direct_e1_runtime(registry=registry(), executor_id="executor-fixed")
    prompt = Prompt("Make a plan.", Interpretation("Make a plan"))
    extraction = AggregatedExtraction((), ())
    method = runtime.build_method(condition("S1", "heterogeneous"), prompt, extraction)
    assert isinstance(method, DirectProtocolStrategyAdapter)

def test_runtime_refuses_to_invent_jigsaw_facets():
    runtime = build_direct_e1_runtime(registry=registry(), executor_id="executor-fixed")
    prompt = Prompt("Make a plan.", Interpretation("Make a plan"))
    extraction = AggregatedExtraction((), ())
    with pytest.raises(ValueError, match="explicit prompt_view_factory"):
        runtime.build_method(condition("S12"), prompt, extraction)
