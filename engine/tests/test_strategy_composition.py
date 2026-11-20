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
            self.calls.append((item, drafts, seed, allowance))
            from sociodec.models.decomposition import Decomposition
            decomposition = Decomposition((), (), ())
            verdict = HypothesisVerdict(_extraction().hypotheses[0], HypothesisVerdictValue.CONFIRMED)
            return StrategyOutcome(
                decomposition, 2, hypothesis_verdicts=(verdict,),
                strategy_run_id=item.value,
            )
    adapter = Adapter()
    executor = SequentialCompositionExecutor(adapter)
    result = executor(
        PlanItem.C8_BRAINSTORM_THEN_REVIEW, _prompt(), _extraction(),
        (None, None), None, 10,
    )
    assert adapter.calls[0][0] is PlanItem.S2
    assert adapter.calls[1][0] is PlanItem.S8
    assert adapter.calls[0][1] == ()
    assert adapter.calls[0][2] is None
    assert adapter.calls[1][2] == result.decomposition
    assert [x[3] for x in adapter.calls] == [4, 6]
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


def test_sequential_composition_discards_external_seeds_before_first_phase():
    class Adapter:
        def __init__(self):
            self.calls = []
            self.decompositions = []
        def __call__(self, item, prompt, extraction, drafts, seed, allowance):
            from sociodec.models.decomposition import Decomposition
            decomposition = Decomposition((), (), ())
            self.calls.append((item, drafts, seed))
            self.decompositions.append(decomposition)
            return StrategyOutcome(decomposition, 1, strategy_run_id=item.value)

    adapter = Adapter()
    executor = SequentialCompositionExecutor(adapter)
    external_drafts = (object(), object())
    external_seed = object()
    executor(
        PlanItem.C8_BRAINSTORM_THEN_REVIEW, _prompt(), _extraction(),
        external_drafts, external_seed, 10,
    )
    assert adapter.calls[0] == (PlanItem.S2, (), None)
    assert adapter.calls[1][0] is PlanItem.S8
    assert adapter.calls[1][1] == external_drafts
    assert adapter.calls[1][2] is adapter.decompositions[0]
