import pytest

from sociodec.extraction import ExtractionResult, aggregate_extractions
from sociodec.models.decomposition import (
    Decomposition, DeliverableComposition, Subproblem,
)
from sociodec.models.prompt import (
    Interpretation, Prompt, Requirement, RequirementType, SourceSpan,
)
from sociodec.orchestrator import StrategyOutcome, run_adaptive
from sociodec.selector import PlanItem


def fixture(*, covered=True):
    text = "Create a plan now."
    requirement = Requirement(
        "Create a plan now", RequirementType.TARGET, "planning",
        SourceSpan(0, len(text)),
    )
    prompt = Prompt(text, Interpretation("Create a plan", deliverables=("Plan",)))
    subproblem = Subproblem(
        "s1", "Prepare the plan", (), "Plan output", (),
        (requirement,) if covered else (),
    )
    decomposition = Decomposition(
        (subproblem,), (),
        (DeliverableComposition("Plan", ("s1",)),),
    )
    extraction = aggregate_extractions((
        ExtractionResult(requirements=(requirement,), extractor_id="extractor-1"),
    ))
    return prompt, extraction, requirement, decomposition


def test_rule_zero_returns_checked_initial_union_without_strategy_calls():
    prompt, extraction, _, d = fixture()
    calls = []

    def draft(prompt, extracted, author_index):
        calls.append(author_index)
        return d

    def execute(*args):
        pytest.fail("Rule 0 must not execute a social strategy")

    result = run_adaptive(
        prompt, extract=lambda _: extraction, draft=draft,
        execute_strategy=execute, budget=10, high_stakes=False,
        model_families=1,
    )
    assert calls == [0, 1]
    assert result.best == result.initial_union
    assert result.strategy_records == ()
    assert result.calls_made == 3
    assert result.best_failures == ()
    assert [e.kind for e in result.events] == [
        "extraction", "initial_draft", "initial_draft", "diagnosis", "initial_union",
    ]


def test_open_prompt_runs_c8_with_both_initial_seeds_and_trace():
    prompt, extraction, _, d = fixture()
    observed = []

    def execute(item, prompt, extracted, initial_drafts, chain_seed, available_calls):
        observed.append((item, initial_drafts, chain_seed, available_calls))
        return StrategyOutcome(d, calls_made=10, strategy_run_id="run-c8")

    result = run_adaptive(
        prompt, extract=lambda _: extraction,
        draft=lambda p, e, i: d, execute_strategy=execute,
        budget=30, high_stakes=False, model_families=1, open_prompt=True,
    )
    assert len(observed) == 1
    item, seeds, chain_seed, available = observed[0]
    assert item is PlanItem.C8_BRAINSTORM_THEN_REVIEW
    assert seeds == (d, d)
    assert chain_seed is None
    assert available == 27
    assert result.strategy_records[0].seed_supplied is False
    assert result.strategy_records[0].outcome.strategy_run_id == "run-c8"
    assert result.calls_made == 13
    assert result.best_failures == ()


def test_initial_union_failure_triggers_algorithm2_escalation_c2():
    prompt, extraction, _, bad = fixture(covered=False)
    _, _, _, good = fixture(covered=True)
    observed = []

    def execute(item, prompt, extracted, initial_drafts, chain_seed, available_calls):
        observed.append((item, initial_drafts, chain_seed))
        return StrategyOutcome(good, calls_made=8, strategy_run_id="c2")

    result = run_adaptive(
        prompt, extract=lambda _: extraction,
        draft=lambda p, e, i: bad, execute_strategy=execute,
        budget=20, high_stakes=False, model_families=1,
    )
    assert observed[0][0] is PlanItem.COMBO_JIGSAW_THEN_CRITIC
    assert observed[0][1] == (bad, bad)
    assert observed[0][2] is None
    assert result.best == good
    assert result.best_failures == ()
    assert result.calls_made == 11
    assert any(e.kind == "escalation" for e in result.events)


def test_budget_reports_strategy_not_run_when_chain_cannot_fit():
    prompt, extraction, _, d = fixture()
    called = []

    def execute(*args):
        called.append(args)
        return StrategyOutcome(d, calls_made=10)

    result = run_adaptive(
        prompt, extract=lambda _: extraction,
        draft=lambda p, e, i: d, execute_strategy=execute,
        budget=13, high_stakes=False, model_families=1, open_prompt=True,
    )
    assert called == []
    assert result.strategies_not_run == (PlanItem.C8_BRAINSTORM_THEN_REVIEW,)
    assert result.calls_made == 3


def test_strategy_adapter_receives_remaining_budget_and_cannot_exceed_it():
    prompt, extraction, _, d = fixture()

    def execute(item, prompt, extracted, initial_drafts, chain_seed, available_calls):
        assert available_calls == 10
        return StrategyOutcome(d, calls_made=12)

    with pytest.raises(RuntimeError, match="exceeded the remaining call budget reserved before repair"):
        run_adaptive(
            prompt, extract=lambda _: extraction,
            draft=lambda p, e, i: d, execute_strategy=execute,
            budget=14, high_stakes=False, model_families=1, open_prompt=True,
        )


def test_invalid_extractor_result_and_insufficient_initial_budget_fail_closed():
    prompt, extraction, _, d = fixture()
    with pytest.raises(TypeError, match="AggregatedExtraction"):
        run_adaptive(
            prompt, extract=lambda _: object(), draft=lambda p, e, i: d,
            execute_strategy=lambda *args: StrategyOutcome(d, 0),
            budget=10, high_stakes=False, model_families=1,
        )
    with pytest.raises(ValueError, match="two mandatory initial drafts"):
        run_adaptive(
            prompt, extract=lambda _: extraction, draft=lambda p, e, i: d,
            execute_strategy=lambda *args: StrategyOutcome(d, 0),
            budget=2, high_stakes=False, model_families=1,
        )


def test_strategy_result_is_not_selected_when_it_has_more_failures():
    prompt, extraction, _, good = fixture()
    _, _, _, bad = fixture(covered=False)

    def execute(item, prompt, extracted, initial_drafts, chain_seed, available_calls):
        return StrategyOutcome(bad, calls_made=10)

    result = run_adaptive(
        prompt, extract=lambda _: extraction,
        draft=lambda p, e, i: good, execute_strategy=execute,
        budget=30, high_stakes=False, model_families=1, open_prompt=True,
    )
    assert result.best == result.initial_union
    assert result.best_failures == ()
    assert result.strategy_records[0].validation.v1_coverage.status.value == "fail"


def test_strategy_chain_passes_previous_decomposition_as_next_seed():
    prompt, extraction, requirement, d = fixture()
    # Conflict activates stage 3 mediation; open activates C8, producing
    # a multi-stage chain only when separate stage rules match.
    from sociodec.extraction import ConflictPair, ExtractionResult, aggregate_extractions
    conflict_extraction = aggregate_extractions((
        ExtractionResult(
            requirements=(requirement,), conflicts=(ConflictPair("A", "B"),),
            extractor_id="extractor-1",
        ),
    ))
    observed = []

    def execute(item, prompt, extracted, initial_drafts, chain_seed, available_calls):
        observed.append((item, chain_seed))
        return StrategyOutcome(d, calls_made=5)

    result = run_adaptive(
        prompt, extract=lambda _: conflict_extraction,
        draft=lambda p, e, i: d, execute_strategy=execute,
        budget=100, high_stakes=False, model_families=1, open_prompt=True,
    )
    assert [x[0] for x in observed] == [
        PlanItem.C8_BRAINSTORM_THEN_REVIEW, PlanItem.S11,
    ]
    assert observed[0][1] is None
    assert observed[1][1] == d
    assert result.strategy_records[1].seed_supplied is True


def test_c1_full_pipeline_uses_composed_phase_cost_not_sum_of_full_strategies():
    from sociodec.orchestrator import _item_cost
    assert _item_cost(PlanItem.COMBO_FULL_PIPELINE, n=3, k=3, T=2) == 9
