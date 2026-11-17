import pytest

from sociodec.selector import (
    PlanItem, PromptFeatures, plan_strategy_chain,
)


def features(**changes):
    values = dict(
        constraint_count=0, domain_count=1, hypothesis_count=0,
        ambiguity=False, conflict=False, open_prompt=False,
        stakeholder_values=False, justified_plan=False,
        content_gap=0.0, structure_gap=0.0, mean_coupling=0.0,
        high_stakes=False, model_families=2,
    )
    values.update(changes)
    return PromptFeatures(**values)


def plan(f, **changes):
    values = dict(initial_distance=0.5, failures=(), budget=200,
                  extraction_calls=3, n=3, k=3, T=2)
    values.update(changes)
    return plan_strategy_chain(f, **values)


def test_rule_zero_returns_checked_union_without_strategy():
    result = plan(features(), initial_distance=0.05)
    assert result.items == ()
    assert result.not_run == ()
    assert result.reason == "checked union (rule 0)"
    assert result.calls_reserved == 5


def test_stage_one_ambiguity_and_stakeholder_values_selects_s10():
    result = plan(features(ambiguity=True, stakeholder_values=True))
    assert result.items[0] is PlanItem.S10
    assert result.rule_ids[0] == "1.1"


def test_stage_one_ambiguity_without_stakeholders_selects_delphi():
    result = plan(features(ambiguity=True))
    assert result.items[0] is PlanItem.S4
    assert result.rule_ids[0] == "1.2"


def test_stage_two_open_prompt_selects_c8_combination():
    result = plan(features(open_prompt=True))
    assert result.items[0] is PlanItem.C8_BRAINSTORM_THEN_REVIEW
    assert result.rule_ids[0] == "2.1"


def test_stage_two_structural_gap_high_stakes_selects_s7():
    result = plan(features(content_gap=0.05, structure_gap=0.4, high_stakes=True))
    assert result.items[0] is PlanItem.S7
    assert result.rule_ids[0] == "2.2"


def test_stage_two_structural_gap_without_high_stakes_selects_s6():
    result = plan(features(content_gap=0.05, structure_gap=0.4))
    assert result.items[0] is PlanItem.S6
    assert result.rule_ids[0] == "2.3"


def test_stage_two_near_agreement_requires_two_families():
    result = plan(features(), initial_distance=0.15)
    assert result.items[0] is PlanItem.S9
    blocked = plan(features(model_families=1), initial_distance=0.15)
    assert PlanItem.S9 not in blocked.items


def test_stage_two_constraint_threshold_is_inclusive():
    assert plan(features(constraint_count=5)).items[0] is PlanItem.S12
    assert plan(features(constraint_count=4)).items == ()


def test_stage_two_hypothesis_selects_jigsaw():
    assert plan(features(hypothesis_count=1)).items[0] is PlanItem.S12


def test_stage_two_domains_and_coupling_select_division_of_labour():
    assert plan(features(domain_count=3, mean_coupling=1.0)).items[0] is PlanItem.S1
    assert plan(features(domain_count=3, mean_coupling=1.01)).items == ()


def test_stage_two_content_gap_requires_two_families():
    assert plan(features(content_gap=0.21)).items[0] is PlanItem.S3
    assert plan(features(content_gap=0.21, model_families=1)).items == ()


def test_stage_three_conflict_precedes_high_stakes():
    result = plan(features(conflict=True, high_stakes=True))
    assert PlanItem.S11 in result.items
    assert result.items[0] is PlanItem.S11
    assert result.items[1] is PlanItem.COMBO_FULL_PIPELINE


def test_stage_three_high_stakes_selects_peer_review():
    result = plan(features(high_stakes=True))
    assert result.items[0] is PlanItem.S8
    assert result.rule_ids[0] == "3.2"


def test_stage_three_justified_plan_requires_two_families():
    assert plan(features(justified_plan=True)).items[0] is PlanItem.S13
    assert plan(features(justified_plan=True, model_families=1)).items == ()


def test_escalation_uncovered_requirement_selects_jigsaw_then_critic():
    result = plan(features(), failures=("uncovered_requirements",))
    assert result.items == (PlanItem.COMBO_JIGSAW_THEN_CRITIC,)
    assert result.reason == "Algorithm 2 escalation"


def test_escalation_cycle_or_composition_failure_selects_peer_review():
    result = plan(features(), failures=("dependency_cycle",))
    assert result.items == (PlanItem.S8,)


def test_escalation_other_failure_selects_full_pipeline():
    result = plan(features(), failures=("some_other_failure",))
    assert result.items == (PlanItem.COMBO_FULL_PIPELINE,)


def test_escalation_high_stakes_after_peer_review_adds_full_pipeline():
    result = plan(features(high_stakes=True), failures=())
    assert result.items == (PlanItem.S8, PlanItem.COMBO_FULL_PIPELINE)


def test_rule_zero_with_failed_union_still_escalates():
    result = plan(features(), initial_distance=0.05, failures=("uncovered_requirements",))
    assert result.items == (PlanItem.COMBO_JIGSAW_THEN_CRITIC,)


def test_budget_truncation_reports_selected_strategy_as_not_run():
    result = plan(features(ambiguity=True), budget=5 + 8 + 0)
    assert result.items == ()
    assert result.not_run == (PlanItem.S4,)
    assert result.calls_reserved == 5


def test_budget_must_cover_extraction_and_two_drafts():
    with pytest.raises(ValueError, match="two mandatory initial drafts"):
        plan(features(), budget=4)


@pytest.mark.parametrize("kwargs", [
    {"content_gap": -0.1}, {"structure_gap": 1.1}, {"mean_coupling": -0.01},
    {"model_families": 0}, {"constraint_count": -1}, {"ambiguity": 1},
])
def test_invalid_feature_values_are_rejected(kwargs):
    with pytest.raises(ValueError):
        features(**kwargs)


def test_threshold_and_distance_boundaries():
    f = features(content_gap=0.1, structure_gap=0.10001)
    assert plan(f, initial_distance=0.11).items[0] is PlanItem.S6
    assert plan(features(content_gap=0.2), initial_distance=0.2).items == ()
