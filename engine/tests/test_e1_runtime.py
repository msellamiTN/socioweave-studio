import pytest
from sociodec.e1_protocol import ALL_DATASETS, EXPECTED_PROMPTS, E1Condition, build_e1_conditions
from sociodec.extraction import AggregatedExtraction, aggregate_extractions
from sociodec.experiments import BenchmarkPrompt, content_hash
from sociodec.datasets import DATASET_REGISTRY, E1FrozenSnapshot
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
            weight_access="closed-weight", model_revision=name,
            access_date="2026-11-20",
        )
    if name == "m2":
        return ProviderSpec(
            backend="huggingface-local", model_id=name,
            family_id="MB", provider_org="Provider-B", weight_access="open-weight",
            model_size="small", model_revision="a" * 40, access_date="2026-11-20",
        )
    if name == "m3":
        return ProviderSpec(
            backend="huggingface-local", model_id=name,
            family_id="MC", provider_org="Provider-C", weight_access="open-weight",
            model_size="large", model_revision="b" * 40, access_date="2026-11-20",
        )
    if name == "executor":
        return ProviderSpec(
            backend="openai-compatible", model_id=name,
            base_url="https://me.example.invalid/v1", api_key_env="ME_API_KEY",
            provider_name="executor-provider", family_id="ME", provider_org="Executor-Provider",
            weight_access="closed-weight", model_revision=name,
            access_date="2026-11-20",
        )
    raise ValueError(name)

def registry():
    required_agents = {
        "coordinator", "specialist-1", "specialist-2", "specialist-3",
        "expert-1", "expert-2", "expert-3", "integrator",
        "participant-1", "participant-2", "participant-3", "aggregator",
        "member-1", "member-2", "member-3", "voter-1", "voter-2", "voter-3",
        "facilitator", "author", "critic", "judge", "decomposer-1", "decomposer-2",
        "synthesizer", "reviewer-1", "reviewer-2", "reviewer-3", "editor",
        "agent-A", "agent-B", "party-1", "party-2", "mediator", "moderator",
        "single-decomposer", "self-refiner", "self-consistency-sampler",
        "decomposer", "separate-evaluator", "debater-1", "debater-2",
        "independent-judge", "nominal-member-1", "nominal-member-2", "nominal-member-3",
    }
    family_b = {
        "specialist-2", "expert-2", "participant-2", "member-2", "voter-2",
        "critic", "decomposer-2", "reviewer-2", "agent-B", "party-2",
        "self-refiner", "debater-2", "nominal-member-2",
    }
    family_a = {
        "coordinator", "specialist-1", "expert-1", "participant-1", "member-1",
        "voter-1", "author", "decomposer-1", "reviewer-1", "agent-A", "party-1",
        "single-decomposer", "self-consistency-sampler", "decomposer", "debater-1",
        "nominal-member-1",
    }
    heterogeneous = {agent: spec("m3") for agent in required_agents}
    heterogeneous.update({agent: spec("m1") for agent in family_a})
    heterogeneous.update({agent: spec("m2") for agent in family_b})
    homogeneous = {agent: spec("m1") for agent in required_agents}
    assignments = {"homogeneous": homogeneous, "heterogeneous": heterogeneous}
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
    assert manifest["executor_provenance"]["model_revision"] == "executor"

def test_runtime_exports_full_non_secret_campaign_model_manifest():
    runtime = build_direct_e1_runtime(registry=registry(), executor_id="executor-fixed")
    manifest = runtime.campaign_manifest()
    assert manifest["schema_version"] == "e1-provider-manifest-v1"
    assert set(manifest["model_modes"]) == {"homogeneous", "heterogeneous"}
    assert set(manifest["model_family_catalogue"]) == {"MA", "MB", "MC"}
    assert manifest["executor"]["executor_id"] == "executor-fixed"
    assert manifest["executor"]["provenance"]["model_revision"] == "executor"
    assert manifest["executor"]["connection"]["api_key_env"] == "ME_API_KEY"
    assert manifest["model_modes"]["homogeneous"]["coordinator"]["connection"]["api_key_env"] == "MA_API_KEY"
    assert manifest["model_modes"]["heterogeneous"]["specialist-2"]["connection"]["base_url"] is None
    assert "'api_key':" not in str(manifest).lower()
    assert "'secret':" not in str(manifest).lower()


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


def test_runtime_rejects_missing_agent_provider_assignments_before_building_executor():
    providers = registry()
    del providers.assignments["heterogeneous"]["reviewer-3"]
    with pytest.raises(ValueError, match="provider roster is incomplete"):
        build_direct_e1_runtime(registry=providers, executor_id="executor-fixed")


def frozen_snapshot_fixture():
    expected_ids = {
        dataset: tuple(f"{dataset}-{i:03d}" for i in range(EXPECTED_PROMPTS[dataset]))
        for dataset in ALL_DATASETS
    }
    examples = tuple(
        BenchmarkPrompt(
            dataset, example_id, f"fixture prompt {example_id}",
            split="test", source_version=f"{dataset}-fixture-v1",
            reference_data={"fixture_annotation": "synthetic test fixture only"},
        )
        for dataset, ids in expected_ids.items() for example_id in ids
    )
    entries = {}
    for dataset, ids in expected_ids.items():
        dataset_examples = [item for item in examples if item.dataset == dataset]
        entries[dataset] = {
            "source_file": f"{dataset}.jsonl",
            "source_sha256": "f" * 64,
            "source_version": f"{dataset}-fixture-v1",
            "split": "test",
            "selection_protocol": "synthetic test fixture only",
            "selection_seed": None,
            "license_review_status": "approved",
            "paper_source_url": DATASET_REGISTRY[dataset]["paper_source_url"],
            "prompt_case": DATASET_REGISTRY[dataset]["prompt_case"],
            "reference_provided": DATASET_REGISTRY[dataset]["reference_provided"],
            "metrics": list(DATASET_REGISTRY[dataset]["metrics"]),
            "coverage_applicable": DATASET_REGISTRY[dataset]["coverage_applicable"],
            "source_release_status": DATASET_REGISTRY[dataset]["source_release_status"],
            "prompt_count": len(ids),
            "prompt_ids": list(ids),
            "prompt_sha256": {item.example_id: item.prompt_hash for item in dataset_examples},
            "reference_data_sha256": {
                item.example_id: item.reference_data_hash for item in dataset_examples
            },
        }
    manifest = {
        "schema_version": "e1-frozen-benchmark-snapshot-v1",
        "dataset_order": list(ALL_DATASETS),
        "datasets": entries,
        "total_prompt_count": len(examples),
        "snapshot_sha256": content_hash({"datasets": entries}),
    }
    return E1FrozenSnapshot(examples, expected_ids, manifest)


def full_conditions_fixture():
    snapshot = frozen_snapshot_fixture()
    return snapshot, build_e1_conditions(expected_prompt_ids=snapshot.expected_prompt_ids)


def test_no_call_preflight_validates_complete_e1_grid_and_all_provider_rosters():
    providers = registry()
    runtime = build_direct_e1_runtime(
        registry=providers, executor_id="executor-fixed",
        
    )
    snapshot, conditions = full_conditions_fixture()
    report = runtime.preflight_campaign(snapshot=snapshot, conditions=conditions)
    assert report.condition_count == 4550
    assert report.prompt_count == 460
    assert report.provider_rosters_validated == 38
    assert report.live_provider_calls == 0
    assert report.readiness == "configuration_validated_no_live_calls"
    assert len(report.dataset_snapshot_sha256) == 64
    assert len(report.provider_manifest_sha256) == 64
    assert len(report.conditions_sha256) == 64


def test_no_call_preflight_rejects_unversioned_custom_jigsaw_factory():
    runtime = build_direct_e1_runtime(
        registry=registry(), executor_id="executor-fixed",
        prompt_view_factory=lambda _sid, _prompt, _extraction, ids: {
            agent_id: "custom facet view" for agent_id in ids
        },
    )
    snapshot, conditions = full_conditions_fixture()
    with pytest.raises(ValueError, match="versioned Jigsaw facet policy"):
        runtime.preflight_campaign(snapshot=snapshot, conditions=conditions)


def test_no_call_preflight_rejects_snapshot_manifest_tampering():
    runtime = build_direct_e1_runtime(
        registry=registry(), executor_id="executor-fixed",
        prompt_view_factory=lambda _sid, _prompt, _extraction, ids: {
            agent_id: "explicit facet fixture" for agent_id in ids
        },
    )
    snapshot, conditions = full_conditions_fixture()
    changed = dict(snapshot.manifest)
    changed_entries = dict(changed["datasets"])
    changed_break = dict(changed_entries["BREAK"])
    changed_break["source_sha256"] = "0" * 64
    changed_entries["BREAK"] = changed_break
    changed["datasets"] = changed_entries
    tampered = E1FrozenSnapshot(snapshot.examples, snapshot.expected_prompt_ids, changed)
    with pytest.raises(ValueError, match="snapshot manifest SHA-256"):
        runtime.preflight_campaign(snapshot=tampered, conditions=conditions)


def test_no_call_preflight_rejects_heterogeneous_judge_family_collision():
    providers = registry()
    providers.assignments["heterogeneous"]["editor"] = spec("m1")
    runtime = build_direct_e1_runtime(
        registry=providers, executor_id="executor-fixed",
        prompt_view_factory=lambda _sid, _prompt, _extraction, ids: {
            agent_id: "explicit facet fixture" for agent_id in ids
        },
    )
    snapshot, conditions = full_conditions_fixture()
    with pytest.raises(ValueError, match="judge editor shares a model family"):
        runtime.preflight_campaign(snapshot=snapshot, conditions=conditions)



def test_provider_spec_rejects_embedded_credentials_and_invalid_secret_variable_names():
    with pytest.raises(ValueError, match="must not embed credentials"):
        ProviderSpec(
            backend="openai-compatible", model_id="unsafe",
            base_url="https://user:password@example.invalid/v1",
            api_key_env="MA_API_KEY",
        )
    with pytest.raises(ValueError, match="environment-variable name"):
        ProviderSpec(
            backend="openai-compatible", model_id="unsafe",
            base_url="https://example.invalid/v1",
            api_key_env="MA-API-KEY",
        )
