import pytest

from sociodec.models.strategy import (
    Action, Agent, DecisionRule, ProtocolStep, Role, RoleAssignment,
    SocialStrategy, VisibilityRound,
)
from sociodec.strategy_execution import (
    StrategyExecutionError, execute_strategy,
)


def make_strategy(*, second_stage_ref="output:r1:s1:expert-a:draft", anonymous=False):
    agents = (
        Agent("expert-a", "small-model", "independent specialist"),
        Agent("expert-b", "small-model", "independent specialist"),
        Agent("integrator", "small-model", "merge specialist outputs"),
    )
    roles = (Role.DECOMPOSER, Role.AGGREGATOR)
    assignments = (
        RoleAssignment("expert-a", 1, Role.DECOMPOSER),
        RoleAssignment("expert-b", 1, Role.DECOMPOSER),
        RoleAssignment("integrator", 1, Role.AGGREGATOR),
    )
    visibility = (
        VisibilityRound(1, (
            ("expert-a", "expert-a"),
            ("expert-b", "expert-b"),
            ("integrator", "integrator"),
            ("integrator", "expert-a"),
            ("integrator", "expert-b"),
        )),
    )
    protocol = (
        ProtocolStep("expert-a", Action.DRAFT, "prompt", 1, 1),
        ProtocolStep("expert-b", Action.DRAFT, "prompt", 1, 1),
        ProtocolStep("integrator", Action.MERGE, second_stage_ref, 1, 2),
    )
    return SocialStrategy(
        agents, roles, assignments, visibility, protocol,
        DecisionRule.UNION, rounds=1,
    )


def test_parallel_stage_outputs_are_not_visible_to_each_other():
    strategy = make_strategy()
    seen = {}

    def executor(context):
        seen[context.step.agent_id] = dict(context.visible_outputs)
        return f"draft from {context.step.agent_id}"

    result = execute_strategy(strategy, "Build a service", model_executor=executor)
    assert result.model_calls == 3
    assert result.depth == 2
    assert seen["expert-a"] == {}
    assert seen["expert-b"] == {}
    assert set(seen["integrator"]) == {
        "r1:s1:expert-a:draft", "r1:s1:expert-b:draft",
    }
    assert len(result.records) == 3


def test_protocol_cannot_read_output_hidden_by_visibility_relation():
    strategy = make_strategy(second_stage_ref="output:r1:s1:expert-a:draft")
    # Remove integrator's access to expert-a while leaving other relations intact.
    visibility = (
        VisibilityRound(1, (
            ("expert-a", "expert-a"),
            ("expert-b", "expert-b"),
            ("integrator", "integrator"),
            ("integrator", "expert-b"),
        )),
    )
    strategy = SocialStrategy(
        strategy.agents, strategy.roles, strategy.assignments, visibility,
        strategy.protocol, strategy.decision_rule, strategy.rounds,
    )
    with pytest.raises(StrategyExecutionError, match="visibility violation"):
        execute_strategy(strategy, "Build a service", model_executor=lambda _: "ok")


def test_same_stage_outputs_cannot_be_read_even_when_author_is_visible():
    protocol = (
        ProtocolStep("expert-a", Action.DRAFT, "prompt", 1, 1),
        ProtocolStep("expert-b", Action.DRAFT, "output:r1:s1:expert-a:draft", 1, 1),
    )
    strategy = SocialStrategy(
        agents=(
            Agent("expert-a", "small-model", "writer"),
            Agent("expert-b", "small-model", "writer"),
        ),
        roles=(Role.DECOMPOSER,),
        assignments=(
            RoleAssignment("expert-a", 1, Role.DECOMPOSER),
            RoleAssignment("expert-b", 1, Role.DECOMPOSER),
        ),
        visibility=(VisibilityRound(1, (
            ("expert-a", "expert-a"), ("expert-b", "expert-b"),
            ("expert-b", "expert-a"),
        )),),
        protocol=protocol,
        decision_rule=DecisionRule.UNION,
        rounds=1,
    )
    with pytest.raises(StrategyExecutionError, match="unavailable output"):
        execute_strategy(strategy, "Prompt", model_executor=lambda _: "draft")


def test_non_model_step_requires_explicit_local_executor_and_is_not_counted():
    strategy = SocialStrategy(
        agents=(Agent("coordinator", "small-model", "coordinator"),),
        roles=(Role.COORDINATOR,),
        assignments=(RoleAssignment("coordinator", 1, Role.COORDINATOR),),
        visibility=(VisibilityRound(1, (("coordinator", "coordinator"),)),),
        protocol=(
            ProtocolStep("coordinator", Action.CHECK, "prompt", 1, 1, invokes_model=False),
        ),
        decision_rule=DecisionRule.AUTHORITY,
        rounds=1,
    )
    with pytest.raises(StrategyExecutionError, match="local_executor"):
        execute_strategy(strategy, "Prompt", model_executor=lambda _: "model output")
    result = execute_strategy(
        strategy, "Prompt", model_executor=lambda _: "model output",
        local_executor=lambda _: "local check passed",
    )
    assert result.model_calls == 0
    assert result.records[0].output_text == "local check passed"


def test_empty_output_is_rejected():
    strategy = make_strategy()
    with pytest.raises(StrategyExecutionError, match="non-empty"):
        execute_strategy(strategy, "Prompt", model_executor=lambda _: " ")



def test_anonymous_strategy_hides_agent_and_output_identities_from_executor():
    strategy = make_strategy(anonymous=True)
    contexts = []

    def executor(context):
        contexts.append(context)
        return f"output-{len(contexts)}"

    result = execute_strategy(strategy, "Build a service", model_executor=executor)
    integrator_context = contexts[-1]

    assert integrator_context.step.agent_id == "agent-3"
    assert integrator_context.step.input_ref == "output:r1:s1:o1"
    assert set(integrator_context.visible_outputs) == {
        "r1:s1:o1", "r1:s1:o2",
    }
    assert integrator_context.visible_author_ids == frozenset({
        "agent-1", "agent-2", "agent-3",
    })
    for context in contexts:
        assert "expert-a" not in repr(context)
        assert "expert-b" not in repr(context)
        assert "integrator" not in repr(context)

    # The audit trace retains real identities, but they were not exposed above.
    assert result.records[-1].agent_id == "integrator"
    assert result.records[0].output_id == "r1:s1:expert-a:draft"
