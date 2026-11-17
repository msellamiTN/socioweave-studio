import pytest

from sociodec.models.strategy import Agent, ProtocolStep, Role, Action
from sociodec.providers.base import ChatMessage, GenerationResult
from sociodec.provider_runtime import ProviderProtocolInvoker, protocol_messages
from sociodec.runtime import ProtocolContext


class FakeProvider:
    provider_name = "fake"
    model_name = "fake-model"

    def __init__(self):
        self.requests = []

    def generate(self, messages, config=None):
        self.requests.append((messages, config))
        return GenerationResult('{"ok": true}', "fake", "fake-model",
                                12, 4, "stop", "req-1")


def _context():
    return ProtocolContext(
        prompt_view="visible prompt", agent_context="analyst context",
        agent_id="a1", role=Role.DECOMPOSER, action="draft",
        input_ref="prompt", input_content="visible prompt", hypotheses=(),
        visible_history=(),
    )


def test_provider_invoker_maps_protocol_context_and_records_trace():
    provider = FakeProvider()
    traces = []
    invoker = ProviderProtocolInvoker(provider, on_trace=traces.append, seed=7)
    agent = Agent("a1", "fake-model", "analyst context")
    step = ProtocolStep("a1", Action.DRAFT, "prompt", 1, 1, True)
    result = invoker.invoke(agent, step, _context())
    assert result == '{"ok": true}'
    assert len(provider.requests) == len(traces) == 1
    messages, config = provider.requests[0]
    assert all(isinstance(item, ChatMessage) for item in messages)
    assert config.temperature == 0.7 and config.max_new_tokens == 1024
    assert config.seed == 7
    assert traces[0].provider == "fake"
    assert traces[0].model == "fake-model"
    assert traces[0].input_tokens == 12 and traces[0].output_tokens == 4
    assert traces[0].request_id == "req-1"
    assert len(traces[0].prompt_sha256) == len(traces[0].output_sha256) == 64


def test_protocol_messages_only_include_context_visible_history():
    provider = FakeProvider()
    invoker = ProviderProtocolInvoker(provider)
    agent = Agent("a1", "fake-model", "")
    step = ProtocolStep("a1", Action.CRITIQUE, "prompt", 1, 1, True)
    context = _context()
    invoker.invoke(agent, step, context)
    payload = provider.requests[0][0][1].content
    assert "visible prompt" in payload
    assert "hidden peer draft" not in payload


def test_invoker_rejects_empty_provider_completion():
    class EmptyProvider(FakeProvider):
        def generate(self, messages, config=None):
            return GenerationResult(" ", "fake", "fake-model")
    invoker = ProviderProtocolInvoker(EmptyProvider())
    with pytest.raises(ValueError, match="empty completion"):
        invoker.invoke(Agent("a1", "fake-model", ""), 
                       ProtocolStep("a1", Action.DRAFT, "prompt", 1, 1, True),
                       _context())
