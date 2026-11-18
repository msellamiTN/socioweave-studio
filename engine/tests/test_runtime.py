import json
import pytest

from sociodec.extraction import Hypothesis
from sociodec.models.prompt import Interpretation, Prompt, RequirementType
from sociodec.models.strategy import (
    Action, Agent, DecisionRule, ProtocolStep, Role, RoleAssignment,
    SocialStrategy, VisibilityRound,
)
from sociodec.runtime import run_strategy
from sociodec.strategy_protocols import build_strategy_blueprint


class RecordingInvoker:
    def __init__(self):
        self.calls = []

    def invoke(self, agent, step, context):
        self.calls.append((agent.identifier, step.action, context))
        return f"{agent.identifier}:{step.action.value}:{len(context.visible_history)}"


def strategy(*, anonymous=False, peer_visible=False):
    agents = (
        Agent("a1", "model-A", "Full prompt"),
        Agent("a2", "model-B", "Full prompt"),
    )
    roles = (Role.DECOMPOSER, Role.CRITIC)
    assignments = (
        RoleAssignment("a1", 1, Role.DECOMPOSER),
        RoleAssignment("a2", 1, Role.CRITIC),
        RoleAssignment("a1", 2, Role.DECOMPOSER),
        RoleAssignment("a2", 2, Role.CRITIC),
    )
    first = [("a1", "a1"), ("a2", "a2")]
    if peer_visible:
        first.extend([("a1", "a2"), ("a2", "a1")])
    visibility = (
        VisibilityRound(1, tuple(first)),
        VisibilityRound(2, (("a1", "a1"), ("a2", "a2"), ("a1", "a2"), ("a2", "a1"))),
    )
    protocol = (
        ProtocolStep("a1", Action.DRAFT, "prompt", 1, 1),
        ProtocolStep("a2", Action.DRAFT, "prompt", 1, 1),
        ProtocolStep("a1", Action.CRITIQUE, "step:1", 2, 2),
        ProtocolStep("a2", Action.JUDGE, "step:0", 2, 2),
    )
    return SocialStrategy(
        agents, roles, assignments, visibility, protocol,
        DecisionRule.AUTHORITY, 2, anonymous,
    )


def prompt():
    return Prompt("Improve the permit service.", Interpretation("Improve service"))


class S8VerdictInvoker:
    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = []
    def invoke(self, agent, step, context):
        self.calls.append((step.action.value, context))
        if step.action.value == "judge":
            return json.dumps({"verdict": self.verdict, "rationale": "Test verdict."})
        return "stub:" + step.action.value

@pytest.mark.parametrize("verdict,expected_calls,expected_depth,expected_steps", [
    ("accept", 3, 3, (0, 1, 2)),
    ("revise", 4, 4, (0, 1, 2, 3)),
])
def test_s8_conditional_revision_branch_counts_and_stable_step_indexes(verdict, expected_calls, expected_depth, expected_steps):
    blueprint = build_strategy_blueprint("S8", k=1)
    invoker = S8VerdictInvoker(verdict)
    run = run_strategy("S8", prompt(), blueprint.strategy, invoker, prompt_views=blueprint.prompt_views)
    assert run.calls_made == expected_calls
    assert run.depth_executed == expected_depth
    assert tuple(output.step_index for output in run.outputs) == expected_steps
    assert 3 not in run.output_refs if verdict == "accept" else 3 in [o.step_index for o in run.outputs]
    assert sum(1 for action, _ in invoker.calls if action == "revise") == (1 if verdict == "revise" else 0)

@pytest.mark.parametrize("bad_json", ["{invalid", "{}", "not-json"])
def test_s8_runtime_fails_closed_for_invalid_editor_verdict(bad_json):
    blueprint = build_strategy_blueprint("S8", k=1)
    class InvalidVerdictInvoker:
        def invoke(self, agent, step, context):
            if step.action.value == "judge":
                return bad_json
            return "stub"
    with pytest.raises(ValueError, match="S8 editor verdict"):
        run_strategy("S8", prompt(), blueprint.strategy, InvalidVerdictInvoker(), prompt_views=blueprint.prompt_views)
def test_runtime_executes_protocol_and_counts_calls_and_depth():
    invoker = RecordingInvoker()
    result = run_strategy("test", prompt(), strategy(), invoker)
    assert len(result.outputs) == 4
    assert result.calls_made == 4
    assert result.depth_executed == 2
    assert result.output_refs["step:0"].startswith("a1:draft")


def test_runtime_enforces_first_round_visibility_and_stage_snapshot():
    invoker = RecordingInvoker()
    run_strategy("test", prompt(), strategy(peer_visible=False), invoker)
    first_context_a1 = invoker.calls[0][2]
    first_context_a2 = invoker.calls[1][2]
    assert first_context_a1.visible_history == ()
    assert first_context_a2.visible_history == ()

    second_round_context_a1 = invoker.calls[2][2]
    assert [item.author for item in second_round_context_a1.visible_history] == ["a1", "a2"]


def test_runtime_anonymises_visible_author_labels():
    invoker = RecordingInvoker()
    run_strategy("anon", prompt(), strategy(anonymous=True), invoker)
    context = invoker.calls[2][2]
    assert {item.author for item in context.visible_history} == {"anonymous"}


def test_seed_is_adopted_without_model_call_and_only_once_per_agent():
    invoker = RecordingInvoker()
    result = run_strategy(
        "seeded", prompt(), strategy(), invoker,
        seeds={"a1": "seeded draft"},
    )
    first = result.outputs[0]
    assert first.text == "seeded draft"
    assert first.from_seed is True
    assert first.model_invoked is False
    assert result.calls_made == 3
    assert result.seeded_agents == ("a1",)


def test_seed_is_not_used_for_non_draft_or_later_round():
    invoker = RecordingInvoker()
    strat = strategy()
    protocol = (
        ProtocolStep("a1", Action.CRITIQUE, "prompt", 1, 1),
        *strat.protocol[1:],
    )
    strat = SocialStrategy(
        strat.agents, strat.roles, strat.assignments, strat.visibility,
        protocol, strat.decision_rule, strat.rounds,
    )
    result = run_strategy("not-seedable", prompt(), strat, invoker, seeds={"a1": "seed"})
    assert result.seeded_agents == ()
    assert result.calls_made == 4


def test_non_model_step_uses_precomputed_output_without_invoker_call():
    strat = strategy()
    protocol = (
        strat.protocol[0],
        ProtocolStep("a2", Action.JUDGE, "prompt", 1, 1, False),
        *strat.protocol[2:],
    )
    strat = SocialStrategy(
        strat.agents, strat.roles, strat.assignments, strat.visibility,
        protocol, strat.decision_rule, strat.rounds,
    )
    invoker = RecordingInvoker()
    result = run_strategy(
        "precomputed", prompt(), strat, invoker,
        precomputed_outputs={"step:1": "fixed judgement"},
    )
    assert result.outputs[1].text == "fixed judgement"
    assert result.calls_made == 3


def test_runtime_rejects_unknown_seed_prompt_view_and_input_reference():
    invoker = RecordingInvoker()
    with pytest.raises(ValueError, match="unknown agent"):
        run_strategy("x", prompt(), strategy(), invoker, seeds={"ghost": "seed"})
    with pytest.raises(ValueError, match="Prompt view"):
        run_strategy("x", prompt(), strategy(), invoker, prompt_views={"ghost": "view"})

    strat = strategy()
    bad_protocol = (
        ProtocolStep("a1", Action.DRAFT, "missing-input", 1, 1),
        *strat.protocol[1:],
    )
    bad = SocialStrategy(
        strat.agents, strat.roles, strat.assignments, strat.visibility,
        bad_protocol, strat.decision_rule, strat.rounds,
    )
    with pytest.raises(ValueError, match="Unknown protocol input"):
        run_strategy("x", prompt(), bad, invoker)


def test_runtime_rejects_same_stage_peer_output_reference():
    strat = strategy()
    bad_protocol = (
        ProtocolStep("a1", Action.DRAFT, "prompt", 1, 1),
        ProtocolStep("a2", Action.DRAFT, "step:0", 1, 1),
        *strat.protocol[2:],
    )
    bad = SocialStrategy(
        strat.agents, strat.roles, strat.assignments, strat.visibility,
        bad_protocol, strat.decision_rule, strat.rounds,
    )
    with pytest.raises(ValueError, match="not available before stage"):
        run_strategy("x", prompt(), bad, RecordingInvoker())


def test_runtime_passes_hypotheses_to_invoker_context():
    invoker = RecordingInvoker()
    h = Hypothesis("Keep the service accessible", RequirementType.TARGET, "service")
    run_strategy("hyp", prompt(), strategy(), invoker, hypotheses=(h,))
    assert invoker.calls[0][2].hypotheses == (h,)


def test_runtime_rejects_empty_invoker_or_precomputed_output():
    class EmptyInvoker:
        def invoke(self, agent, step, context):
            return " "

    with pytest.raises(ValueError, match="non-empty text"):
        run_strategy("empty", prompt(), strategy(), EmptyInvoker())

    strat = strategy()
    protocol = (
        strat.protocol[0],
        ProtocolStep("a2", Action.JUDGE, "prompt", 1, 1, False),
        *strat.protocol[2:],
    )
    strat = SocialStrategy(
        strat.agents, strat.roles, strat.assignments, strat.visibility,
        protocol, strat.decision_rule, strat.rounds,
    )
    with pytest.raises(ValueError, match="requires precomputed output"):
        run_strategy("missing-precomputed", prompt(), strat, RecordingInvoker())



def test_s8_reviewers_are_independent_and_table4_profile_is_preserved():
    blueprint = build_strategy_blueprint("S8", k=3)
    assert blueprint.strategy.calls == 6  # k + 3 worst-case
    assert blueprint.strategy.depth == 4
    invoker = S8VerdictInvoker("revise")
    run = run_strategy("S8", prompt(), blueprint.strategy, invoker,
                       prompt_views=blueprint.prompt_views)
    reviewer_contexts = [context for action, context in invoker.calls if action == "critique"]
    assert len(reviewer_contexts) == 3
    for context in reviewer_contexts:
        assert context.input_content == "stub:draft"
        assert "reviewer-" not in context.input_content
        assert all(item.author == "author" for item in context.visible_history)


@pytest.mark.parametrize("reviewer_count", [1, 3, 5])
def test_s8_runtime_routes_all_reviews_to_editor_and_editor_verdict_to_author(reviewer_count):
    class EvidenceInvoker:
        def __init__(self):
            self.calls = []

        def invoke(self, agent, step, context):
            self.calls.append((agent.identifier, step.action.value, context))
            if step.action.value == "draft":
                return "AUTHOR_DRAFT"
            if step.action.value == "critique":
                return f"REVIEW_FROM_{agent.identifier}"
            if step.action.value == "judge":
                return json.dumps({"verdict": "revise", "rationale": "Revise using all reviews."})
            if step.action.value == "revise":
                return "AUTHOR_REVISION"
            raise AssertionError(f"Unexpected S8 action: {step.action.value}")

    blueprint = build_strategy_blueprint("S8", k=reviewer_count)
    invoker = EvidenceInvoker()
    result = run_strategy(
        "S8", prompt(), blueprint.strategy, invoker,
        prompt_views=blueprint.prompt_views,
    )

    reviews = {f"REVIEW_FROM_reviewer-{i}" for i in range(1, reviewer_count + 1)}
    by_action = {
        (agent, action): context
        for agent, action, context in invoker.calls
    }
    editor_context = by_action[("editor", "judge")]
    revision_context = by_action[("author", "revise")]

    # Every reviewer receives D0, but no other reviewer's critique.
    for i in range(1, reviewer_count + 1):
        reviewer_context = by_action[(f"reviewer-{i}", "critique")]
        assert reviewer_context.input_content == "AUTHOR_DRAFT"
        assert all(
            item.author == "author" and item.action == "draft"
            for item in reviewer_context.visible_history
        )

    # The editor receives D0 and the complete set of independent critiques.
    assert "AUTHOR_DRAFT" in editor_context.input_content
    assert all(review in editor_context.input_content for review in reviews)
    assert {item.author for item in editor_context.visible_history} == {
        "author", *(f"reviewer-{i}" for i in range(1, reviewer_count + 1))
    }

    # The author receives all critiques plus the editor's typed verdict for D1.
    assert all(review in revision_context.input_content for review in reviews)
    assert '"verdict": "revise"' in revision_context.input_content
    assert {item.author for item in revision_context.visible_history} == {
        "author", "editor", *(f"reviewer-{i}" for i in range(1, reviewer_count + 1))
    }
    assert result.calls_made == reviewer_count + 3
    assert result.depth_executed == 4

@pytest.mark.parametrize("reviewer_count", [1, 3, 5])
def test_s8_runtime_persists_exact_expected_agent_roster(reviewer_count):
    blueprint = build_strategy_blueprint("S8", k=reviewer_count)
    result = run_strategy(
        "S8", prompt(), blueprint.strategy, S8VerdictInvoker("accept"),
        prompt_views=blueprint.prompt_views,
    )
    assert result.expected_agent_ids == tuple(
        agent.identifier for agent in blueprint.strategy.agents
    )
    assert result.expected_agent_ids == (
        "author",
        *(f"reviewer-{i}" for i in range(1, reviewer_count + 1)),
        "editor",
    )


def test_s9_runtime_persists_exact_expected_voter_roster():
    blueprint = build_strategy_blueprint("S9", n=4)
    result = run_strategy(
        "S9", prompt(), blueprint.strategy, RecordingInvoker(),
        prompt_views=blueprint.prompt_views,
    )
    assert result.expected_agent_ids == ("voter-1", "voter-2", "voter-3", "voter-4")


class DelphiInvoker:
    def __init__(self, revisions):
        self.revisions = revisions
        self.calls = []

    def invoke(self, agent, step, context):
        self.calls.append((agent.identifier, step.round, step.action.value))
        if step.action.value in {"draft", "revise"}:
            value = 0 if step.round == 1 else self.revisions.get(agent.identifier, 0)
            return json.dumps({"candidate": {"value": value}})
        return json.dumps({"summary": f"Round {step.round} divergences"})


def test_s4_stops_after_exact_per_expert_stability():
    blueprint = build_strategy_blueprint("S4", n=2, T=4)
    invoker = DelphiInvoker({"expert-1": 0, "expert-2": 0})
    run = run_strategy("S4", prompt(), blueprint.strategy, invoker,
                       prompt_views=blueprint.prompt_views)
    assert {item.round for item in run.outputs} == {1, 2}
    assert run.calls_made == 6
    assert run.depth_executed == 4
    assert sum(1 for _, _, action in invoker.calls if action == "summarise") == 2


def test_s4_epsilon_stopping_uses_each_experts_successive_drafts():
    blueprint = build_strategy_blueprint("S4", n=2, T=4)
    invoker = DelphiInvoker({"expert-1": 1, "expert-2": 2})
    distances = []
    def distance(previous, current):
        distances.append((previous, current))
        return 0.05
    run = run_strategy("S4", prompt(), blueprint.strategy, invoker,
                       prompt_views=blueprint.prompt_views,
                       delphi_epsilon=0.1,
                       delphi_candidate_distance=distance)
    assert {item.round for item in run.outputs} == {1, 2}
    assert run.calls_made == 6
    assert len(distances) == 2
    assert all(previous == '{"value":0}' for previous, _ in distances)


def test_s4_continues_when_not_stable_and_distance_exceeds_epsilon():
    blueprint = build_strategy_blueprint("S4", n=2, T=3)
    invoker = DelphiInvoker({"expert-1": 1, "expert-2": 2})
    run = run_strategy("S4", prompt(), blueprint.strategy, invoker,
                       prompt_views=blueprint.prompt_views,
                       delphi_epsilon=0.01,
                       delphi_candidate_distance=lambda previous, current: 0.5)
    assert {item.round for item in run.outputs} == {1, 2, 3}
    assert run.calls_made == 9
    assert run.depth_executed == 6


def test_s4_requires_explicit_distance_when_epsilon_is_configured():
    blueprint = build_strategy_blueprint("S4", n=2, T=2)
    with pytest.raises(ValueError, match="delphi_candidate_distance is required"):
        run_strategy("S4", prompt(), blueprint.strategy, DelphiInvoker({}),
                     prompt_views=blueprint.prompt_views, delphi_epsilon=0.1)


def test_s4_rejects_delphi_options_for_other_strategies():
    blueprint = build_strategy_blueprint("S5")
    with pytest.raises(ValueError, match="only for S4"):
        run_strategy("S5", prompt(), blueprint.strategy, RecordingInvoker(),
                     prompt_views=blueprint.prompt_views, delphi_epsilon=0.1)



class ConsensusInvoker:
    def __init__(self, value_for_round):
        self.value_for_round = value_for_round
        self.calls = []

    def invoke(self, agent, step, context):
        self.calls.append((agent.identifier, step.round, step.action.value, context))
        if step.action.value == "judge":
            return json.dumps({"no_objection": True, "rationale": "The shared draft is stable."})
        return json.dumps({"candidate": {"value": self.value_for_round(step.round)}})


def test_s10_stops_after_stable_full_shared_draft_turn_and_keeps_moderator_closure():
    blueprint = build_strategy_blueprint("S10", n=2, T=4)
    invoker = ConsensusInvoker(lambda round_number: 0)
    run = run_strategy("S10", prompt(), blueprint.strategy, invoker,
                       prompt_views=blueprint.prompt_views)
    participant_rounds = {item.round for item in run.outputs if item.agent_id.startswith("participant-")}
    assert participant_rounds == {1, 2}
    assert run.calls_made == 5
    assert run.depth_executed == 5
    assert run.outputs[-1].agent_id == "moderator"
    assert run.outputs[-1].action == "judge"
    # Participant 2 sees participant 1's immediately preceding shared-draft turn.
    second_participant_call = next(call for call in invoker.calls
                                   if call[0] == "participant-2" and call[1] == 2)
    assert any(item.author == "participant-1" for item in second_participant_call[3].visible_history)


def test_s10_epsilon_stopping_compares_completed_shared_draft_states():
    blueprint = build_strategy_blueprint("S10", n=2, T=4)
    invoker = ConsensusInvoker(lambda round_number: round_number - 1)
    distances = []
    def distance(previous, current):
        distances.append((previous, current))
        return 0.04
    run = run_strategy("S10", prompt(), blueprint.strategy, invoker,
                       prompt_views=blueprint.prompt_views,
                       consensus_epsilon=0.05,
                       consensus_candidate_distance=distance)
    participant_rounds = {item.round for item in run.outputs if item.agent_id.startswith("participant-")}
    assert participant_rounds == {1, 2}
    assert len(distances) == 1
    assert distances[0] == ('{"value":0}', '{"value":1}')
    assert run.outputs[-1].agent_id == "moderator"


def test_s10_continues_until_maximum_round_when_shared_draft_keeps_changing():
    blueprint = build_strategy_blueprint("S10", n=2, T=3)
    invoker = ConsensusInvoker(lambda round_number: round_number)
    run = run_strategy("S10", prompt(), blueprint.strategy, invoker,
                       prompt_views=blueprint.prompt_views)
    participant_rounds = {item.round for item in run.outputs if item.agent_id.startswith("participant-")}
    assert participant_rounds == {1, 2, 3}
    assert run.calls_made == 7
    assert run.outputs[-1].agent_id == "moderator"


def test_s10_requires_explicit_distance_when_epsilon_is_configured():
    blueprint = build_strategy_blueprint("S10", n=2, T=2)
    with pytest.raises(ValueError, match="consensus_candidate_distance is required"):
        run_strategy("S10", prompt(), blueprint.strategy,
                     ConsensusInvoker(lambda round_number: round_number),
                     prompt_views=blueprint.prompt_views, consensus_epsilon=0.1)


def test_s10_rejects_consensus_options_for_other_strategies():
    blueprint = build_strategy_blueprint("S5")
    with pytest.raises(ValueError, match="only for S10"):
        run_strategy("S5", prompt(), blueprint.strategy, RecordingInvoker(),
                     prompt_views=blueprint.prompt_views, consensus_epsilon=0.1)



class MediationInvoker:
    def __init__(self, candidate_values):
        self.candidate_values = candidate_values
        self.calls = []

    def invoke(self, agent, step, context):
        self.calls.append((agent.identifier, step.round, step.action.value, context))
        if step.action.value == "summarise":
            return json.dumps({
                "summary": f"Round {step.round}: neutral agreements and differences",
                "agreements": ["Both parties cover the required objective"],
                "disagreements": ["The ordering of two tasks differs"],
            })
        value = self.candidate_values(step.round, agent.identifier)
        return json.dumps({"candidate": {"value": value}})


def test_s11_stops_after_party_revisions_agree_and_preserves_parallel_stages():
    blueprint = build_strategy_blueprint("S11", n=2, T=4)
    invoker = MediationInvoker(lambda round_number, party: 0 if round_number == 1 and party == "party-1" else 1)
    run = run_strategy("S11", prompt(), blueprint.strategy, invoker,
                       prompt_views=blueprint.prompt_views)
    assert {item.round for item in run.outputs} == {1, 2}
    assert run.calls_made == 10
    assert run.depth_executed == 6
    assert [(item.stage, item.round) for item in run.outputs] == [
        (1, 1), (1, 1), (2, 1), (3, 1), (3, 1),
        (4, 2), (4, 2), (5, 2), (6, 2), (6, 2),
    ]


def test_s11_epsilon_stopping_compares_two_party_revised_decompositions():
    blueprint = build_strategy_blueprint("S11", n=2, T=4)
    invoker = MediationInvoker(lambda round_number, party: 0 if party == "party-1" else 1)
    compared = []
    def distance(left, right):
        compared.append((left, right))
        return 0.03
    run = run_strategy("S11", prompt(), blueprint.strategy, invoker,
                       prompt_views=blueprint.prompt_views,
                       mediation_epsilon=0.05,
                       mediation_candidate_distance=distance)
    assert {item.round for item in run.outputs} == {1}
    assert run.calls_made == 5
    assert run.depth_executed == 3
    assert compared == [('{"value":0}', '{"value":1}')]


def test_s11_runs_through_T_when_party_revisions_remain_different():
    blueprint = build_strategy_blueprint("S11", n=2, T=3)
    invoker = MediationInvoker(lambda round_number, party: round_number + (party == "party-2"))
    run = run_strategy("S11", prompt(), blueprint.strategy, invoker,
                       prompt_views=blueprint.prompt_views,
                       mediation_epsilon=0.01,
                       mediation_candidate_distance=lambda left, right: 0.5)
    assert {item.round for item in run.outputs} == {1, 2, 3}
    assert run.calls_made == 15
    assert run.depth_executed == 9


def test_s11_requires_explicit_distance_when_epsilon_is_configured():
    blueprint = build_strategy_blueprint("S11", n=2, T=2)
    with pytest.raises(ValueError, match="mediation_candidate_distance is required"):
        run_strategy("S11", prompt(), blueprint.strategy, MediationInvoker(lambda r, p: r),
                     prompt_views=blueprint.prompt_views, mediation_epsilon=0.1)


def test_s11_rejects_mediation_options_for_other_strategies():
    blueprint = build_strategy_blueprint("S10", n=2, T=2)
    with pytest.raises(ValueError, match="only for S11"):
        run_strategy("S10", prompt(), blueprint.strategy, RecordingInvoker(),
                     prompt_views=blueprint.prompt_views, mediation_epsilon=0.1)
