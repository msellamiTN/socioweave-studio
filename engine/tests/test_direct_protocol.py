import json

import pytest

from sociodec.catalogue import StrategyId
from sociodec.decisions import decomposition_distance
from sociodec.direct_protocol import DirectProtocolStrategyAdapter
from sociodec.e1_protocol import E1Condition
from sociodec.extraction import ExtractionResult, aggregate_extractions
from sociodec.models.decomposition import Decomposition, DeliverableComposition, Subproblem
from sociodec.models.prompt import Interpretation, Prompt, Requirement, RequirementType, SourceSpan
from sociodec.strategy_decoding import DecisionAdjudication


PROMPT = Prompt(
    "Create a report.",
    Interpretation("Create a report", deliverables=("Report",)),
)
REQUIREMENT = Requirement(
    "Create a report", RequirementType.DELIVERABLE, "report", SourceSpan(0, 16),
)
EXTRACTION = aggregate_extractions((
    ExtractionResult(requirements=(REQUIREMENT,), extractor_id="extractor-1"),
))
NEGOTIATED = Decomposition(
    (Subproblem("s1", "Create a report", (), "Report", (), (REQUIREMENT,)),),
    (), (DeliverableComposition("Report", ("s1",)),),
)


def candidate(question):
    return {
        "candidate": {
            "subproblems": [{
                "id": "s1",
                "question": question,
                "inputs": [],
                "output": "Report",
                "local_constraints": [],
                "covered_requirements": [{
                    "type": "deliverable",
                    "domain": "report",
                    "statement": "Create a report",
                }],
            }],
            "dependencies": [],
            "kappa": {"Report": ["s1"]},
        }
    }


class TracedInvoker:
    def __init__(self, agent_id, response):
        self.agent_id = agent_id
        self.response = response
        self.traces = []
        self.contexts = []

    def invoke(self, agent, step, context):
        self.contexts.append((agent.identifier, step.action.value, context))
        if step.action.value == "split":
            result = json.dumps({"partitions": {
                "specialist-1": "LEGAL",
                "specialist-2": "TECHNICAL",
                "specialist-3": "OPERATIONS",
            }})
        elif step.action.value == "summarise":
            result = json.dumps({
                "summary": "Both parties cover the report; wording differs.",
                "agreements": ["The report deliverable is covered."],
                "disagreements": ["The wording of the task differs."],
            })
        else:
            result = self.response(agent, step, context)
        self.traces.append({"agent_id": agent.identifier, "action": step.action.value})
        return result

    def trace_dicts(self):
        return tuple(self.traces)


def test_direct_s1_executes_coordinator_split_and_routes_only_assigned_partition():
    candidate_json = json.dumps(candidate("Create a report"))
    invokers = {}

    def factory(agent, seed):
        provider = TracedInvoker(
            agent.identifier,
            lambda _agent, _step, _context: candidate_json,
        )
        invokers[agent.identifier] = provider
        return provider

    adapter = DirectProtocolStrategyAdapter(
        extraction=EXTRACTION,
        model_resolver=lambda _condition, ids: {agent_id: "model-A" for agent_id in ids},
        invoker_factory=factory,
        n=3,
    )
    condition = E1Condition(
        "smart-administration", "S1", "homogeneous", 0, ("p-001",), 5,
    )
    result = adapter.run(condition=condition, prompt=PROMPT, seed=11)

    assert result.calls_made == 5
    assert result.metadata["execution_path"] == "direct_protocol"
    assert result.metadata["trace_complete"] is True
    expected = {
        "specialist-1": "LEGAL",
        "specialist-2": "TECHNICAL",
        "specialist-3": "OPERATIONS",
    }
    for agent_id, partition in expected.items():
        _, action, context = next(
            item for item in invokers[agent_id].contexts if item[1] == "draft"
        )
        assert action == "draft"
        assert context.input_content == partition
        assert context.prompt_view == partition
        assert "Create a report." not in context.prompt_view


def test_direct_s11_uses_definition7_distance_for_epsilon_stopping():
    calls = []

    def factory(agent, seed):
        def respond(_agent, step, context):
            calls.append((agent.identifier, step.action.value, context))
            if step.action.value == "draft":
                return json.dumps(candidate("Initial report plan"))
            if step.action.value == "revise":
                question = (
                    "Create a report" if agent.identifier == "party-1"
                    else "Produce a report"
                )
                return json.dumps(candidate(question))
            raise AssertionError(f"Unexpected action: {step.action.value}")
        return TracedInvoker(agent.identifier, respond)

    adapter = DirectProtocolStrategyAdapter(
        extraction=EXTRACTION,
        model_resolver=lambda _condition, ids: {
            agent_id: ("model-A" if agent_id != "party-2" else "model-B")
            for agent_id in ids
        },
        invoker_factory=factory,
        n=2,
        T=2,
    )
    condition = E1Condition(
        "smart-administration", "S11", "heterogeneous", 0, ("p-001",), 8,
    )
    result = adapter.run(condition=condition, prompt=PROMPT, seed=17)

    assert result.calls_made == 5
    assert result.metadata["strategy_depth_executed"] == 3
    assert result.metadata["mediation_epsilon"] == 0.1
    assert result.metadata["mediation_distance_matcher"] == "exact-output-local-constraints-v1"
    assert result.metadata["mediation_converged"] is True
    assert result.metadata["mediation_stop_round"] == 1
    assert result.metadata["mediation_distance"] <= 0.1
    assert result.metadata["decision_selected_candidate"] == "party-1"
    assert result.metadata["strategy_base_calls"] == 5
    assert result.metadata["strategy_max_calls"] == 8
    left = Decomposition(
        (Subproblem("s1", "Create a report", (), "Report", (), (REQUIREMENT,)),),
        (), (DeliverableComposition("Report", ("s1",)),),
    )
    right = Decomposition(
        (Subproblem("s1", "Produce a report", (), "Report", (), (REQUIREMENT,)),),
        (), (DeliverableComposition("Report", ("s1",)),),
    )
    assert decomposition_distance(left, right) == 0.0
    # The response callback records draft/revision candidate comparisons;
    # the traced provider separately records the mediator summary call.
    assert [action for _, action, _ in calls] == [
        "draft", "draft", "revise", "revise",
    ]


def test_direct_s10_applies_definition7_epsilon_and_reindexes_moderator_closure():
    calls = []

    def factory(agent, seed):
        def respond(_agent, step, context):
            calls.append((agent.identifier, step.round, step.action.value))
            if step.action.value == "revise":
                question = (
                    "Initial report plan" if step.round == 1
                    else "Produce a report" if agent.identifier == "participant-2"
                    else "Revised report plan"
                )
                return json.dumps(candidate(question))
            if step.action.value == "judge":
                return json.dumps({
                    "no_objection": True,
                    "rationale": "No participant objection remains.",
                })
            raise AssertionError(f"Unexpected S10 action: {step.action.value}")
        return TracedInvoker(agent.identifier, respond)

    adapter = DirectProtocolStrategyAdapter(
        extraction=EXTRACTION,
        model_resolver=lambda _condition, ids: {agent_id: "model-A" for agent_id in ids},
        invoker_factory=factory,
        n=2,
        T=3,
    )
    condition = E1Condition(
        "smart-administration", "S10", "homogeneous", 0, ("p-001",), 7,
    )
    result = adapter.run(condition=condition, prompt=PROMPT, seed=23)

    assert result.calls_made == 5
    assert result.metadata["strategy_depth_executed"] == 5
    assert result.metadata["consensus_epsilon"] == 0.1
    assert result.metadata["consensus_distance_matcher"] == "exact-output-local-constraints-v1"
    assert [round_number for _, round_number, action in calls if action == "revise"] == [
        1, 1, 2, 2,
    ]
    assert calls[-1] == ("moderator", 2, "judge")


def test_direct_s4_uses_definition7_epsilon_for_delphi_stability():
    calls = []

    def factory(agent, seed):
        def respond(_agent, step, context):
            calls.append((agent.identifier, step.round, step.action.value))
            if step.action.value in {"draft", "revise"}:
                if step.round == 1:
                    question = "Initial report plan"
                else:
                    question = (
                        "Create a report" if agent.identifier == "expert-1"
                        else "Produce a report"
                    )
                return json.dumps(candidate(question))
            raise AssertionError(f"Unexpected S4 action: {step.action.value}")
        return TracedInvoker(agent.identifier, respond)

    adapter = DirectProtocolStrategyAdapter(
        extraction=EXTRACTION,
        model_resolver=lambda _condition, ids: {agent_id: "model-A" for agent_id in ids},
        invoker_factory=factory,
        n=2,
        T=3,
    )
    condition = E1Condition(
        "smart-administration", "S4", "homogeneous", 0, ("p-001",), 8,
    )
    result = adapter.run(condition=condition, prompt=PROMPT, seed=29)

    assert result.calls_made == 6
    assert result.metadata["strategy_depth_executed"] == 4
    assert result.metadata["delphi_epsilon"] == 0.1
    assert result.metadata["delphi_distance_matcher"] == "exact-output-local-constraints-v1"
    assert {round_number for _, round_number, action in calls if action == "revise"} == {2}
    assert [action for _, _, action in calls].count("draft") == 2
    assert [action for _, _, action in calls].count("revise") == 2


def test_heterogeneous_strategy_rejects_judge_sharing_author_family():
    adapter = DirectProtocolStrategyAdapter(
        extraction=EXTRACTION,
        model_resolver=lambda _condition, ids: {
            agent_id: {"author": "model-A", "reviewer-1": "model-B",
                       "reviewer-2": "model-C", "reviewer-3": "model-B",
                       "editor": "model-A"}[agent_id]
            for agent_id in ids
        },
        model_family_resolver=lambda _condition, ids: {
            agent_id: {"author": "MA", "reviewer-1": "MB",
                       "reviewer-2": "MC", "reviewer-3": "MB",
                       "editor": "MA"}[agent_id]
            for agent_id in ids
        },
        invoker_factory=lambda _agent, _seed: (_ for _ in ()).throw(
            AssertionError("provider invocation must not begin after invalid family preflight")
        ),
        n=3,
        k=3,
    )
    condition = E1Condition(
        "smart-administration", "S8", "heterogeneous", 0, ("p-001",), 6,
    )
    with pytest.raises(ValueError, match="judge editor must use a model family distinct"):
        adapter.run(condition=condition, prompt=PROMPT, seed=21)
