import json

import pytest

from sociodec.providers.base import GenerationResult
from sociodec.small_model_runtime import (
    SmallModelConfig, parse_decomposition, run_small_model_core,
)


PROMPT = "Build a permit. Report."


def extraction_response():
    return json.dumps({
        "requirements": [
            {"statement": "Build a permit", "type": "target", "domain": "service",
             "source_span": {"start": 0, "end": 15}},
            {"statement": "Provide a report", "type": "deliverable", "domain": "reporting",
             "source_span": {"start": 16, "end": 22}},
        ],
        "hypotheses": [],
        "entities": [],
        "ambiguities": [],
        "conflicts": [],
    })


def decomposition_response():
    return json.dumps({
        "subproblems": [
            {"id": "sp1", "question": "Design the permit service", "inputs": [],
             "output": "Permit service design", "covered_requirements": ["Build a permit"],
             "local_constraints": []},
            {"id": "sp2", "question": "Prepare the report", "inputs": ["Permit service design"],
             "output": "Permit report", "covered_requirements": ["Provide a report"],
             "local_constraints": []},
        ],
        "dependencies": [{"source_id": "sp1", "target_id": "sp2"}],
        "composition": {"Provide a report": ["sp2"]},
    })


class FakeProvider:
    model_name = "fake-small-model"

    def __init__(self):
        self.responses = [extraction_response()] * 3 + [decomposition_response()]
        self.calls = 0

    def generate(self, messages, config=None):
        self.calls += 1
        return GenerationResult(
            text=self.responses.pop(0), provider="fake", model=self.model_name,
            input_tokens=100, output_tokens=80, finish_reason="stop",
        )


def test_small_model_config_is_t4_oriented_and_keeps_paper_q():
    cfg = SmallModelConfig()
    assert cfg.model_id == "Qwen/Qwen2.5-1.5B-Instruct"
    assert cfg.load_in_4bit is True
    assert cfg.extractor_count == 3
    with pytest.raises(ValueError, match="q=3"):
        SmallModelConfig(extractor_count=1)


def test_small_model_core_runs_extraction_aggregation_decomposition_and_validation():
    provider = FakeProvider()
    run = run_small_model_core(PROMPT, provider=provider)
    assert provider.calls == 4
    assert run.provider_calls == 4
    assert len(run.extraction.extractor_results) == 3
    assert len(run.extraction.requirements) == 2
    assert len(run.decomposition.subproblems) == 2
    assert run.validation.v1_coverage.status.value == "pass"
    assert run.validation.v2_acyclicity.status.value == "pass"
    assert run.validation.v5_composition.status.value == "pass"
    assert run.validation.v3_solvability.status.value == "not_evaluated"
    assert run.validation.v4_faithfulness.status.value == "not_evaluated"
    report = run.report()
    assert report["scientific_result"] is False
    assert report["mode"] == "engineering_smoke_only"


def test_small_model_parser_rejects_invented_requirement_references():
    with pytest.raises(ValueError, match="unknown requirement"):
        parse_decomposition(
            json.dumps({
                "subproblems": [{
                    "id": "sp1", "question": "Do work", "inputs": [],
                    "output": "Done", "covered_requirements": ["invented"],
                    "local_constraints": [],
                }],
                "dependencies": [],
                "composition": {},
            }),
            requirements=(), constraints=(),
        )


def test_small_model_parser_rejects_non_json_output():
    with pytest.raises(json.JSONDecodeError):
        parse_decomposition("not json", requirements=(), constraints=())
