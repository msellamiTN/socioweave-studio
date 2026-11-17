import json

import pytest

from sociodec.extraction import (
    ExtractionFormatError, ProviderRequirementExtractor, aggregate_extractions,
    parse_extraction, run_extractors,
)
from sociodec.providers.base import GenerationResult


def valid_payload():
    return {
        "requirements": [], "hypotheses": [], "entities": [],
        "ambiguities": [], "conflicts": [],
    }


@pytest.mark.parametrize("raw", ["", "not json", "{broken}", "[]", "null"])
def test_parser_rejects_malformed_or_non_object_json_roots(raw):
    with pytest.raises(ExtractionFormatError):
        parse_extraction(raw, "prompt", "x")


def test_parser_accepts_fenced_json_and_preserves_raw_response():
    raw = "```json\n" + json.dumps(valid_payload()) + "\n```"
    result = parse_extraction(raw, "prompt", "fenced")
    assert result.extractor_id == "fenced"
    assert result.raw_response == raw


@pytest.mark.parametrize("section,value", [
    ("requirements", [{"statement": "x", "type": "unknown", "domain": "d",
                       "source_span": {"start": 0, "end": 1}}]),
    ("hypotheses", [{"statement": "x", "type": "unknown", "domain": "d"}]),
    ("entities", [{"name": "  "}]),
    ("ambiguities", [{"subject": "x", "readings": ["only one"]}]),
    ("conflicts", [{"left": "same", "right": "same"}]),
])
def test_parser_rejects_invalid_records_in_each_section(section, value):
    data = valid_payload()
    data[section] = value
    with pytest.raises(ExtractionFormatError):
        parse_extraction(json.dumps(data), "x prompt", "bad")


def test_provenance_does_not_collide_when_statement_has_different_types_or_domains():
    prompt = "same words"
    def item(kind, domain):
        data = valid_payload()
        data["requirements"] = [{
            "statement": "same words", "type": kind, "domain": domain,
            "source_span": {"start": 0, "end": len(prompt)},
        }]
        return parse_extraction(json.dumps(data), prompt, kind + domain)
    a = item("target", "service")
    b = item("constraint", "service")
    c = item("target", "legal")
    result = aggregate_extractions([a, b, c])
    assert len(result.requirements) == 3
    assert result.requirement_sources == {
        "target|service|same words": ("targetservice",),
        "constraint|service|same words": ("constraintservice",),
        "target|legal|same words": ("targetlegal",),
    }


def test_semantically_equivalent_duplicate_keeps_all_extractor_provenance():
    prompt = "Respond within 20 days."
    def extracted(statement, extractor):
        data = valid_payload()
        data["requirements"] = [{
            "statement": statement, "type": "target", "domain": "service",
            "source_span": {"start": 0, "end": len(prompt)},
        }]
        return parse_extraction(json.dumps(data), prompt, extractor)
    result = aggregate_extractions([
        extracted("Respond within 20 days", "a"),
        extracted(" RESPOND within 20 days! ", "b"),
    ])
    assert len(result.requirements) == 1
    assert result.requirement_sources["target|service|respond within 20 days"] == ("a", "b")


def test_custom_equivalence_matcher_is_used_for_requirements():
    prompt = "one two"
    def extracted(statement, extractor):
        data = valid_payload()
        data["requirements"] = [{
            "statement": statement, "type": "target", "domain": "d",
            "source_span": {"start": 0, "end": len(prompt)},
        }]
        return parse_extraction(json.dumps(data), prompt, extractor)
    result = aggregate_extractions(
        [extracted("one", "a"), extracted("two", "b")],
        matcher=lambda left, right: True,
    )
    assert len(result.requirements) == 1
    assert result.requirement_sources["target|d|one"] == ("a", "b")


class StubProvider:
    provider_name = "stub"
    model_name = "stub-model"

    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate(self, messages, config=None):
        self.calls.append((messages, config))
        return GenerationResult(text=self.response, provider=self.provider_name, model=self.model_name)


def test_provider_extractor_uses_configured_generation_and_parses_response():
    raw = json.dumps(valid_payload())
    provider = StubProvider(raw)
    extractor = ProviderRequirementExtractor(provider, "stub-extractor")
    result = extractor.extract("A user prompt")
    assert result.extractor_id == "stub-extractor"
    assert len(provider.calls) == 1
    messages, config = provider.calls[0]
    assert messages[0].role == "system"
    assert "source_span" in messages[0].content
    assert "A user prompt" in messages[1].content
    assert config.temperature == 0.7
    assert config.max_new_tokens == 1024


def test_run_extractors_preserves_order_and_returns_every_extractor_result():
    class Extractor:
        def __init__(self, identifier):
            self.extractor_id = identifier
        def extract(self, prompt_text):
            return parse_extraction(json.dumps(valid_payload()), prompt_text, self.extractor_id)
    result = run_extractors("prompt", [Extractor("first"), Extractor("second")])
    assert [x.extractor_id for x in result.extractor_results] == ["first", "second"]