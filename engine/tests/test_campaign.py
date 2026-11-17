import pytest

from sociodec.execution import (
    ConstraintAssessment, ExecutionRun, ExecutionStatus, PredecessorAnswer,
    SubproblemExecution,
)
from sociodec.experiments import TrialOutcome
from sociodec.models.decomposition import (
    Decomposition, DeliverableComposition, Dependency, Subproblem,
)
from sociodec.models.prompt import (
    Constraint, ConstraintKind, Interpretation, Prompt, Requirement,
    RequirementType, SourceSpan,
)
from sociodec.orchestrator import AdaptiveResult, Diagnosis
from sociodec.validation import (
    CheckResult, CheckStatus, ValidationReport, HypothesisVerdict,
)
from sociodec.campaign import evaluate_adaptive_trial


REQ = Requirement("Create a report", RequirementType.DELIVERABLE, "report", SourceSpan(0, 16))
HARD = Constraint("Must be accessible", ConstraintKind.HARD)
PROMPT = Prompt("Create a report.", Interpretation(
    "Create a report", constraints=(HARD,), deliverables=("Report",)
))


def _decomposition():
    return Decomposition(
        (Subproblem("s1", "Create report", (), "Report", (), (REQ,)),),
        (),
        (DeliverableComposition("Report", ("s1",)),),
    )


def _adaptive():
    decomposition = _decomposition()
    passed = CheckResult("structural", CheckStatus.PASS)
    not_eval = CheckResult("not evaluated", CheckStatus.NOT_EVALUATED)
    validation = ValidationReport(
        CheckResult("coverage", CheckStatus.PASS),
        CheckResult("acyclic", CheckStatus.PASS),
        not_eval, not_eval,
        CheckResult("composition", CheckStatus.PASS),
        CheckResult("hypotheses", CheckStatus.PASS),
        (REQ,),
    )
    diagnosis = Diagnosis.__new__(Diagnosis)
    return AdaptiveResult(
        prompt=PROMPT, best=decomposition, best_validation=validation,
        best_failures=(), extraction=type("Extraction", (), {
            "requirements": (REQ,), "hypotheses": (), "extractor_results": ()
        })(),
        diagnosis=diagnosis, initial_union=decomposition,
        initial_validation=validation, strategy_records=(), strategies_not_run=(),
        calls_made=3, budget=20, events=(), terminated_reason="test",
        best_hypothesis_verdicts=(), best_candidate_support_counts=(),
        best_strategy_run_id="S2:test",
    )


class GoodExecutor:
    executor_id = "fixed-executor-v1"

    def execute(self, prompt, decomposition, *, seed):
        assert seed == 17
        return ExecutionRun(
            self.executor_id,
            (SubproblemExecution("s1", ExecutionStatus.SOLVED, "Report completed"),),
            "Accessible report completed.",
            (ConstraintAssessment(HARD, True, "Accessibility checklist passed"),),
        )


class WrongExecutor(GoodExecutor):
    executor_id = "different-executor"


def test_fixed_executor_metrics_and_finalization_include_v3_v4():
    outcome, final = evaluate_adaptive_trial(
        _adaptive(), GoodExecutor(), seed=17,
        expected_executor_id="fixed-executor-v1",
        utility_scorer=lambda prompt, answer: 0.8,
        provider_trace=({"provider": "fake"},),
    )
    assert isinstance(outcome, TrialOutcome)
    assert outcome.metrics["coverage"] == 1.0
    assert outcome.metrics["structural_valid"] == 1.0
    assert outcome.metrics["v3_solvability"] == 1.0
    assert outcome.metrics["v4_faithfulness"] == 1.0
    assert outcome.metrics["fully_valid"] == 1.0
    assert outcome.metrics["utility"] == 0.8
    assert final.fully_valid is True
    assert outcome.metadata["executor_id"] == "fixed-executor-v1"
    assert outcome.metadata["provider_trace_count"] == 1
    assert "composed_answer_sha256" in outcome.metadata


def test_executor_identity_is_fixed_and_checked_before_execution():
    with pytest.raises(ValueError, match="Executor mismatch"):
        evaluate_adaptive_trial(
            _adaptive(), WrongExecutor(), seed=1,
            expected_executor_id="fixed-executor-v1",
        )


def test_failed_execution_is_reflected_in_v3_and_fully_valid_metrics():
    class FailedExecutor(GoodExecutor):
        def execute(self, prompt, decomposition, *, seed):
            return ExecutionRun(
                self.executor_id,
                (SubproblemExecution("s1", ExecutionStatus.FAILED, None, error="tool error"),),
                "No report could be composed.",
                (ConstraintAssessment(HARD, False, "Required accessibility property absent"),),
            )
    outcome, final = evaluate_adaptive_trial(
        _adaptive(), FailedExecutor(), seed=1,
        expected_executor_id="fixed-executor-v1",
    )
    assert outcome.metrics["v3_solvability"] == 0.0
    assert outcome.metrics["v4_faithfulness"] == 0.0
    assert outcome.metrics["fully_valid"] == 0.0
    assert final.fully_valid is False


def test_utility_is_omitted_without_independent_scorer():
    outcome, _ = evaluate_adaptive_trial(
        _adaptive(), GoodExecutor(), seed=1,
        expected_executor_id="fixed-executor-v1",
    )
    assert "utility" not in outcome.metrics


def test_nonfinite_or_out_of_range_utility_is_rejected():
    for value in (float("nan"), 1.2, -0.1, True):
        with pytest.raises(ValueError, match="utility_scorer"):
            evaluate_adaptive_trial(
                _adaptive(), GoodExecutor(), seed=1,
                expected_executor_id="fixed-executor-v1",
                utility_scorer=lambda prompt, answer, v=value: v,
            )


def test_cycle_makes_depth_undefined_and_fails_closed():
    from dataclasses import replace
    cyclic = Decomposition(
        _decomposition().subproblems,
        (Dependency("s1", "s1"),),
        _decomposition().composition,
    )
    adaptive = replace(_adaptive(), best=cyclic)
    with pytest.raises(ValueError, match="cyclic"):
        evaluate_adaptive_trial(
            adaptive, GoodExecutor(), seed=1,
            expected_executor_id="fixed-executor-v1",
        )
