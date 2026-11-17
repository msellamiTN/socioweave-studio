import pytest

from sociodec.execution import (
    ConstraintAssessment, ExecutionRun, ExecutionStatus, PredecessorAnswer,
    SubproblemExecution, assess_execution, combine_validity,
)
from sociodec.models.decomposition import (
    Decomposition, DeliverableComposition, Dependency, Subproblem,
)
from sociodec.models.prompt import (
    Constraint, ConstraintKind, Interpretation, Prompt, Requirement, RequirementType,
)
from sociodec.validation import CheckStatus, validate_decomposition


def fixture():
    hard = Constraint("Response time must not exceed 20 days", ConstraintKind.HARD)
    prompt = Prompt(
        "Deliver a permit service within 20 days.",
        Interpretation(
            "Deliver a permit service",
            constraints=(hard,),
            deliverables=("Service plan",),
        ),
    )
    r = Requirement("Deliver a permit service", RequirementType.DELIVERABLE, "service")
    s1 = Subproblem("s1", "Analyse service", (), "Analysis", (), (r,))
    s2 = Subproblem("s2", "Design service", ("Analysis",), "Design", (), (r,))
    d = Decomposition(
        (s1, s2), (Dependency("s1", "s2"),),
        (DeliverableComposition("Service plan", ("s2",)),),
    )
    run = ExecutionRun(
        "executor-v1",
        (
            SubproblemExecution("s1", ExecutionStatus.SOLVED, "analysis result"),
            SubproblemExecution(
                "s2", ExecutionStatus.SOLVED, "design result",
                (PredecessorAnswer("s1", "analysis result"),),
            ),
        ),
        "The service design meets the 20-day target.",
        (ConstraintAssessment(hard, True, "Verified against the service SLA."),),
    )
    return prompt, (r,), hard, d, run


def test_v3_v4_pass_with_complete_execution_and_constraint_evidence():
    prompt, _, _, d, run = fixture()
    report = assess_execution(prompt, d, run)
    assert report.v3_solvability.status is CheckStatus.PASS
    assert report.v4_faithfulness.status is CheckStatus.PASS
    assert report.execution_valid is True


def test_v3_fails_when_subproblem_execution_record_missing():
    prompt, _, _, d, run = fixture()
    incomplete = ExecutionRun(
        run.executor_id, run.executions[:1], run.composed_answer, run.constraint_assessments
    )
    report = assess_execution(prompt, d, incomplete)
    assert report.v3_solvability.status is CheckStatus.FAIL
    assert any(f.code == "missing_execution_record" for f in report.v3_solvability.findings)


def test_v3_fails_when_executor_reports_failed_subproblem():
    prompt, _, _, d, run = fixture()
    failed = ExecutionRun(
        run.executor_id,
        (
            SubproblemExecution("s1", ExecutionStatus.FAILED, None, error="Tool unavailable"),
            run.executions[1],
        ),
        run.composed_answer,
        run.constraint_assessments,
    )
    report = assess_execution(prompt, d, failed)
    assert any(f.code == "subproblem_execution_failed" for f in report.v3_solvability.findings)
    assert any(f.code == "predecessor_not_solved" for f in report.v3_solvability.findings)


def test_v3_requires_exact_predecessor_answer_and_topological_order():
    prompt, _, _, d, run = fixture()
    mismatch = ExecutionRun(
        run.executor_id,
        (
            run.executions[0],
            SubproblemExecution(
                "s2", ExecutionStatus.SOLVED, "design result",
                (PredecessorAnswer("s1", "different answer"),),
            ),
        ),
        run.composed_answer,
        run.constraint_assessments,
    )
    report = assess_execution(prompt, d, mismatch)
    assert any(f.code == "predecessor_answer_mismatch" for f in report.v3_solvability.findings)

    reversed_order = ExecutionRun(
        run.executor_id,
        (
            run.executions[1],
            run.executions[0],
        ),
        run.composed_answer,
        run.constraint_assessments,
    )
    report = assess_execution(prompt, d, reversed_order)
    assert any(f.code == "execution_order_violation" for f in report.v3_solvability.findings)


def test_v3_rejects_missing_and_unexpected_predecessor_answers():
    prompt, _, _, d, run = fixture()
    missing = ExecutionRun(
        run.executor_id,
        (run.executions[0], SubproblemExecution("s2", ExecutionStatus.SOLVED, "design")),
        run.composed_answer,
        run.constraint_assessments,
    )
    report = assess_execution(prompt, d, missing)
    assert any(f.code == "missing_predecessor_answer" for f in report.v3_solvability.findings)

    extra = ExecutionRun(
        run.executor_id,
        (
            run.executions[0],
            SubproblemExecution(
                "s2", ExecutionStatus.SOLVED, "design",
                (PredecessorAnswer("s1", "analysis result"), PredecessorAnswer("sX", "extra")),
            ),
        ),
        run.composed_answer,
        run.constraint_assessments,
    )
    report = assess_execution(prompt, d, extra)
    assert any(f.code == "unexpected_predecessor_answer" for f in report.v3_solvability.findings)


def test_v3_rejects_unknown_execution_record():
    prompt, _, _, d, run = fixture()
    unknown = ExecutionRun(
        run.executor_id,
        (*run.executions, SubproblemExecution("unknown", ExecutionStatus.SOLVED, "x")),
        run.composed_answer,
        run.constraint_assessments,
    )
    report = assess_execution(prompt, d, unknown)
    assert any(f.code == "unknown_execution_subproblem" for f in report.v3_solvability.findings)


def test_execution_models_reject_invalid_records():
    with pytest.raises(ValueError, match="non-empty answer"):
        SubproblemExecution("s", ExecutionStatus.SOLVED, "")
    with pytest.raises(ValueError, match="must not expose"):
        SubproblemExecution("s", ExecutionStatus.FAILED, "not a successful answer")
    with pytest.raises(ValueError, match="unique"):
        SubproblemExecution(
            "s", ExecutionStatus.SOLVED, "answer",
            (PredecessorAnswer("p", "a"), PredecessorAnswer("p", "b")),
        )
    with pytest.raises(ValueError, match="evidence"):
        ConstraintAssessment(
            Constraint("Hard", ConstraintKind.HARD), True, " "
        )


def test_v4_fails_when_hard_constraint_is_violated_or_unassessed():
    prompt, _, hard, d, run = fixture()
    violated = ExecutionRun(
        run.executor_id, run.executions, run.composed_answer,
        (ConstraintAssessment(hard, False, "Measured response was 28 days."),),
    )
    report = assess_execution(prompt, d, violated)
    assert report.v4_faithfulness.status is CheckStatus.FAIL
    assert report.v4_faithfulness.findings[0].code == "hard_constraint_violated"

    missing = ExecutionRun(run.executor_id, run.executions, run.composed_answer, ())
    report = assess_execution(prompt, d, missing)
    assert any(f.code == "missing_hard_constraint_assessment" for f in report.v4_faithfulness.findings)


def test_v4_rejects_assessment_for_soft_or_foreign_constraint():
    prompt, _, _, d, run = fixture()
    soft = Constraint("Prefer a simple interface", ConstraintKind.SOFT)
    invalid = ExecutionRun(
        run.executor_id, run.executions, run.composed_answer,
        (ConstraintAssessment(soft, True, "Reviewed."),),
    )
    report = assess_execution(prompt, d, invalid)
    assert any(f.code == "assessment_for_non_hard_constraint" for f in report.v4_faithfulness.findings)


def test_execution_can_be_combined_with_structural_report_for_full_validity():
    prompt, requirements, _, d, run = fixture()
    structural = validate_decomposition(prompt, requirements, d)
    execution = assess_execution(prompt, d, run)
    combined = combine_validity(structural, execution)
    assert combined.fully_valid is True


def test_execution_evidence_does_not_claim_independent_semantic_proof():
    prompt, _, _, d, run = fixture()
    report = assess_execution(prompt, d, run)
    assert report.v4_faithfulness.status is CheckStatus.PASS
    # A PASS means the supplied evaluator evidence is complete and affirmative.
    # It is not a theorem that the natural-language answer is true.
    assert report.v4_faithfulness.findings == ()


def test_execution_contract_rejects_invalid_status_and_assessment_types():
    hard = Constraint("Must be available", ConstraintKind.HARD)
    with pytest.raises(ValueError, match="status must be solved or failed"):
        SubproblemExecution("s", "solved", "answer")
    with pytest.raises(ValueError, match="satisfied must be a boolean"):
        ConstraintAssessment(hard, "yes", "Observed test evidence.")
