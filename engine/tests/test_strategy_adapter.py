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
    expected_calls = blueprint.strategy.calls - 1 if sid is StrategyId.S8 else blueprint.strategy.calls
    expected_depth = blueprint.strategy.depth - 1 if sid is StrategyId.S8 else blueprint.strategy.depth
    assert run.calls_made == expected_calls
    assert run.depth_executed == expected_depth


@pytest.mark.parametrize("item", [PlanItem.S1, PlanItem.S12])
def test_partitioned_adapter_fails_closed_without_prompt_view_factory(item):
    decomposition = _decomposition()
    adapter = ConcreteStrategyAdapter(
        EchoInvoker(),
        lambda sid, run: DecodedStrategyResult(
            DecisionResult(decomposition, "authority" if sid is StrategyId.S1 else "union", "x", "test")
        ),
    )
    with pytest.raises(ValueError, match="requires an explicit prompt_view_factory"):
        adapter(item, _prompt(), _extraction(), (decomposition, decomposition), None, 50)


@pytest.mark.parametrize("sid,item,integrator,agents,decision_rule", [
    (StrategyId.S1, PlanItem.S1, "coordinator",
     ("specialist-1", "specialist-2", "specialist-3"), "authority"),
    (StrategyId.S12, PlanItem.S12, "integrator",
     ("expert-1", "expert-2", "expert-3"), "union"),
])
def test_partitioned_adapter_passes_only_explicit_views_to_runtime(
    sid, item, integrator, agents, decision_rule,
):
    decomposition = _decomposition()
    invoker = EchoInvoker()
    views = {integrator: _prompt().text, **{
        agent: f"private-partition:{agent}" for agent in agents
    }}
    adapter = ConcreteStrategyAdapter(
        invoker,
        lambda strategy_id, run: DecodedStrategyResult(
            DecisionResult(decomposition, decision_rule, "x", "test")
        ),
        prompt_view_factory=lambda strategy_id, prompt, extraction, agent_ids: views,
    )
    adapter(item, _prompt(), _extraction(), (decomposition, decomposition), None, 50)
    observed = {agent: context.prompt_view for agent, action, context in invoker.calls}
    assert observed[integrator] == _prompt().text
    for agent in agents:
        assert observed[agent] == f"private-partition:{agent}"


def test_partitioned_adapter_rejects_full_prompt_leakage_to_specialist():
    decomposition = _decomposition()
    views = {
        "coordinator": _prompt().text,
        "specialist-1": _prompt().text,
        "specialist-2": "technical",
        "specialist-3": "operations",
    }
    adapter = ConcreteStrategyAdapter(
        EchoInvoker(),
        lambda sid, run: DecodedStrategyResult(
            DecisionResult(decomposition, "authority", "x", "test")
        ),
        prompt_view_factory=lambda *args: views,
    )
    with pytest.raises(ValueError, match="must not receive the full prompt"):
        adapter(PlanItem.S1, _prompt(), _extraction(),
                (decomposition, decomposition), None, 50)


def test_s1_specialists_receive_only_their_domain_view_not_coordinator_split():
    invoker = EchoInvoker()
    views = {"coordinator": "full prompt", "specialist-1": "legal",
             "specialist-2": "technical", "specialist-3": "organisation"}
    blueprint = build_strategy_blueprint("S1", prompt_views=views)
    run_strategy("S1", _prompt(), blueprint.strategy, invoker, prompt_views=views)
    specialist_inputs = [context.prompt_view for agent, action, context in invoker.calls if action == "draft"]
    assert specialist_inputs == ["legal", "technical", "organisation"]


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
