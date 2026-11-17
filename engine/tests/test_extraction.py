import json
import pytest
from sociodec.extraction import (
    AmbiguityFlag, ConflictPair, ExtractionFormatError,
    aggregate_extractions, parse_extraction, run_extractors,
)
from sociodec.models.prompt import SourceSpan

PROMPT = "The service must respond within 20 days and provide an online form."

def payload():
    return {
        "requirements": [{
            "statement": "Response within 20 days", "type": "target",
            "domain": "service", "source_span": {"start": 0, "end": 42},
            "entity_names": [],
        }],
        "hypotheses": [{
            "statement": "Provide an appeal procedure", "type": "deliverable",
            "domain": "legal", "rationale": "A review route may be needed",
            "entity_names": [],
        }],
        "entities": [{"name": "Service", "description": "Public service"}],
        "ambiguities": [{
            "subject": "20 days", "readings": ["calendar days", "working days"],
            "explanation": "Calendar convention is unspecified",
        }],
        "conflicts": [],
    }

def test_parse_keeps_explicit_and_implicit_separate():
    result = parse_extraction(json.dumps(payload()), PROMPT, "extractor-a")
    assert len(result.requirements) == 1
    assert len(result.hypotheses) == 1
    assert result.requirements[0].source_span == SourceSpan(0, 42)
    assert result.extractor_id == "extractor-a"

def test_parse_rejects_invalid_source_span():
    data = payload()
    data["requirements"][0]["source_span"] = {"start": 0, "end": 999}
    with pytest.raises(ExtractionFormatError):
        parse_extraction(json.dumps(data), PROMPT, "bad-span")

def test_aggregation_unions_and_deduplicates_with_provenance():
    a = parse_extraction(json.dumps(payload()), PROMPT, "a")
    data = payload()
    data["requirements"][0]["statement"] = " RESPONSE within 20 days! "
    b = parse_extraction(json.dumps(data), PROMPT, "b")
    result = aggregate_extractions([a, b])
    assert len(result.requirements) == 1
    assert set(result.requirement_sources["response within 20 days"]) == {"a", "b"}
    assert len(result.hypotheses) == 1
    assert len(result.entities) == 1
    assert len(result.ambiguities) == 1

def test_different_requirement_types_are_not_merged():
    a = parse_extraction(json.dumps(payload()), PROMPT, "a")
    data = payload()
    data["requirements"][0]["type"] = "constraint"
    b = parse_extraction(json.dumps(data), PROMPT, "b")
    assert len(aggregate_extractions([a, b]).requirements) == 2

def test_empty_extractor_list_is_rejected():
    with pytest.raises(ValueError):
        run_extractors(PROMPT, [])

def test_ambiguity_and_conflict_invariants():
    with pytest.raises(ValueError):
        AmbiguityFlag("term", ("one",))
    with pytest.raises(ValueError):
        ConflictPair("same", "same")
