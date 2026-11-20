import pytest

from sociodec.e1_protocol import E1Condition
from sociodec.provider_factory import E1ProviderRegistry, ProviderSpec


class FakeProvider:
    def __init__(self, spec):
        self.model_name = spec.model_id


def spec(model, family="MA", *, provider_org=None, model_size=None):
    if family == "MA":
        return ProviderSpec(
            backend="openai-compatible", model_id=model,
            base_url="https://ma.example.invalid/v1", api_key_env="MA_API_KEY",
            provider_name="provider-a", family_id="MA",
            provider_org=provider_org or "Provider-A", weight_access="closed-weight",
            model_revision="ma-revision-2026-11", access_date="2026-11-20",
        )
    if family == "MB":
        return ProviderSpec(
            backend="huggingface-local", model_id=model,
            family_id="MB", provider_org=provider_org or "Provider-B",
            weight_access="open-weight", model_size=model_size or "small",
            model_revision="mb-commit-abc123", access_date="2026-11-20",
        )
    if family == "MC":
        return ProviderSpec(
            backend="huggingface-local", model_id=model,
            family_id="MC", provider_org=provider_org or "Provider-C",
            weight_access="open-weight", model_size=model_size or "large",
            model_revision="mc-commit-def456", access_date="2026-11-20",
        )
    if family == "ME":
        return ProviderSpec(
            backend="openai-compatible", model_id=model,
            base_url="https://me.example.invalid/v1", api_key_env="ME_API_KEY",
            provider_name="executor-provider", family_id="ME",
            provider_org="Executor-Provider", weight_access="closed-weight",
            model_revision="me-revision-2026-11", access_date="2026-11-20",
        )
    raise ValueError(family)


def condition(mode, method="S1"):
    return E1Condition(
        dataset="BREAK", method_id=method, model_mode=mode,
        seed=0, prompt_ids=("b-001",), call_budget=5,
    )


def registry(assignments):
    return E1ProviderRegistry(
        assignments=assignments, executor=spec("executor-model", "ME"),
        provider_builder=FakeProvider,
    )


def standard_assignments():
    return {
        "homogeneous": {
            "a": spec("m1", "MA"), "b": spec("m1", "MA"), "c": spec("m1", "MA"),
        },
        "heterogeneous": {
            "a": spec("m1", "MA"), "b": spec("m2", "MB"), "c": spec("m3", "MC"),
        },
    }


def test_homogeneous_roster_uses_one_model_and_caches_provider():
    r = registry(standard_assignments())
    c = condition("homogeneous")
    assert r.resolve_models(c, ("a", "b")) == {"a": "m1", "b": "m1"}
    assert r.resolve_model_families(c, ("a", "b")) == {"a": "MA", "b": "MA"}
    assert r.provider_for(c, "a") is r.provider_for(c, "a")


def test_heterogeneous_roster_resolves_three_distinct_provider_families():
    r = registry(standard_assignments())
    c = condition("heterogeneous")
    assert r.resolve_models(c, ("a", "b", "c")) == {"a": "m1", "b": "m2", "c": "m3"}
    assert r.resolve_model_families(c, ("a", "b", "c")) == {
        "a": "MA", "b": "MB", "c": "MC",
    }


def test_heterogeneous_rejects_single_model_assignment():
    assignments = standard_assignments()
    assignments["heterogeneous"] = {
        "a": spec("m1", "MA"), "b": spec("m1", "MA"), "c": spec("m3", "MC"),
    }
    r = registry(assignments)
    with pytest.raises(ValueError, match="at least two distinct model identities"):
        r.resolve_models(condition("heterogeneous"), ("a", "b"))


def test_heterogeneous_rejects_distinct_model_ids_from_one_family():
    assignments = standard_assignments()
    assignments["heterogeneous"] = {
        "a": spec("m1", "MA"), "b": spec("m1-variant", "MA"), "c": spec("m3", "MC"),
        "unused": spec("m2", "MB"),
    }
    r = registry(assignments)
    with pytest.raises(ValueError, match="requires at least 2 distinct model families"):
        r.resolve_model_families(condition("heterogeneous"), ("a", "b"))


def test_model_family_catalogue_requires_three_distinct_provider_organizations():
    assignments = standard_assignments()
    assignments["heterogeneous"]["c"] = spec("m3", "MC", provider_org="Provider-B")
    r = registry(assignments)
    with pytest.raises(ValueError, match="three distinct provider organizations"):
        r.validate_family_catalogue()


def test_model_family_catalogue_requires_different_open_weight_sizes():
    assignments = standard_assignments()
    assignments["heterogeneous"]["c"] = spec("m3", "MC", model_size="small")
    r = registry(assignments)
    with pytest.raises(ValueError, match="different size labels"):
        r.validate_family_catalogue()


def test_missing_agent_assignment_fails_closed():
    r = registry(standard_assignments())
    with pytest.raises(ValueError, match="No provider assignment"):
        r.resolve_models(condition("homogeneous"), ("a", "missing"))


def test_executor_provider_is_separate_and_cached():
    r = registry(standard_assignments())
    executor = r.executor_provider()
    assert executor.model_name == "executor-model"
    assert executor is r.executor_provider()


def test_baseline_debate_judge_must_be_from_family_distinct_from_both_authors():
    assignments = standard_assignments()
    assignments["homogeneous"].update({
        "debater-1": spec("m1", "MA"),
        "debater-2": spec("m1", "MA"),
        "independent-judge": spec("m1", "MA"),
    })
    assignments["heterogeneous"].update({
        "debater-1": spec("m1", "MA"),
        "debater-2": spec("m2", "MB"),
        "independent-judge": spec("m3", "MC"),
    })
    r = registry(assignments)
    assert r.validate_baseline_assignment(
        condition("heterogeneous", "multi_agent_debate"), "multi_agent_debate"
    ) == {"debater-1": "MA", "debater-2": "MB", "independent-judge": "MC"}

    assignments["heterogeneous"]["independent-judge"] = spec("m1", "MA")
    invalid = registry(assignments)
    with pytest.raises(ValueError, match="distinct from both authors"):
        invalid.validate_baseline_assignment(
            condition("heterogeneous", "multi_agent_debate"), "multi_agent_debate"
        )


def test_assignment_manifest_records_non_secret_family_provenance():
    r = registry(standard_assignments())
    manifest = r.assignment_manifest(condition("heterogeneous"), ("a", "b", "c"))
    assert manifest["agent_model_families"] == {"a": "MA", "b": "MB", "c": "MC"}
    assert manifest["agent_model_provenance"]["b"]["model_revision"] == "mb-commit-abc123"
    assert manifest["executor_provenance"]["family_id"] == "ME"
    assert "api_key" not in str(manifest).lower()
