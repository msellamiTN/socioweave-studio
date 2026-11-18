import json
import pytest
from sociodec.c1_provider_adapter import C1ProviderAdapter, _candidate_distance
from sociodec.providers.base import GenerationResult
from sociodec.models.decomposition import Decomposition, Subproblem
from sociodec.extraction import ExtractionResult, Hypothesis, aggregate_extractions
from sociodec.models.prompt import Constraint, ConstraintKind, Interpretation, Prompt, Requirement, RequirementType, SourceSpan


class FakeProvider:
    provider_name = "fake"
    model_name = "fake-model"
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []
    def generate(self, messages, config=None):
        self.calls.append(messages)
        return GenerationResult(next(self.outputs), "fake", "fake-model", request_id="req-test")


def fixture():
    task = "Build an accessible service within budget."
    req = Requirement("Build accessible service", RequirementType.TARGET, "service", SourceSpan(0, len(task)))
    hyp = Hypothesis("Provide an appeal route", RequirementType.DELIVERABLE, "legal", "review route")
    con = Constraint("Within budget", ConstraintKind.HARD)
    prompt = Prompt(task, Interpretation("Build service", constraints=(con,), deliverables=("Service plan",)))
    extraction = aggregate_extractions((ExtractionResult(requirements=(req,), hypotheses=(hyp,), extractor_id="extractor"),))
    candidate = {
        "candidate_id": "c",
        "subproblems": [{"id":"s1","question":"Design service","inputs":["requirements"],"output":"Service plan",
          "local_constraints":[{"kind":"hard","statement":"Within budget"}],
          "covered_requirements":[{"type":"target","domain":"service","statement":"Build accessible service"}]}],
        "dependencies": [], "kappa":{"Service plan":["s1"]}
    }
    return prompt, extraction, candidate


def test_provider_adapter_draft_uses_provider_and_strict_candidate_decoder():
    prompt, extraction, raw = fixture()
    provider = FakeProvider([json.dumps({"candidate": raw})])
    adapter = C1ProviderAdapter(prompt=prompt, extraction=extraction, providers={"m1":provider},
        model_ids={"author-1":"m1"}, model_families={"m1":"family-1"})
    candidate = adapter.callbacks(comparator_actor="cmp", synthesizer_actor="syn", judge_actor="judge",
        algorithm1_check_and_repair=lambda d:(d,())) .draft("author-1")
    assert candidate.decomposition.subproblems[0].identifier == "s1"
    assert len(provider.calls) == 1
    assert adapter.traces[0].phase == "gen"
    assert adapter.traces[0].model_family == "family-1"
    assert len(adapter.traces[0].input_sha256) == 64 and len(adapter.traces[0].output_sha256) == 64


def test_adapter_requires_exact_provider_model_configuration():
    prompt, extraction, _ = fixture()
    with pytest.raises(ValueError, match="providers"):
        C1ProviderAdapter(prompt=prompt, extraction=extraction, providers={}, model_ids={"author":"m1"}, model_families={"m1":"f"})


def test_structural_distance_is_zero_for_same_decomposition():
    candidate = Decomposition((Subproblem("s1","question",("in",),"out"),),(),())
    wrapped = type("CandidateWrapper", (), {"decomposition":candidate})()
    assert _candidate_distance(wrapped, wrapped) == 0.0
