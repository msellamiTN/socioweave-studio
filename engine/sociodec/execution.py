"""Execution evidence model for Definition 6 conditions V3 and V4.

This is an engineering realisation of the paper's executor M contract. It
records executor outputs, consumed predecessor answers, composed answers and
hard-constraint assessments. The validator checks evidence completeness and
consistency; it cannot independently prove that a natural-language answer
satisfies a constraint.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sociodec.models.decomposition import Decomposition
from sociodec.models.prompt import Constraint, Prompt
from sociodec.validation import (
    CheckResult,
    CheckStatus,
    ValidationFinding,
    ValidationReport,
)


class ExecutionStatus(StrEnum):
    SOLVED = "solved"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PredecessorAnswer:
    subproblem_id: str
    answer: str

    def __post_init__(self) -> None:
        if not self.subproblem_id.strip():
            raise ValueError("PredecessorAnswer.subproblem_id must not be empty")
        if not self.answer.strip():
            raise ValueError("PredecessorAnswer.answer must not be empty")


@dataclass(frozen=True, slots=True)
class SubproblemExecution:
    subproblem_id: str
    status: ExecutionStatus
    answer: str | None
    predecessor_answers: tuple[PredecessorAnswer, ...] = ()
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.subproblem_id.strip():
            raise ValueError("SubproblemExecution.subproblem_id must not be empty")
        if not isinstance(self.status, ExecutionStatus):
            raise ValueError("SubproblemExecution.status must be solved or failed")
        if self.status is ExecutionStatus.SOLVED and (
            self.answer is None or not self.answer.strip()
        ):
            raise ValueError("A solved subproblem must have a non-empty answer")
        if self.status is ExecutionStatus.FAILED and self.answer is not None:
            raise ValueError("A failed subproblem must not expose a successful answer")
        predecessor_ids = [item.subproblem_id for item in self.predecessor_answers]
        if len(predecessor_ids) != len(set(predecessor_ids)):
            raise ValueError("predecessor_answers must have unique subproblem identifiers")


@dataclass(frozen=True, slots=True)
class ConstraintAssessment:
    constraint: Constraint
    satisfied: bool
    evidence: str

    def __post_init__(self) -> None:
        if not isinstance(self.satisfied, bool):
            raise ValueError("ConstraintAssessment.satisfied must be a boolean")
        if not self.evidence.strip():
            raise ValueError("ConstraintAssessment.evidence must not be empty")


@dataclass(frozen=True, slots=True)
class ExecutionRun:
    executor_id: str
    executions: tuple[SubproblemExecution, ...]
    composed_answer: str
    constraint_assessments: tuple[ConstraintAssessment, ...]

    def __post_init__(self) -> None:
        if not self.executor_id.strip():
            raise ValueError("ExecutionRun.executor_id must not be empty")
        if not self.composed_answer.strip():
            raise ValueError("ExecutionRun.composed_answer must not be empty")
        identifiers = [item.subproblem_id for item in self.executions]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("ExecutionRun.executions must have unique subproblem identifiers")
        constraints = [item.constraint for item in self.constraint_assessments]
        if len(constraints) != len(set(constraints)):
            raise ValueError("Constraint assessments must be unique per constraint")


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    v3_solvability: CheckResult
    v4_faithfulness: CheckResult
    executor_id: str

    @property
    def execution_valid(self) -> bool:
        return (
            self.v3_solvability.status is CheckStatus.PASS
            and self.v4_faithfulness.status is CheckStatus.PASS
        )


@dataclass(frozen=True, slots=True)
class FullValidityReport:
    structural: ValidationReport
    execution: ExecutionReport

    @property
    def fully_valid(self) -> bool:
        return self.structural.structural_valid and self.execution.execution_valid


def assess_execution(
    prompt: Prompt,
    decomposition: Decomposition,
    run: ExecutionRun,
) -> ExecutionReport:
    """Assess V3/V4 from an executor's recorded evidence.

    Execution records must follow a topological order. For every dependency
    u→v, v must record the exact answer produced by u as a predecessor input.
    V4 requires one evidence-bearing assessment for every hard constraint.
    """
    findings_v3: list[ValidationFinding] = []
    expected_ids = {item.identifier for item in decomposition.subproblems}
    record_by_id = {item.subproblem_id: item for item in run.executions}
    order = {item.subproblem_id: index for index, item in enumerate(run.executions)}

    unknown_records = set(record_by_id) - expected_ids
    for identifier in sorted(unknown_records):
        findings_v3.append(ValidationFinding(
            "unknown_execution_subproblem",
            "Execution contains a subproblem not present in the decomposition.",
            (identifier,),
        ))

    missing_records = expected_ids - set(record_by_id)
    for identifier in sorted(missing_records):
        findings_v3.append(ValidationFinding(
            "missing_execution_record",
            "No executor result was recorded for this subproblem.",
            (identifier,),
        ))

    incoming: dict[str, set[str]] = {identifier: set() for identifier in expected_ids}
    for source, target in decomposition.E:
        incoming[target].add(source)

    for identifier, record in record_by_id.items():
        if identifier not in expected_ids:
            continue
        if record.status is ExecutionStatus.FAILED:
            findings_v3.append(ValidationFinding(
                "subproblem_execution_failed",
                record.error or "Executor did not solve this subproblem.",
                (identifier,),
            ))
            continue
        if record.answer is None or not record.answer.strip():
            findings_v3.append(ValidationFinding(
                "missing_subproblem_answer",
                "A solved subproblem must provide a non-empty answer.",
                (identifier,),
            ))
            continue

        supplied = {item.subproblem_id: item.answer for item in record.predecessor_answers}
        expected_predecessors = incoming[identifier]
        for predecessor_id in sorted(expected_predecessors - set(supplied)):
            findings_v3.append(ValidationFinding(
                "missing_predecessor_answer",
                "The subproblem did not record an answer from a required predecessor.",
                (identifier, predecessor_id),
            ))
        for predecessor_id in sorted(set(supplied) - expected_predecessors):
            findings_v3.append(ValidationFinding(
                "unexpected_predecessor_answer",
                "The subproblem recorded an answer from a non-predecessor.",
                (identifier, predecessor_id),
            ))
        for predecessor_id in sorted(expected_predecessors & set(supplied)):
            predecessor = record_by_id.get(predecessor_id)
            if predecessor is None or predecessor.status is not ExecutionStatus.SOLVED:
                findings_v3.append(ValidationFinding(
                    "predecessor_not_solved",
                    "A required predecessor has no successful execution result.",
                    (identifier, predecessor_id),
                ))
            elif predecessor.answer != supplied[predecessor_id]:
                findings_v3.append(ValidationFinding(
                    "predecessor_answer_mismatch",
                    "The consumed predecessor answer differs from its recorded output.",
                    (identifier, predecessor_id),
                ))
            elif order.get(predecessor_id, len(order)) >= order.get(identifier, -1):
                findings_v3.append(ValidationFinding(
                    "execution_order_violation",
                    "A subproblem was executed before one of its predecessors.",
                    (identifier, predecessor_id),
                ))

    findings_v4: list[ValidationFinding] = []
    hard_constraints = set(prompt.iota.hard_constraints)
    assessments = {item.constraint: item for item in run.constraint_assessments}
    unknown_assessments = set(assessments) - hard_constraints
    for constraint in unknown_assessments:
        findings_v4.append(ValidationFinding(
            "assessment_for_non_hard_constraint",
            "Faithfulness assessment refers to a constraint outside the prompt's hard constraints.",
            (constraint.statement,),
        ))
    missing_assessments = hard_constraints - set(assessments)
    for constraint in missing_assessments:
        findings_v4.append(ValidationFinding(
            "missing_hard_constraint_assessment",
            "No faithfulness assessment was supplied for this hard constraint.",
            (constraint.statement,),
        ))
    for constraint in hard_constraints & set(assessments):
        assessment = assessments[constraint]
        if not assessment.satisfied:
            findings_v4.append(ValidationFinding(
                "hard_constraint_violated",
                "The composed answer was assessed as violating a hard constraint.",
                (constraint.statement, assessment.evidence),
            ))

    return ExecutionReport(
        v3_solvability=CheckResult(
            "Executor solves each subproblem using predecessor answers",
            CheckStatus.FAIL if findings_v3 else CheckStatus.PASS,
            tuple(findings_v3),
        ),
        v4_faithfulness=CheckResult(
            "Composed answer satisfies every hard constraint",
            CheckStatus.FAIL if findings_v4 else CheckStatus.PASS,
            tuple(findings_v4),
        ),
        executor_id=run.executor_id,
    )


def combine_validity(
    structural: ValidationReport,
    execution: ExecutionReport,
) -> FullValidityReport:
    """Combine structural V1/V2/V5 and execution V3/V4 evidence."""
    return FullValidityReport(structural=structural, execution=execution)
