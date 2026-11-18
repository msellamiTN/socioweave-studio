import json

import pytest

from sociodec.models.strategy import Agent, Action, Role, ProtocolStep
from sociodec.providers.base import GenerationResult
from sociodec.providers.protocol_invoker import ProviderProtocolInvoker
from sociodec.runtime import ProtocolContext


class RecordingProvider:
    provider_name = "recording"
    model_name = "family-model-v2"

    def __init__(self):
        self.requests = []

    def generate(self, messages, config=None):
        self.requests.append(messages)
        return GenerationResult(
            "typed protocol response", self.provider_name, self.model_name,
            12, 7, "stop", f"req-{len(self.requests)}",
        )


def _context():
    return ProtocolContext(
        prompt_view='{"assigned_domains":["finance"]}',
        agent_context="domain expert",
        agent_id="expert-1",
        role=Role.DECOMPOSER,
        action="draft",
        input_ref="prompt",
        input_content='{"assigned_domains":["finance"]}',
        hypotheses=(),
        visible_history=(),
    )


def test_provider_invoker_routes_by_model_id_and_records_family_and_trace():
    provider = RecordingProvider()
    invoker = ProviderProtocolInvoker(
        {"model-v2": provider},
        model_families={"model-v2": "family-a"},
    )
    agent = Agent("expert-1", "model-v2", "domain expert")
    step = ProtocolStep("expert-1", Action.DRAFT, "prompt", 1, 1)
    result = invoker.invoke(agent, step, _context())
    assert result == "typed protocol response"
    assert len(provider.requests) == 1
    payload = json.loads(provider.requests[0][1].content)
    assert payload["prompt_view"] == '{"assigned_domains":["finance"]}'
    trace = invoker.traces[0]
    assert trace.agent_id == "expert-1"
    assert trace.model_id == "model-v2"
    assert trace.model_family == "family-a"
    assert trace.returned_model == "family-model-v2"
    assert trace.input_tokens == 12
    assert trace.output_tokens == 7
    assert trace.request_id == "req-1"
    assert len(trace.input_sha256) == len(trace.output_sha256) == 64


def test_provider_invoker_requires_explicit_provider_and_family_mapping():
    with pytest.raises(ValueError, match="exactly one model family"):
        ProviderProtocolInvoker(
            {"model-v2": RecordingProvider()}, model_families={},
        )


def test_provider_invoker_fails_closed_for_unconfigured_agent_model():
    invoker = ProviderProtocolInvoker(
        {"model-v2": RecordingProvider()},
        model_families={"model-v2": "family-a"},
    )
    with pytest.raises(ValueError, match="No provider/model-family configuration"):
        invoker.invoke(
            Agent("expert-1", "unconfigured", "expert"),
            ProtocolStep("expert-1", Action.DRAFT, "prompt", 1, 1),
            _context(),
        )


def test_provider_invoker_rejects_empty_provider_output():
    class EmptyProvider(RecordingProvider):
        def generate(self, messages, config=None):
            return GenerationResult("", self.provider_name, self.model_name)
    invoker = ProviderProtocolInvoker(
        {"model-v2": EmptyProvider()},
        model_families={"model-v2": "family-a"},
    )
    with pytest.raises(ValueError, match="empty protocol output"):
        invoker.invoke(
            Agent("expert-1", "model-v2", "expert"),
            ProtocolStep("expert-1", Action.DRAFT, "prompt", 1, 1),
            _context(),
        )
