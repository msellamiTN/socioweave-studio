from sociodec.e1_protocol import E1Condition
from sociodec.provider_factory import E1ProviderRegistry, ProviderSpec

class FakeProvider:
    def __init__(self, spec): self.model_name = spec.model_id

def condition(mode):
    return E1Condition(dataset="BREAK", method_id="S1", model_mode=mode,
        seed=0, prompt_ids=("b-001",), call_budget=5)

def spec(model): return ProviderSpec(backend="huggingface-local", model_id=model)

def registry(assignments):
    return E1ProviderRegistry(assignments=assignments, executor=spec("executor-model"),
        provider_builder=FakeProvider)

def test_homogeneous_roster_uses_one_model_and_caches_provider():
    r = registry({"homogeneous":{"coordinator":spec("m1"),"specialist-1":spec("m1")},
        "heterogeneous":{"coordinator":spec("m1"),"specialist-1":spec("m2")}})
    c = condition("homogeneous")
    assert r.resolve_models(c,("coordinator","specialist-1")) == {"coordinator":"m1","specialist-1":"m1"}
    assert r.provider_for(c,"coordinator") is r.provider_for(c,"coordinator")

def test_heterogeneous_roster_requires_two_distinct_models():
    r = registry({"homogeneous":{"a":spec("m1")},
        "heterogeneous":{"a":spec("m1"),"b":spec("m2")}})
    assert len(set(r.resolve_models(condition("heterogeneous"),("a","b")).values())) == 2

def test_heterogeneous_rejects_single_model_assignment():
    r = registry({"homogeneous":{"a":spec("m1")},
        "heterogeneous":{"a":spec("m1"),"b":spec("m1")}})
    try: r.resolve_models(condition("heterogeneous"),("a","b"))
    except ValueError as exc: assert "at least two" in str(exc)
    else: raise AssertionError("heterogeneous condition accepted one model")

def test_missing_agent_assignment_fails_closed():
    r = registry({"homogeneous":{"a":spec("m1")},"heterogeneous":{"a":spec("m1"),"b":spec("m2")}})
    try: r.resolve_models(condition("homogeneous"),("a","missing"))
    except ValueError as exc: assert "No provider assignment" in str(exc)
    else: raise AssertionError("missing agent assignment was silently accepted")

def test_executor_provider_is_separate_and_cached():
    r = registry({"homogeneous":{"a":spec("m1")},"heterogeneous":{"a":spec("m1"),"b":spec("m2")}})
    executor = r.executor_provider()
    assert executor.model_name == "executor-model"
    assert executor is r.executor_provider()
