import json

import pytest

from sociodec.campaign import FixedExecutor
from sociodec.experiments import BenchmarkPrompt, ExperimentConfig, TrialContext, TrialOutcome
from sociodec.execution import ConstraintAssessment, ExecutionRun, ExecutionStatus, SubproblemExecution
from sociodec.extraction import AggregatedExtraction, ExtractionResult
from sociodec.models.decomposition import Decomposition, DeliverableComposition, Subproblem
from sociodec.models.prompt import Constraint, ConstraintKind, Interpretation, Prompt, Requirement, RequirementType, SourceSpan
from sociodec.orchestrator import StrategyOutcome
from sociodec.providers.base import GenerationResult
from sociodec.selector import PlanItem
from sociodec.validation import HypothesisVerdict
from sociodec.provider_campaign import (
    CampaignPolicy, ProviderBackedTrialAdapter, ProviderInitialDrafter,
    provider_extraction_runner,
)


TEXT = "Create a report."
REQ = Requirement("Create a report", RequirementType.DELIVERABLE, "report", SourceSpan(0, 16))
HARD = Constraint("Must be accessible", ConstraintKind.HARD)
PROMPT = Prompt(TEXT, Interpretation("Create a report", (HARD,), (), ("Report",)))


def _decomp():
    return Decomposition(
        (Subproblem("s1", "Create report", (), "Report", (), (REQ,)),),
        (), (DeliverableComposition("Report", ("s1",)),),
    )


class FakeProvider:
    provider_name = "fake"
    model_name = "fake-model"

    def __init__(self, content):
        self.content = content
        self.calls = 0

    def generate(self, messages, config=None):
        self.calls += 1
        return GenerationResult(self.content, self.provider_name, self.model_name,
                                10, 20, "stop", f"req-{self.calls}")


def _candidate_json():
    return json.dumps({"candidate_id":"x","subproblems":[{
        "id":"s1","question":"Create report","inputs":[],"output":"Report",
        "local_constraints":[{"kind":"hard","statement":"Must be accessible"}],
        "covered_requirements":[{"type":"deliverable","domain":"report","statement":"Create a report"}]
    }],"dependencies":[],"kappa":{"Report":["s1"]}})


def test_provider_initial_drafter_keeps_two_authors_independent_and_decodes_typed_candidate():
    a, b = FakeProvider(_candidate_json()), FakeProvider(_candidate_json())
    drafter = ProviderInitialDrafter((a,b))
    extraction = AggregatedExtraction((REQ,), (), (), (), (), {}, {}, ())
    da = drafter(PROMPT, extraction, 0)
    db = drafter(PROMPT, extraction, 1)
    assert da == db == _decomp()
    assert a.calls == b.calls == 1
    assert [x.author_index for x in drafter.traces] == [0,1]
    assert drafter.traces[0].output_sha256 == drafter.traces[1].output_sha256


def test_provider_initial_drafter_rejects_bad_json():
    drafter = ProviderInitialDrafter((FakeProvider("not-json"), FakeProvider("not-json")))
    with pytest.raises(ValueError, match="invalid JSON"):
        drafter(PROMPT, AggregatedExtraction((REQ,), (), (), (), (), {}, {}, ()), 0)


def test_provider_extraction_runner_uses_q_extractors():
    class Extractor:
        def __init__(self, identifier):
            self.extractor_id = identifier
        def extract(self, text):
            assert text == TEXT
            from sociodec.extraction import ExtractionResult
            return ExtractionResult((REQ,), extractor_id=self.extractor_id)
    result = provider_extraction_runner((Extractor("a"), Extractor("b")))(PROMPT)
    assert len(result.extractor_results) == 2
    assert result.requirements == (REQ,)


class FakeExecutor:
    executor_id = "executor-v1"
    def execute(self, prompt, decomposition, *, seed):
        return ExecutionRun(
            self.executor_id,
            (SubproblemExecution("s1", ExecutionStatus.SOLVED, "Report"),),
            "Accessible report",
            (ConstraintAssessment(HARD, True, "Verified"),),
        )


def test_end_to_end_trial_adapter_runs_orchestrator_and_fixed_executor():
    extraction = AggregatedExtraction((REQ,), (), (), (), (), {}, {},
                                      (ExtractionResult((REQ,), extractor_id="e1"),))
    def extract(_prompt):
        return extraction
    draft_calls = []
    def draft(prompt, extraction, author_index):
        draft_calls.append(author_index)
        return _decomp()
    def strategy(item, prompt, extraction, initial, seed, available):
        return StrategyOutcome(_decomp(), 0, strategy_run_id=f"{item.value}:fake")
    adapter = ProviderBackedTrialAdapter(
        prompt_factory=lambda example: PROMPT,
        extract=extract, draft=draft, execute_strategy=strategy,
        executor=FakeExecutor(), expected_executor_id="executor-v1",
        policy=CampaignPolicy(call_budget=20, high_stakes=True),
        trace_supplier=lambda: ({"provider":"fake","model":"m"},),
    )
    config = ExperimentConfig("E1","demo",("family-a",),"executor-v1",("S8",),repeats=1)
    context = TrialContext(config, BenchmarkPrompt("demo","p1",TEXT), 0, 17)
    outcome = adapter(context)
    assert isinstance(outcome, TrialOutcome)
    assert draft_calls == [0,1]
    assert outcome.metrics["fully_valid"] == 1.0
    assert outcome.metrics["v3_solvability"] == 1.0
    assert outcome.metrics["v4_faithfulness"] == 1.0
    assert outcome.metrics["orchestration_calls"] > 0
    assert outcome.metadata["executor_id"] == "executor-v1"
    assert outcome.metadata["trace_count"] == 1
    assert outcome.metadata["strategies_executed"]


def test_prompt_factory_must_preserve_benchmark_text():
    extraction = AggregatedExtraction((REQ,), (), (), (), (), {}, {},
                                      (ExtractionResult((REQ,), extractor_id="e1"),))
    adapter = ProviderBackedTrialAdapter(
        prompt_factory=lambda example: Prompt("different", PROMPT.interpretation),
        extract=lambda _: extraction, draft=lambda *args: _decomp(),
        execute_strategy=lambda *args: StrategyOutcome(_decomp(), 0),
        executor=FakeExecutor(), expected_executor_id="executor-v1",
        policy=CampaignPolicy(call_budget=20),
    )
    config = ExperimentConfig("E1","demo",("family-a",),"executor-v1",("S2",),repeats=1)
    with pytest.raises(ValueError, match="preserve the exact"):
        adapter(TrialContext(config, BenchmarkPrompt("demo","p1",TEXT), 0, 17))


def test_policy_rejects_zero_budget():
    with pytest.raises(ValueError):
        CampaignPolicy(call_budget=0)
