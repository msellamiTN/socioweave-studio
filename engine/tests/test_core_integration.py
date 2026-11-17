import json

from sociodec.extraction import parse_extraction
from sociodec.models.prompt import Interpretation, Prompt


def test_extracted_explicit_requirements_validate_against_prompt_model():
    prompt_text = "The service must respond within 20 days."
    payload = {
        "requirements": [{
            "statement": "Response within 20 days",
            "type": "target",
            "domain": "service",
            "source_span": {"start": 4, "end": 40},
            "entity_names": [],
        }],
        "hypotheses": [],
        "entities": [],
        "ambiguities": [],
        "conflicts": [],
    }
    extraction = parse_extraction(json.dumps(payload), prompt_text, "integration")
    prompt = Prompt(prompt_text, Interpretation("Improve service response"))
    prompt.validate_explicit_requirements(extraction.requirements)
    assert extraction.requirements[0].source_span.extract(prompt.x) == "service must respond within 20 days."