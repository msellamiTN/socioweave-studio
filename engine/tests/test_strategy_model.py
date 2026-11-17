import pytest

from sociodec.models.strategy import (
    Action, Agent, DecisionRule, ProtocolStep, Role, RoleAssignment,
    SocialStrategy, VisibilityRound,
)


def make_strategy(*, rounds=2, homogeneous=True, independent=True, stable=True):
    agents = (
        Agent("a1", "model-A", "Full prompt"),
        Agent("a2", "model-A" if homogeneous else "model-B", "Full prompt"),
    )
    roles = (Role.DECOMPOSER, Role.CRITIC, Role.JUDGE)
    assignments = []
    for round_number in range(1, rounds + 1):
        assignments.append(RoleAssignment("a1", round_number, Role.DECOMPOSER))
        assignments.append(RoleAssignment(
            "a2", round_number,
            Role.CRITIC if stable or round_number == 1 else Role.JUDGE,
        ))
    visibility = []
    for round_number in range(1, rounds + 1):
        pairs = [("a1", "a1"), ("a2", "a2")]
        if not independent or round_number > 1:
            pairs.append(("a1", "a2"))
        visibility.append(VisibilityRound(round_number, tuple(pairs)))
    protocol = (
        ProtocolStep("a1", Action.DRAFT, "prompt", 1, 1),
        ProtocolStep("a2", Action.DRAFT, "prompt", 1, 1),
        ProtocolStep("a1", Action.CRITIQUE, "drafts", min(2, rounds), 2),
        ProtocolStep("a2", Action.JUDGE, "candidates", min(2, rounds), 3, False),
    )
    return SocialStrategy(
        agents, roles, tuple(assignments), tuple(visibility), protocol,
        DecisionRule.AUTHORITY, rounds, anonymous=True,
    )


def test_strategy_models_definition_9_and_10():
    strategy = make_strategy()
    assert strategy.calls == 3
    assert strategy.depth == 3
    assert strategy.homogeneous is True
    assert strategy.independent_first_round is True
    assert strategy.role_stable is True
    assert strategy.anonymous is True


def test_heterogeneous_agents_and_role_rotation_are_detected():
    strategy = make_strategy(homogeneous=False, stable=False)
    assert strategy.homogeneous is False
    assert strategy.role_stable is False


def test_shared_first_round_visibility_breaks_independence():
    strategy = make_strategy(independent=False)
    assert strategy.independent_first_round is False


def test_agent_requires_model_context_and_identifier():
    with pytest.raises(ValueError, match="identifier"):
        Agent(" ", "m", "context")
    with pytest.raises(ValueError, match="model_id"):
        Agent("a", " ", "context")
    with pytest.raises(ValueError, match="context"):
        Agent("a", "m", " ")


def test_role_assignment_rejects_invalid_round_and_role():
    with pytest.raises(ValueError, match="round"):
        RoleAssignment("a", 0, Role.CRITIC)
    with pytest.raises(ValueError, match="defined Role"):
        RoleAssignment("a", 1, "critic")


def test_visibility_round_rejects_duplicate_and_blank_pairs():
    with pytest.raises(ValueError, match="unique"):
        VisibilityRound(1, (("a", "a"), ("a", "a")))
    with pytest.raises(ValueError, match="non-empty"):
        VisibilityRound(1, (("a", " "),))


def test_protocol_step_rejects_invalid_action_stage_and_round():
    with pytest.raises(ValueError, match="defined Action"):
        ProtocolStep("a", "draft", "prompt", 1, 1)
    with pytest.raises(ValueError, match="stage"):
        ProtocolStep("a", Action.DRAFT, "prompt", 1, 0)


def test_strategy_requires_total_role_assignment_alpha():
    strategy = make_strategy()
    with pytest.raises(ValueError, match="cover every agent"):
        SocialStrategy(
            strategy.agents, strategy.roles, strategy.assignments[:-1],
            strategy.visibility, strategy.protocol, strategy.decision_rule,
            strategy.rounds, strategy.anonymous,
        )


def test_strategy_rejects_unknown_agent_in_visibility_and_protocol():
    strategy = make_strategy()
    bad_visibility = (
        VisibilityRound(1, (("a1", "a1"), ("a2", "a2"), ("ghost", "a1"))),
        strategy.visibility[1],
    )
    with pytest.raises(ValueError, match="unknown agent"):
        SocialStrategy(
            strategy.agents, strategy.roles, strategy.assignments,
            bad_visibility, strategy.protocol, strategy.decision_rule,
            strategy.rounds,
        )

    bad_protocol = (
        ProtocolStep("ghost", Action.DRAFT, "prompt", 1, 1),
    )
    with pytest.raises(ValueError, match="unknown agent"):
        SocialStrategy(
            strategy.agents, strategy.roles, strategy.assignments,
            strategy.visibility, bad_protocol, strategy.decision_rule,
            strategy.rounds,
        )


def test_strategy_requires_self_visibility_and_all_rounds():
    strategy = make_strategy()
    bad = (VisibilityRound(1, (("a1", "a1"),)), strategy.visibility[1])
    with pytest.raises(ValueError, match="own outputs"):
        SocialStrategy(
            strategy.agents, strategy.roles, strategy.assignments,
            bad, strategy.protocol, strategy.decision_rule, strategy.rounds,
        )
    with pytest.raises(ValueError, match="exactly one relation"):
        SocialStrategy(
            strategy.agents, strategy.roles, strategy.assignments,
            strategy.visibility[:1], strategy.protocol,
            strategy.decision_rule, strategy.rounds,
        )


def test_strategy_requires_contiguous_protocol_stages():
    strategy = make_strategy()
    bad = (
        ProtocolStep("a1", Action.DRAFT, "prompt", 1, 1),
        ProtocolStep("a2", Action.JUDGE, "draft", 2, 3),
    )
    with pytest.raises(ValueError, match="contiguous"):
        SocialStrategy(
            strategy.agents, strategy.roles, strategy.assignments,
            strategy.visibility, bad, strategy.decision_rule, strategy.rounds,
        )


def test_strategy_calls_and_depth_are_distinct():
    strategy = make_strategy()
    assert strategy.calls == 3  # one deterministic protocol step
    assert strategy.depth == 3  # parallel drafts share stage 1
