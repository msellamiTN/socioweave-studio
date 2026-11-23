import json
import pytest

from sociodec.catalogue import StrategyId
from sociodec.decisions import Candidate, union
from sociodec.extraction import ExtractionResult, aggregate_extractions
from sociodec.models.decomposition import Decomposition, Subproblem
from sociodec.models.prompt import Interpretation, Prompt, RequirementType
from sociodec.orchestrator import StrategyOutcome
from sociodec.runtime import run_strategy
from sociodec.selector import PlanItem
from sociodec.strategy_adapter import (
    ConcreteStrategyAdapter, DecodedStrategyResult,
)
from sociodec.decisions import DecisionResult
from sociodec.strategy_protocols import build_strategy_blueprint


class EchoInvoker:
    def __init__(self):
        self.calls = []

    def invoke(self, agent, step, context):
        self.calls.append((agent.identifier, step.action.value, context))
        if agent.identifier == "editor" and step.action.value == "judge":
            return json.dumps({"verdict": "accept", "rationale": "Echo test accepts draft."})
        if step.action.value == "split":
            return json.dumps({"partitions": {
                "specialist-1": "coordinator:legal",
                "specialist-2": "coordinator:technical",
                "specialist-3": "coordinator:organisation",
            }})
        return f"{step.action.value}:{context.input_content}"


def _prompt():
    return Prompt("Build an accessible service.", Interpretation("Build service"))


def _decomposition():
    return Decomposition((Subproblem("s1", "Build service", (), "Service", (), ()),), (), ())


def _extraction():
    return aggregate_extractions((
        ExtractionResult(extractor_id="e1"),
    ))


@pytest.mark.parametrize("sid", list(StrategyId))
def test_runtime_executes_every_concrete_protocol_with_table4_call_count(sid):
    invoker = EchoInvoker()
    options = {"n": 3, "k": 3, "T": 2}
    views = None
    if sid is StrategyId.S1:
        views = {"coordinator": "full", **{f"specialist-{i}": f"domain-{i}" for i in range(1, 4)}}
    elif sid is StrategyId.S12:
        views = {**{f"expert-{i}": f"facet-{i}" for i in range(1, 4)}, "integrator": "full"}
    blueprint = build_strategy_blueprint(sid, prompt_views=views, **options)
    inputs = {"all_previous_outputs": ""} if sid is StrategyId.S10 else {}
    run = run_strategy(
        sid.value, _prompt(), blueprint.strategy, invoker,
        prompt_views=blueprint.prompt_views, initial_inputs=inputs,
    )
    expected_calls = (5 if sid is StrategyId.S11 else blueprint.strategy.calls - 1 if sid is StrategyId.S8 else blueprint.strategy.calls)
    expected_depth = (3 if sid is StrategyId.S11 else blueprint.strategy.depth - 1 if sid is StrategyId.S8 else blueprint.strategy.depth)
    assert run.calls_made == expected_calls
    assert run.depth_executed == expected_depth


def test_s1_specialists_receive_coordinator_generated_partitions_not_static_views():
    invoker = EchoInvoker()
    views = {"coordinator": "full prompt", "specialist-1": "STATIC_LEAK_1",
             "specialist-2": "STATIC_LEAK_2", "specialist-3": "STATIC_LEAK_3"}
    blueprint = build_strategy_blueprint("S1", prompt_views=views)
    run_strategy("S1", _prompt(), blueprint.strategy, invoker, prompt_views=views)
    specialist_contexts = [context for agent, action, context in invoker.calls if action == "draft"]
    assert [context.prompt_view for context in specialist_contexts] == [
        "coordinator:legal", "coordinator:technical", "coordinator:organisation",
    ]
    assert [context.input_content for context in specialist_contexts] == [
        "coordinator:legal", "coordinator:technical", "coordinator:organisation",
    ]
    assert all("STATIC_LEAK" not in context.prompt_view for context in specialist_contexts)


def test_anonymous_delphi_aggregate_input_does_not_leak_author_ids():
    invoker = EchoInvoker()
    blueprint = build_strategy_blueprint("S4", n=3, T=2)
    run_strategy("S4", _prompt(), blueprint.strategy, invoker, prompt_views=blueprint.prompt_views)
    facilitator_context = next(
        context for agent, action, context in invoker.calls if agent == "facilitator"
    )
    assert "anonymous" in facilitator_context.input_content
    assert "[expert-1:draft]" not in facilitator_context.input_content


def test_visibility_is_enforced_for_direct_step_references():
    blueprint = build_strategy_blueprint("S7")
    protocol = list(blueprint.strategy.protocol)
    # party-1 attempts to read party-2's draft while the strategy's visibility
    # relation intentionally keeps parties' drafts private.
    protocol[2] = type(protocol[2])(
        "party-1", protocol[2].action, "step:1", protocol[2].round,
        protocol[2].stage, protocol[2].invokes_model,
    )
    from sociodec.models.strategy import SocialStrategy
    bad = SocialStrategy(
        blueprint.strategy.agents, blueprint.strategy.roles,
        blueprint.strategy.assignments, blueprint.strategy.visibility,
        tuple(protocol), blueprint.strategy.decision_rule,
        blueprint.strategy.rounds, blueprint.strategy.anonymous,
    )
    with pytest.raises(ValueError, match="not visible"):
        run_strategy("bad-visibility", _prompt(), bad, EchoInvoker())


def test_concrete_adapter_runs_runtime_and_requires_typed_decision_result():
    decomposition = _decomposition()

    def decoder(sid, run):
        assert sid is StrategyId.S2
        candidates = [Candidate("aggregate", decomposition)]
        decision = union(candidates)
        return DecodedStrategyResult(decision)

    adapter = ConcreteStrategyAdapter(EchoInvoker(), decoder, n=3)
    outcome = adapter(
        PlanItem.S2, _prompt(), _extraction(),
        (decomposition, decomposition), None, 10,
    )
    assert isinstance(outcome, StrategyOutcome)
    assert outcome.calls_made == 2
    assert outcome.decomposition.subproblems[0].question == decomposition.subproblems[0].question
    assert outcome.strategy_run_id.startswith("S2:")


def test_concrete_adapter_rejects_wrong_decision_operator():
    decomposition = _decomposition()

    def decoder(sid, run):
        return DecodedStrategyResult(
            DecisionResult(decomposition, "authority", "x", "judge selected x")
        )

    adapter = ConcreteStrategyAdapter(EchoInvoker(), decoder)
    with pytest.raises(ValueError, match="requires decision operator 'union'"):
        adapter(
            PlanItem.S2, _prompt(), _extraction(),
            (decomposition, decomposition), None, 10,
        )


def test_composition_requires_explicit_composition_executor():
    decomposition = _decomposition()
    adapter = ConcreteStrategyAdapter(EchoInvoker(), lambda sid, run: None)
    with pytest.raises(ValueError, match="requires an explicit composition executor"):
        adapter(
            PlanItem.C8_BRAINSTORM_THEN_REVIEW, _prompt(), _extraction(),
            (decomposition, decomposition), None, 20,
        )


@pytest.mark.parametrize("item", [PlanItem.S1, PlanItem.S12])
def test_partitioned_adapter_rejects_missing_prompt_view_factory(item):
    decomposition = _decomposition()
    invoker = EchoInvoker()
    adapter = ConcreteStrategyAdapter(invoker, lambda sid, run: None)
    with pytest.raises(ValueError, match="explicit prompt_view_factory"):
        adapter(item, _prompt(), _extraction(),
                (decomposition, decomposition), None, 20)
    assert invoker.calls == []


@pytest.mark.parametrize("sid,restricted", [
    (StrategyId.S1, ("specialist-1", "specialist-2", "specialist-3")),
    (StrategyId.S12, ("expert-1", "expert-2", "expert-3")),
])
def test_partitioned_adapter_rejects_full_prompt_for_restricted_agents(sid, restricted):
    decomposition = _decomposition()
    prompt = _prompt()

    def views(strategy_id, source_prompt, extraction, agent_ids):
        result = {agent_id: f"restricted:{agent_id}" for agent_id in agent_ids}
        if sid is StrategyId.S1:
            result["coordinator"] = source_prompt.text
        else:
            result["integrator"] = source_prompt.text
        result[restricted[0]] = source_prompt.text
        return result

    adapter = ConcreteStrategyAdapter(
        EchoInvoker(), lambda strategy_id, run: None,
        prompt_view_factory=views,
    )
    item = PlanItem.S1 if sid is StrategyId.S1 else PlanItem.S12
    with pytest.raises(ValueError, match="must not equal the full prompt"):
        adapter(item, prompt, _extraction(),
                (decomposition, decomposition), None, 20)
