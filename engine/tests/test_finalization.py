from sociodec.execution import ExecutionRun, ExecutionStatus, SubproblemExecution
from sociodec.extraction import ExtractionResult, Hypothesis, aggregate_extractions
from sociodec.finalization import finalize_adaptive_result
from sociodec.models.decomposition import Decomposition, DeliverableComposition, Subproblem
from sociodec.models.prompt import Interpretation, Prompt, Requirement, RequirementType, SourceSpan
from sociodec.orchestrator import StrategyOutcome, run_adaptive
from sociodec.selector import PlanItem
from sociodec.validation import HypothesisVerdict, HypothesisVerdictValue


def _case():
    text = "Create a plan now."
    requirement = Requirement("Create a plan now", RequirementType.TARGET, "planning", SourceSpan(0, len(text)))
    prompt = Prompt(text, Interpretation("Create a plan", deliverables=("Plan",)))
    hypothesis = Hypothesis("Maintain an audit trail", RequirementType.CONSTRAINT, "compliance")
    confirmed = Requirement(hypothesis.statement, hypothesis.type, hypothesis.domain)
    subproblem = Subproblem("s1", "Prepare plan and audit trail", (), "Plan output", (), (requirement, confirmed))
    decomposition = Decomposition((subproblem,), (), (DeliverableComposition("Plan", ("s1",)),))
    extraction = aggregate_extractions((ExtractionResult(requirements=(requirement,), hypotheses=(hypothesis,), extractor_id="e1"),))
    return prompt, extraction, hypothesis, decomposition


def test_finalizer_keeps_v3_v4_not_evaluated_without_executor_evidence():
    prompt, extraction, _, decomposition = _case()
    initial = Decomposition(
        (Subproblem("s1", "Prepare plan", (), "Plan output", (), decomposition.subproblems[0].covered_requirements[:1]),),
        (), (DeliverableComposition("Plan", ("s1",)),),
    )
    result = run_adaptive(
        prompt, extract=lambda _: extraction,
        draft=lambda p, e, i: initial,
        execute_strategy=lambda *args: StrategyOutcome(decomposition, 10),
        budget=20, high_stakes=False, model_families=1, open_prompt=True,
    )
    final = finalize_adaptive_result(result)
    assert final.structural.v1_coverage.status.value == "pass"
    assert final.structural.v2_acyclicity.status.value == "pass"
    assert final.structural.v5_composition.status.value == "pass"
    assert final.structural.v3_solvability.status.value == "not_evaluated"
    assert final.structural.v4_faithfulness.status.value == "not_evaluated"
    assert final.execution is None
    assert final.fully_valid is None


def test_finalizer_uses_winning_hypothesis_verdict_and_execution_evidence():
    prompt, extraction, hypothesis, decomposition = _case()

    def execute(item, prompt, extracted, drafts, seed, available):
        assert item is PlanItem.C8_BRAINSTORM_THEN_REVIEW
        return StrategyOutcome(
            decomposition, 10,
            hypothesis_verdicts=(HypothesisVerdict(hypothesis, HypothesisVerdictValue.CONFIRMED),),
            candidate_support_counts=(),
            strategy_run_id="confirmed-run",
        )

    initial = Decomposition(
        (Subproblem("s1", "Prepare plan", (), "Plan output", (), (extraction.requirements[0],)),),
        (), (DeliverableComposition("Plan", ("s1",)),),
    )
    result = run_adaptive(
        prompt, extract=lambda _: extraction,
        draft=lambda p, e, i: initial,
        execute_strategy=execute,
        budget=20, high_stakes=False, model_families=1, open_prompt=True,
    )
    assert result.best_strategy_run_id == "confirmed-run"
    assert result.best_hypothesis_verdicts == (
        HypothesisVerdict(hypothesis, HypothesisVerdictValue.CONFIRMED),
    )
    run = ExecutionRun(
        "mock-executor",
        (SubproblemExecution("s1", ExecutionStatus.SOLVED, "completed plan"),),
        "completed plan",
        (),
    )
    final = finalize_adaptive_result(result, execution_run=run)
    assert final.structural.hypothesis_verdicts.status.value == "pass"
    assert final.structural.v1_coverage.status.value == "pass"
    assert final.execution.v3_solvability.status.value == "pass"
    assert final.execution.v4_faithfulness.status.value == "pass"
    assert final.fully_valid is True
