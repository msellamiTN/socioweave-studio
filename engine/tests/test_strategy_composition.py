import json

import pytest

from sociodec.catalogue import StrategyId
from sociodec.extraction import AggregatedExtraction, Hypothesis
from sociodec.models.prompt import Constraint, ConstraintKind, Interpretation, Prompt, Requirement, RequirementType, SourceSpan
from sociodec.orchestrator import StrategyOutcome
from sociodec.selector import PlanItem
from sociodec.strategy_composition import DomainPartition, build_domain_prompt_views, SequentialCompositionExecutor
from sociodec.validation import HypothesisVerdict, HypothesisVerdictValue


def _prompt():
    return Prompt("Build a service for users and operators.", Interpretation(
        "Build a service", (Constraint("Accessible", ConstraintKind.HARD),),
        ("user data",), ("Working service",),
    ))


def _extraction():
    reqs = (
        Requirement("Serve users", RequirementType.TARGET, "users", SourceSpan(0, 5)),
        Requirement("Manage operators", RequirementType.TARGET, "operations", SourceSpan(6, 10)),
    )
    hyps = (Hypothesis("Audit operations", RequirementType.CONSTRAINT, "operations", "Regulatory context"),)
    return AggregatedExtraction(reqs, hyps, (), (), (), {}, {}, ())


@pytest.mark.parametrize("sid,prefix,integrator", [
    (StrategyId.S1, "specialist-", "coordinator"),
    (StrategyId.S12, "expert-", "integrator"),
])
def test_domain_views_partition_all_extracted_domains_without_cross_leakage(sid, prefix, integrator):
    partition = DomainPartition({
        f"{prefix}1": ("users",),
        f"{prefix}2": ("operations",),
    })
    views = build_domain_prompt_views(
        _prompt(), _extraction(), strategy_id=sid,
        partition=partition, integrator_id=integrator,
    )
    user_view = json.loads(views[f"{prefix}1"])
    ops_view = json.loads(views[f"{prefix}2"])
    assert [x["domain"] for x in user_view["explicit_requirements"]] == ["users"]
    assert [x["domain"] for x in ops_view["explicit_requirements"]] == ["operations"]
    assert len(ops_view["implicit_hypotheses"]) == 1
    assert "Manage operators" not in views[f"{prefix}1"]
    assert views[integrator] == _prompt().text


def test_domain_views_reject_missing_or_unknown_domains():
    with pytest.raises(ValueError, match="mismatch"):
        build_domain_prompt_views(
            _prompt(), _extraction(), strategy_id="S1",
            partition=DomainPartition({"specialist-1": ("users",)}),
        )


def test_domain_views_reject_non_partitioned_strategy():
    with pytest.raises(ValueError, match="only for S1 and S12"):
        build_domain_prompt_views(
            _prompt(), _extraction(), strategy_id="S2",
            partition=DomainPartition({"specialist-1": ("users", "operations")}),
        )


def test_domain_partition_rejects_duplicate_domain_assignments():
    with pytest.raises(ValueError, match="exactly one"):
        DomainPartition({"specialist-1": ("users",), "specialist-2": ("users",)})


def test_sequential_composition_seeds_second_phase_and_accumulates_calls_and_evidence():
    class Adapter:
        def __init__(self):
            self.calls = []
        def __call__(self, item, prompt, extraction, drafts, seed, allowance):
            self.calls.append((item, seed, allowance))
            from sociodec.models.decomposition import Decomposition
            decomposition = Decomposition((), (), ())
            verdict = HypothesisVerdict(_extraction().hypotheses[0], HypothesisVerdictValue.CONFIRMED)
            return StrategyOutcome(
                decomposition, 2, hypothesis_verdicts=(verdict,),
                strategy_run_id=item.value,
            )
    adapter = Adapter()
    executor = SequentialCompositionExecutor(adapter)
    external_seed = object()
    result = executor(
        PlanItem.C8_BRAINSTORM_THEN_REVIEW, _prompt(), _extraction(),
        (None, None), external_seed, 10,
    )
    assert adapter.calls[0][0] is PlanItem.S2
    assert adapter.calls[0][1] is None  # first phase must not consume any external seed
    assert adapter.calls[1][0] is PlanItem.S8
    assert adapter.calls[1][1] == result.decomposition
    assert [x[2] for x in adapter.calls] == [4, 6]
    assert result.calls_made == 4
    assert result.strategy_run_id.startswith("C8:")


def test_sequential_composition_rejects_c1_phase_pipeline():
    executor = SequentialCompositionExecutor(lambda *args: None)
    with pytest.raises(ValueError, match="dedicated Algorithm 3"):
        executor(
            PlanItem.COMBO_FULL_PIPELINE, _prompt(), _extraction(),
            (None, None), None, 20,
        )


def test_sequential_composition_rejects_conflicting_hypothesis_verdicts():
    class Adapter:
        def __init__(self):
            self.i = 0
        def __call__(self, item, *args):
            from sociodec.models.decomposition import Decomposition
            self.i += 1
            value = HypothesisVerdictValue.CONFIRMED if self.i == 1 else HypothesisVerdictValue.REJECTED
            return StrategyOutcome(
                Decomposition((), (), ()), 1,
                hypothesis_verdicts=(HypothesisVerdict(_extraction().hypotheses[0], value),),
            )
    with pytest.raises(ValueError, match="Conflicting chained"):
        SequentialCompositionExecutor(Adapter())(
            PlanItem.COMBO_JIGSAW_THEN_CRITIC, _prompt(), _extraction(),
            (None, None), None, 8,
        )



@pytest.mark.parametrize("item,expected_first,expected_second,expected_calls", [
    (PlanItem.C8_BRAINSTORM_THEN_REVIEW, PlanItem.S2, PlanItem.S8, 7),
    (PlanItem.COMBO_JIGSAW_THEN_CRITIC, PlanItem.S12, PlanItem.S5, 6),
])
def test_provider_backed_sequential_compositions_execute_through_real_adapter_runtime(
    item, expected_first, expected_second, expected_calls,
):
    from sociodec.decisions import DecisionResult
    from sociodec.models.decomposition import Decomposition, Subproblem
    from sociodec.providers.base import GenerationResult
    from sociodec.providers.protocol_invoker import ProviderProtocolInvoker
    from sociodec.strategy_adapter import ConcreteStrategyAdapter, DecodedStrategyResult

    class RecordingProvider:
        provider_name = "recording-provider"
        model_name = "model-v2"
        def __init__(self):
            self.calls = []
        def generate(self, messages, config=None):
            self.calls.append(messages)
            return GenerationResult(
                "opaque protocol response", self.provider_name, self.model_name,
                10, 5, "stop", f"request-{len(self.calls)}",
            )

    decomposition = Decomposition(
        (Subproblem("s1", "Build service", (), "Service", (), ()),), (), (),
    )
    provider = RecordingProvider()
    invoker = ProviderProtocolInvoker(
        {"default-model": provider},
        model_families={"default-model": "family-a"},
    )
    decoder_runs = []

    def decoder(sid, run):
        decoder_runs.append((sid, run.seeded_agents))
        rule = "union" if sid in {StrategyId.S2, StrategyId.S12} else "authority"
        return DecodedStrategyResult(
            DecisionResult(decomposition, rule, "selected", "test adjudication")
        )

    def prompt_views(sid, prompt, extraction, agent_ids):
        if sid is not StrategyId.S12:
            raise AssertionError("Prompt partition factory should only be called for S12")
        return {
            **{agent: f"explicit facet view for {agent}" for agent in agent_ids if agent != "integrator"},
            "integrator": prompt.text,
        }

    adapter = ConcreteStrategyAdapter(
        invoker, decoder, prompt_view_factory=prompt_views, n=2, k=2,
    )
    executor = SequentialCompositionExecutor(adapter)
    available = 8 if item is PlanItem.C8_BRAINSTORM_THEN_REVIEW else 7
    result = executor(
        item, _prompt(), _extraction(),
        (decomposition, decomposition), None, available,
    )

    assert result.calls_made == expected_calls
    assert len(provider.calls) == expected_calls
    assert len(invoker.traces) == expected_calls
    assert [entry[0] for entry in decoder_runs] == [
        StrategyId(expected_first.value), StrategyId(expected_second.value)
    ]
    assert decoder_runs[1][1] == ("author",)
    assert result.strategy_run_id.startswith(item.value + ":")
    assert all(trace.model_family == "family-a" for trace in invoker.traces)
    if item is PlanItem.COMBO_JIGSAW_THEN_CRITIC:
        expert_payloads = [
            json.loads(messages[1].content)
            for messages in provider.calls[:2]
        ]
        assert all(payload["prompt_view"].startswith("explicit facet view") for payload in expert_payloads)
