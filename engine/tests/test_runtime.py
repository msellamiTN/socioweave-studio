import pytest

from sociodec.extraction import Hypothesis
from sociodec.models.prompt import Interpretation, Prompt, RequirementType
from sociodec.models.strategy import (
    Action, Agent, DecisionRule, ProtocolStep, Role, RoleAssignment,
    SocialStrategy, VisibilityRound,
)
from sociodec.runtime import run_strategy


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


# Serialized provider-boundary privacy regression tests.
def test_provider_serialized_delphi_anonymity_and_peer_visibility_contracts():
    import json
    from sociodec.providers.base import GenerationResult
    from sociodec.providers.protocol_invoker import ProviderProtocolInvoker

    class PromptRecordingProvider:
        provider_name = "test-provider"
        model_name = "test-model"
        def __init__(self):
            self.requests = []
        def generate(self, messages, config=None):
            self.requests.append(messages)
            return GenerationResult("opaque-response", self.provider_name, self.model_name)

    provider = PromptRecordingProvider()
    invoker = ProviderProtocolInvoker(
        {"model-A": provider, "model-B": provider},
        model_families={"model-A": "family-A", "model-B": "family-B"},
    )
    # Synthetic Delphi-style contract: first-round drafts are private; later
    # peer-visible history is author-masked at the runtime AND serialized edge.
    anon_strategy = strategy(anonymous=True, peer_visible=False)
    result = run_strategy("delphi-privacy-contract", prompt(), anon_strategy, invoker)
    payloads = [json.loads(messages[1].content) for messages in provider.requests]
    first_round_payloads = payloads[:2]
    assert all(payload["visible_history"] == [] for payload in first_round_payloads)
    assert "a1:draft" not in first_round_payloads[1]["input_content"]
    later_payload = payloads[2]
    assert later_payload["visible_history"]
    assert {item["author"] for item in later_payload["visible_history"]} == {"anonymous"}
    assert "a1" not in {item["author"] for item in later_payload["visible_history"]}
    assert "a2" not in {item["author"] for item in later_payload["visible_history"]}
    # The request still exposes the current actor ID; this test does not claim
    # full identity unlinkability or remove identity from traces/telemetry.
    assert later_payload["agent_id"] in {"a1", "a2"}


def test_provider_serialized_nominal_group_first_round_peer_drafts_are_hidden():
    import json
    from sociodec.providers.base import GenerationResult
    from sociodec.providers.protocol_invoker import ProviderProtocolInvoker

    class PromptRecordingProvider:
        provider_name = "test-provider"
        model_name = "test-model"
        def __init__(self):
            self.requests = []
        def generate(self, messages, config=None):
            self.requests.append(messages)
            return GenerationResult("candidate draft", self.provider_name, self.model_name)

    provider = PromptRecordingProvider()
    invoker = ProviderProtocolInvoker(
        {"model-A": provider, "model-B": provider},
        model_families={"model-A": "family-A", "model-B": "family-B"},
    )
    # Synthetic NGT-style visibility contract: both initial drafts must be
    # provider-isolated. Later peer exposure is not tested as an NGT ranking
    # implementation here; strategy-factory wiring remains a separate audit.
    run_strategy("ngt-visibility-contract", prompt(), strategy(peer_visible=False), invoker)
    payloads = [json.loads(messages[1].content) for messages in provider.requests]
    assert len(payloads) >= 2
    assert all(payload["visible_history"] == [] for payload in payloads[:2])
    assert all("a1:draft" not in payload["input_content"] for payload in payloads[:2])
    assert all("a2:draft" not in payload["input_content"] for payload in payloads[:2])


@pytest.mark.parametrize("strategy_id,n,T,expected_calls", [("S3", 2, 2, 4), ("S4", 2, 2, 6)])
def test_real_s3_s4_blueprints_preserve_anonymity_and_peer_visibility_in_provider_json(strategy_id, n, T, expected_calls):
    import json
    from sociodec.catalogue import StrategyId
    from sociodec.providers.base import GenerationResult
    from sociodec.providers.protocol_invoker import ProviderProtocolInvoker
    from sociodec.strategy_protocols import build_strategy_blueprint

    class CapturingProvider:
        provider_name = "mock-provider"
        model_name = "mock-model"
        def __init__(self):
            self.requests = []
        def generate(self, messages, config=None):
            self.requests.append(messages)
            return GenerationResult("candidate decomposition text", self.provider_name, self.model_name)

    provider = CapturingProvider()
    models = {f"agent-{i}": provider for i in range(1, n + 1)}
    models.update({"member-1": provider, "member-2": provider, "expert-1": provider, "expert-2": provider, "facilitator": provider})
    families = {key: "same-test-family" for key in models}
    invoker = ProviderProtocolInvoker(models, model_families=families)
    blueprint = build_strategy_blueprint(StrategyId(strategy_id), n=n, T=T)
    result = run_strategy(strategy_id, prompt(), blueprint.strategy, invoker, prompt_views=blueprint.prompt_views)
    payloads = [json.loads(messages[1].content) for messages in provider.requests]
    assert result.calls_made == expected_calls
    assert len(payloads) == expected_calls

    if strategy_id == "S3":
        # NGT: member drafts are private in round 1; rankings see the pooled
        # drafts, but the provider serialization masks their authors.
        initial = payloads[:n]
        rankings = payloads[n:]
        assert all(p["visible_history"] == [] for p in initial)
        assert all("anonymous" not in p["input_content"] for p in initial)
        assert all("member-1" not in p["input_content"] and "member-2" not in p["input_content"] for p in initial)
        assert all(p["visible_history"] for p in rankings)
        assert all({v["author"] for v in p["visible_history"]} == {"anonymous"} for p in rankings)
        assert all("anonymous" in p["input_content"] for p in rankings)
        assert all("member-1" not in p["input_content"] and "member-2" not in p["input_content"] for p in rankings)
    else:
        # Delphi: first-round expert drafts remain independent. Facilitator
        # summaries and second-round revisions serialize anonymous author labels.
        first_round = payloads[:n]
        facilitator = payloads[n]
        revisions = payloads[n + 1:n + 1 + n]
        assert all(p["visible_history"] == [] for p in first_round)
        assert all("anonymous" not in p["input_content"] for p in first_round)
        assert facilitator["visible_history"]
        assert {v["author"] for v in facilitator["visible_history"]} == {"anonymous"}
        assert all(p["visible_history"] for p in revisions)
        assert all({v["author"] for v in p["visible_history"]} == {"anonymous"} for p in revisions)
        assert all("expert-1" not in p["input_content"] and "expert-2" not in p["input_content"] for p in payloads)
