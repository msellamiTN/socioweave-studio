import json

import pytest

from sociodec.direct_baselines import (
    BASELINE_CHOICES, PROFILE_ID, DirectBaselineAdapter,
)
from sociodec.e1_protocol import E1Condition
from sociodec.extraction import ExtractionResult, aggregate_extractions
from sociodec.models.prompt import (
    Interpretation, Prompt, Requirement, RequirementType, SourceSpan,
)
from sociodec.providers.base import GenerationResult


PROMPT = Prompt("Create a report.", Interpretation(
    "Create a report", deliverables=("Report",),
))
REQUIREMENT = Requirement(
    "Create a report", RequirementType.DELIVERABLE, "report", SourceSpan(0, 16),
)
EXTRACTION = aggregate_extractions((
    ExtractionResult(requirements=(REQUIREMENT,), extractor_id="extractor-1"),
))


def candidate(question="Create a report"):
    return {
        "candidate": {
            "candidate_id": "candidate-1",
            "subproblems": [{
                "id": "s1", "question": question, "inputs": [],
                "output": "Report", "local_constraints": [],
                "covered_requirements": [{
                    "type": "deliverable", "domain": "report",
                    "statement": "Create a report",
                }],
            }],
            "dependencies": [],
            "kappa": {"Report": ["s1"]},
        }
    }


class FakeProvider:
    def __init__(self, model_name="model-A"):
        self._model_name = model_name
        self.calls = []

    @property
    def provider_name(self):
        return "fake-test-provider"

    @property
    def model_name(self):
        return self._model_name

    def generate(self, messages, config=None):
        system = messages[0].content
        self.calls.append((system, messages[1].content, config))
        if "Critique your own decomposition" in system:
            output = json.dumps({"issues": []})
        elif "Evaluate the candidate decomposition" in system:
            output = json.dumps({"verdict": "accept", "rationale": "No blocking issue", "findings": []})
        elif "Debate the decomposition" in system:
            output = json.dumps({"argument": "Candidate is coherent", "proposed_changes": []})
        elif "Select the better" in system:
            output = json.dumps({"selected_candidate_id": "debater-1-draft", "rationale": "Better coverage"})
        else:
            output = json.dumps(candidate())
        return GenerationResult(output, self.provider_name, self.model_name)


def condition(baseline, budget):
    return E1Condition(
        "smart-administration", baseline, "homogeneous", 0, ("prompt-001",),
        budget, matched_strategy_id="S1",
    )


@pytest.mark.parametrize("baseline,budget,expected", [
    ("single_plan_and_solve", 5, 1),
    ("single_self_refinement", 5, 3),
    ("single_self_consistency", 5, 5),
    ("decomposer_plus_evaluator", 5, 2),
    ("multi_agent_debate", 5, 5),
    ("nominal_multi_agent", 5, 3),
])
def test_each_baseline_executes_under_profile_and_records_calls(baseline, budget, expected):
    providers = {}

    def resolve(_condition, agent_id):
        providers.setdefault(agent_id, FakeProvider())
        return providers[agent_id]

    adapter = DirectBaselineAdapter(extraction=EXTRACTION, provider_resolver=resolve)
    result = adapter.run(condition=condition(baseline, budget), prompt=PROMPT, seed=7)

    assert result.calls_made == expected
    assert len(result.provider_trace) == expected
    assert result.metadata["baseline_profile_id"] == PROFILE_ID
    assert result.metadata["baseline_profile_status"] == "implementation_choice_not_fully_specified_by_paper"
    assert result.metadata["baseline_operational_choice"] == BASELINE_CHOICES[baseline]
    assert result.metadata["selection_uses_gold_labels"] is False
    assert result.decomposition.subproblems


def test_self_consistency_aggregates_equivalent_subproblems_and_reconstructs_kappa():
    adapter = DirectBaselineAdapter(
        extraction=EXTRACTION,
        provider_resolver=lambda _condition, _agent: FakeProvider(),
    )
    result = adapter.run(
        condition=condition("single_self_consistency", 5), prompt=PROMPT, seed=11,
    )
    assert len(result.decomposition.subproblems) == 1
    assert result.decomposition.kappa == {"Report": frozenset({"sc-1"})}


def test_baselines_fail_closed_when_fixed_protocol_exceeds_minimum_budget():
    adapter = DirectBaselineAdapter(
        extraction=EXTRACTION,
        provider_resolver=lambda _condition, _agent: FakeProvider(),
    )
    with pytest.raises(ValueError, match="requires three calls"):
        adapter.run(
            condition=condition("single_self_refinement", 2), prompt=PROMPT, seed=1,
        )
    with pytest.raises(ValueError, match="at least three calls"):
        adapter.run(
            condition=condition("multi_agent_debate", 2), prompt=PROMPT, seed=1,
        )


def test_nominal_selection_uses_extracted_requirements_not_reference_labels():
    providers = {}

    def resolve(_condition, agent_id):
        providers.setdefault(agent_id, FakeProvider())
        return providers[agent_id]

    adapter = DirectBaselineAdapter(extraction=EXTRACTION, provider_resolver=resolve)
    result = adapter.run(
        condition=condition("nominal_multi_agent", 5), prompt=PROMPT, seed=13,
    )
    assert result.metadata["selection_uses_gold_labels"] is False
    assert result.metadata["method_calls"] == 3
