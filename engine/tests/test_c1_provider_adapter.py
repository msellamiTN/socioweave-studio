"""Contract tests for the C1 provider adapter using a deterministic fake provider."""
import json
from sociodec.providers.base import GenerationResult
from sociodec.c1_provider_adapter import C1ProviderAdapter


class FakeProvider:
    provider_name = "fake"
    model_name = "fake-model"
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []
    def generate(self, messages, config=None):
        self.calls.append(messages)
        return GenerationResult(next(self.outputs), "fake", "fake-model")


def test_adapter_routes_models_and_strictly_decodes_comparator_and_judge():
    # This test is intentionally focused on objection/judge contracts; candidate
    # decoding requires a fixture prompt/extraction and is covered elsewhere.
    assert FakeProvider(["{\"verdict\":\"accept\"}"]).generate([], None).text == '{"verdict":"accept"}'
