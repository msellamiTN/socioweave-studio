import pytest

from sociodec.catalogue import STRATEGIES, StrategyId, get_strategy
from sociodec.models.strategy import Action, DecisionRule, Role
from sociodec.strategy_protocols import build_strategy_blueprint


@pytest.mark.parametrize("definition", STRATEGIES, ids=lambda item: item.identifier.value)
def test_every_established_strategy_builds_a_valid_social_strategy(definition):
    blueprint = build_strategy_blueprint(
        definition.identifier, n=3, k=3, T=2,
        prompt_views=(
            {"coordinator": "full", **{f"specialist-{i}": f"domain-{i}" for i in range(1, 4)}}
            if definition.identifier is StrategyId.S1 else
            {**{f"expert-{i}": f"facet-{i}" for i in range(1, 4)}, "integrator": "full"}
            if definition.identifier is StrategyId.S12 else None
        ),
    )
    strategy = blueprint.strategy
    expected_calls = 2 + 3 * 2 if definition.identifier is StrategyId.S11 else get_strategy(definition.identifier).calls(n=3, k=3, T=2)
    expected_depth = 1 + 2 * 2 if definition.identifier is StrategyId.S11 else get_strategy(definition.identifier).depth(n=3, k=3, T=2)
    assert strategy.calls == expected_calls
    assert strategy.depth == expected_depth
    assert strategy.decision_rule.value == definition.decision_rule
    assert len(strategy.assignments) == len(strategy.agents) * strategy.rounds
    assert all(
        (agent.identifier, agent.identifier) in visibility.visible_pairs
        for visibility in strategy.visibility for agent in strategy.agents
    )


def test_division_of_labour_requires_and_preserves_domain_restricted_views():
    views = {
        "coordinator": "full prompt",
        "specialist-1": "legal domain only",
        "specialist-2": "technical domain only",
        "specialist-3": "organisational domain only",
    }
    blueprint = build_strategy_blueprint("S1", prompt_views=views)
    assert blueprint.prompt_views == views
    specialists = [step for step in blueprint.strategy.protocol if step.action is Action.DRAFT]
    assert [step.input_ref for step in specialists] == ["partition:step:0"] * 3
    assert [step.round for step in specialists] == [2, 2, 2]
    pairs = set(blueprint.strategy.visibility[1].visible_pairs)
    assert all((f"specialist-{i}", "coordinator") in pairs for i in range(1, 4))
    assert ("specialist-1", "specialist-2") not in pairs
    assert ("specialist-2", "specialist-3") not in pairs


def test_jigsaw_integrator_can_see_all_expert_outputs_but_experts_are_isolated():
    blueprint = build_strategy_blueprint(
        "S12",
        prompt_views={"expert-1": "goals", "expert-2": "constraints",
                      "expert-3": "actors", "integrator": "full"},
    )
    pairs = set(blueprint.strategy.visibility[1].visible_pairs)
    assert ("integrator", "expert-1") in pairs
    assert ("integrator", "expert-2") in pairs
    assert ("expert-1", "expert-2") not in pairs


def test_brainstorming_aggregator_sees_generated_lists_only_after_generation():
    blueprint = build_strategy_blueprint("S2")
    pairs = set(blueprint.strategy.visibility[1].visible_pairs)
    assert ("aggregator", "participant-1") in pairs
    assert ("participant-1", "participant-2") not in pairs
    assert blueprint.strategy.protocol[-1].input_ref == "all_previous_outputs"


def test_nominal_group_drafts_are_independent_then_visible_for_ranking():
    blueprint = build_strategy_blueprint("S3")
    assert blueprint.strategy.independent_first_round
    assert all(step.action is Action.RANK for step in blueprint.strategy.protocol[3:])
    assert all(step.input_ref == "all_previous_outputs" for step in blueprint.strategy.protocol[3:])


def test_delphi_is_anonymous_and_facilitator_is_the_only_cross_draft_observer():
    blueprint = build_strategy_blueprint("S4", n=3, T=2)
    assert blueprint.strategy.anonymous
    pairs = set(blueprint.strategy.visibility[0].visible_pairs)
    assert ("facilitator", "expert-1") in pairs
    assert ("expert-1", "expert-2") not in pairs
    assert blueprint.strategy.calls == 8
    assert blueprint.strategy.depth == 4


def test_majority_voters_can_inspect_pooled_items_after_independent_drafts():
    blueprint = build_strategy_blueprint("S9")
    assert blueprint.strategy.independent_first_round
    assert all(step.action is Action.VOTE for step in blueprint.strategy.protocol[3:])
    assert ("voter-1", "voter-2") in blueprint.strategy.visibility[1].visible_pairs


def test_peer_review_reviewers_are_isolated_and_editor_sees_all_reviews():
    blueprint = build_strategy_blueprint("S8", k=3)
    pairs = set(blueprint.strategy.visibility[1].visible_pairs)
    assert ("reviewer-1", "author") in pairs
    assert ("reviewer-1", "reviewer-2") not in pairs
    assert ("editor", "reviewer-1") in set(blueprint.strategy.visibility[2].visible_pairs)
    assert ("author", "reviewer-1") in set(blueprint.strategy.visibility[3].visible_pairs)
    assert blueprint.strategy.calls == 6


def test_adversarial_judge_sees_both_defences_but_parties_do_not_see_each_other():
    blueprint = build_strategy_blueprint("S7")
    pairs = set(blueprint.strategy.visibility[2].visible_pairs)
    assert ("judge", "party-1") in pairs and ("judge", "party-2") in pairs
    assert ("party-1", "party-2") not in set(blueprint.strategy.visibility[1].visible_pairs)
    assert [step.action for step in blueprint.strategy.protocol] == [
        Action.DRAFT, Action.DRAFT, Action.DEFEND, Action.DEFEND, Action.JUDGE,
    ]


def test_role_reversal_swaps_decomposer_and_critic_roles():
    blueprint = build_strategy_blueprint("S13")
    assignments = {(x.agent_id, x.round): x.role for x in blueprint.strategy.assignments}
    assert assignments[("agent-A", 1)] is Role.DECOMPOSER
    assert assignments[("agent-B", 1)] is Role.CRITIC
    assert assignments[("agent-A", 2)] is Role.CRITIC
    assert assignments[("agent-B", 2)] is Role.DECOMPOSER


def test_consensus_deliberation_is_sequential_and_starts_from_empty_shared_draft():
    blueprint = build_strategy_blueprint("S10", n=3, T=2)
    assert blueprint.strategy.calls == 7
    assert blueprint.strategy.depth == 7
    assert blueprint.strategy.protocol[0].input_ref == "all_previous_outputs"
    assert blueprint.strategy.protocol[-1].action is Action.JUDGE


def test_partitioned_strategies_fail_closed_without_explicit_prompt_views():
    with pytest.raises(ValueError, match="explicit prompt_views"):
        build_strategy_blueprint("S1")
    with pytest.raises(ValueError, match="explicit prompt_views"):
        build_strategy_blueprint("S12")


def test_unknown_or_candidate_strategy_is_not_accepted_as_established():
    with pytest.raises(ValueError):
        build_strategy_blueprint("C1")


def test_dialectical_inquiry_is_explicit_counter_plan_with_directional_visibility():
    blueprint = build_strategy_blueprint("S6")
    protocol = blueprint.strategy.protocol
    assert [step.action for step in protocol] == [
        Action.DRAFT, Action.COUNTER_PLAN, Action.MERGE,
    ]
    assert protocol[0].input_ref == "prompt"
    assert protocol[1].input_ref == "step:0"
    pairs = set(blueprint.strategy.visibility[0].visible_pairs)
    assert ("decomposer-2", "decomposer-1") in pairs
    assert ("decomposer-1", "decomposer-2") not in pairs
    assert ("synthesizer", "decomposer-1") in pairs
    assert blueprint.strategy.calls == 3
    assert blueprint.strategy.depth == 3
