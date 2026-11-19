import json
from sociodec.direct_e1 import ExecutorRun
from sociodec.execution import ExecutionStatus
from sociodec.models.decomposition import Decomposition, Dependency, DeliverableComposition, Subproblem
from sociodec.models.prompt import Constraint, ConstraintKind, Interpretation, Prompt
from sociodec.providers.base import GenerationResult
from sociodec.provider_executor import ProviderFixedExecutor

class FakeProvider:
    provider_name = "fake"
    model_name = "fake-model"
    def __init__(self, outputs): self.outputs = iter(outputs); self.calls = []
    def generate(self, messages, config=None):
        self.calls.append((messages, config))
        text = next(self.outputs)
        return GenerationResult(text, "fake", "fake-model", 12, 4, "stop", f"req-{len(self.calls)}")

def fixture():
    hard = Constraint("The response must be no more than 20 days", ConstraintKind.HARD)
    prompt = Prompt("Create a service plan within 20 days.",
        Interpretation("Create a service plan", constraints=(hard,), deliverables=("Service plan",)))
    s1 = Subproblem("s1", "Analyse the service", (), "Analysis")
    s2 = Subproblem("s2", "Design the service", ("Analysis",), "Design")
    decomposition = Decomposition((s1,s2),(Dependency("s1","s2"),),
        (DeliverableComposition("Service plan",("s2",)),))
    return prompt, decomposition

def test_provider_executor_runs_topologically_and_records_predecessor_answer():
    prompt, decomposition = fixture()
    provider = FakeProvider([
        json.dumps({"answer":"analysis"}),
        json.dumps({"answer":"design"}),
        json.dumps({"composed_answer":"Plan delivered within 20 days."}),
        json.dumps({"satisfied":True,"evidence":"The answer states the 20-day limit."}),
    ])
    executor = ProviderFixedExecutor(provider, executor_id="executor-v1")
    result = executor.execute(prompt=prompt,decomposition=decomposition,seed=7)
    assert isinstance(result, ExecutorRun)
    assert result.calls_made == 4
    assert [x.subproblem_id for x in result.execution.executions] == ["s1","s2"]
    assert result.execution.executions[1].predecessor_answers[0].answer == "analysis"
    assert result.execution.composed_answer.startswith("Plan delivered")
    assert result.execution.constraint_assessments[0].satisfied is True
    assert len(result.provider_trace) == 4
    assert all(call[1].temperature == 0 for call in provider.calls)

def test_provider_executor_fails_closed_on_bad_subproblem_json_and_blocks_dependents():
    prompt, decomposition = fixture()
    provider = FakeProvider([
        "not-json",
        json.dumps({"composed_answer":"Partial answer"}),
        json.dumps({"satisfied":False,"evidence":"No evidence of compliance."}),
    ])
    executor = ProviderFixedExecutor(provider, executor_id="executor-v1")
    result = executor.execute(prompt=prompt,decomposition=decomposition,seed=3)
    records = {x.subproblem_id:x for x in result.execution.executions}
    assert records["s1"].status is ExecutionStatus.FAILED
    assert records["s2"].status is ExecutionStatus.FAILED
    assert result.calls_made == 3
    assert result.execution.constraint_assessments[0].satisfied is False

def test_provider_executor_records_invalid_constraint_assessment_as_failure():
    prompt, decomposition = fixture()
    provider = FakeProvider([
        json.dumps({"answer":"analysis"}), json.dumps({"answer":"design"}),
        json.dumps({"composed_answer":"Answer"}),
        json.dumps({"satisfied":"yes","evidence":"Looks fine"}),
    ])
    result = ProviderFixedExecutor(provider,executor_id="executor-v1").execute(
        prompt=prompt,decomposition=decomposition,seed=0)
    assessment = result.execution.constraint_assessments[0]
    assert assessment.satisfied is False
    assert "malformed" in assessment.evidence

def test_executor_rejects_cyclic_decomposition():
    prompt, decomposition = fixture()
    cyclic = Decomposition(decomposition.subproblems,
        (Dependency("s1","s2"),Dependency("s2","s1")),decomposition.composition)
    executor = ProviderFixedExecutor(FakeProvider([]),executor_id="executor-v1")
    import pytest
    with pytest.raises(ValueError,match="acyclic"):
        executor.execute(prompt=prompt,decomposition=cyclic,seed=0)
