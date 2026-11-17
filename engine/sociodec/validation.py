"""Paper-aligned structural validation for decompositions.

Scientific basis: Definition 6 (V1--V5) and the final check/repair phase
of Algorithm 1. V1, V2 and V5 are programmatically checked here.
V3 and V4 require an executor and composed answer, so they are explicitly
reported as not evaluated by this structural validator.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from sociodec.extraction import Hypothesis
from sociodec.models.decomposition import Decomposition
from sociodec.models.prompt import Prompt, Requirement


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_EVALUATED = "not_evaluated"


class HypothesisVerdictValue(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class HypothesisVerdict:
    hypothesis: Hypothesis
    verdict: HypothesisVerdictValue

    def __post_init__(self) -> None:
        if not isinstance(self.verdict, HypothesisVerdictValue):
            raise ValueError("Hypothesis verdict must be confirmed or rejected")


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    code: str
    message: str
    subjects: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CheckResult:
    condition: str
    status: CheckStatus
    findings: tuple[ValidationFinding, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationReport:
    v1_coverage: CheckResult
    v2_acyclicity: CheckResult
    v3_solvability: CheckResult
    v4_faithfulness: CheckResult
    v5_composition: CheckResult
    hypothesis_verdicts: CheckResult
    effective_requirements: tuple[Requirement, ...]

    @property
    def structural_valid(self) -> bool:
        return all(
            check.status is CheckStatus.PASS
            for check in (self.v1_coverage, self.v2_acyclicity, self.v5_composition)
        ) and self.hypothesis_verdicts.status is CheckStatus.PASS

    @property
    def execution_evaluated(self) -> bool:
        return (
            self.v3_solvability.status is not CheckStatus.NOT_EVALUATED
            and self.v4_faithfulness.status is not CheckStatus.NOT_EVALUATED
        )

    @property
    def failures(self) -> tuple[ValidationFinding, ...]:
        checks = (
            self.v1_coverage,
            self.v2_acyclicity,
            self.v5_composition,
            self.hypothesis_verdicts,
        )
        return tuple(finding for check in checks for finding in check.findings)


def find_directed_cycle(
    identifiers: tuple[str, ...], edges: frozenset[tuple[str, str]]
) -> tuple[str, ...] | None:
    """Return one directed cycle as node sequence, repeating its first node."""
    graph: dict[str, list[str]] = defaultdict(list)
    for source, target in edges:
        graph[source].append(target)

    state = {node: 0 for node in identifiers}  # 0 unseen, 1 active, 2 done
    stack: list[str] = []
    positions: dict[str, int] = {}

    def visit(node: str) -> tuple[str, ...] | None:
        state[node] = 1
        positions[node] = len(stack)
        stack.append(node)
        for neighbour in graph[node]:
            if state[neighbour] == 0:
                found = visit(neighbour)
                if found:
                    return found
            elif state[neighbour] == 1:
                start = positions[neighbour]
                return tuple(stack[start:] + [neighbour])
        stack.pop()
        positions.pop(node)
        state[node] = 2
        return None

    for node in identifiers:
        graph[node].sort()
        if state[node] == 0:
            found = visit(node)
            if found:
                return found
    return None


def validate_decomposition(
    prompt: Prompt,
    requirements: tuple[Requirement, ...],
    decomposition: Decomposition,
    *,
    hypotheses: tuple[Hypothesis, ...] = (),
    verdicts: tuple[HypothesisVerdict, ...] = (),
) -> ValidationReport:
    """Check V1, V2, V5 and Algorithm 1 hypothesis verdict completeness.

    `requirements` is the explicit requirement universe R(P), usually the
    aggregated explicit extraction. Confirmed hypotheses are converted to
    spanless Requirement values and added to the effective coverage universe,
    as required by the paper. Rejected hypotheses are not added.

    This function does not execute subproblems or compose an answer. V3 and
    V4 are consequently NOT_EVALUATED, never silently treated as passing.
    """
    verdict_by_hypothesis: dict[Hypothesis, HypothesisVerdictValue] = {}
    verdict_findings: list[ValidationFinding] = []
    for item in verdicts:
        if item.hypothesis not in hypotheses:
            verdict_findings.append(ValidationFinding(
                "unknown_hypothesis_verdict",
                "A verdict was supplied for a hypothesis outside the input set.",
                (item.hypothesis.statement,),
            ))
            continue
        if item.hypothesis in verdict_by_hypothesis:
            verdict_findings.append(ValidationFinding(
                "duplicate_hypothesis_verdict",
                "A hypothesis has more than one verdict.",
                (item.hypothesis.statement,),
            ))
            continue
        verdict_by_hypothesis[item.hypothesis] = item.verdict

    for hypothesis in hypotheses:
        if hypothesis not in verdict_by_hypothesis:
            verdict_findings.append(ValidationFinding(
                "missing_hypothesis_verdict",
                "Every extracted hypothesis must be confirmed or rejected.",
                (hypothesis.statement,),
            ))

    confirmed = tuple(
        Requirement(
            statement=h.statement,
            type=h.type,
            domain=h.domain,
            source_span=None,
            entity_names=h.entity_names,
        )
        for h in hypotheses
        if verdict_by_hypothesis.get(h) is HypothesisVerdictValue.CONFIRMED
    )
    effective = tuple(dict.fromkeys((*requirements, *confirmed)))
    decomposition.validate_against(prompt, effective)

    covered = decomposition.cov
    required = frozenset(effective)
    missing = required - covered
    extra = covered - required
    coverage_findings: list[ValidationFinding] = []
    if missing:
        coverage_findings.append(ValidationFinding(
            "uncovered_requirements",
            "The decomposition does not cover every explicit and confirmed requirement.",
            tuple(sorted(item.statement for item in missing)),
        ))
    if extra:
        coverage_findings.append(ValidationFinding(
            "coverage_outside_requirement_set",
            "The decomposition covers items outside the effective requirement set.",
            tuple(sorted(item.statement for item in extra)),
        ))

    cycle = find_directed_cycle(
        tuple(item.identifier for item in decomposition.subproblems),
        decomposition.E,
    )
    cycle_findings = () if cycle is None else (
        ValidationFinding("dependency_cycle", "The dependency graph contains a directed cycle.", cycle),
    )

    composition_findings: list[ValidationFinding] = []
    mapping = decomposition.kappa
    for deliverable in prompt.iota.deliverables:
        contributors = mapping[deliverable]
        if not contributors:
            composition_findings.append(ValidationFinding(
                "unowned_deliverable",
                "A declared deliverable has no contributing subproblem.",
                (deliverable,),
            ))

    contributed = frozenset(
        contributor for contributors in mapping.values() for contributor in contributors
    )
    sinks = tuple(
        item.identifier
        for item in decomposition.subproblems
        if not any(source == item.identifier for source, _ in decomposition.E)
    )
    dead_ends = tuple(identifier for identifier in sinks if identifier not in contributed)
    if dead_ends:
        composition_findings.append(ValidationFinding(
            "sink_without_deliverable",
            "Every sink subproblem must contribute to at least one deliverable.",
            dead_ends,
        ))

    return ValidationReport(
        v1_coverage=CheckResult(
            "cov(D) = R(P), extended by confirmed hypotheses",
            CheckStatus.FAIL if coverage_findings else CheckStatus.PASS,
            tuple(coverage_findings),
        ),
        v2_acyclicity=CheckResult(
            "(S, E) is a directed acyclic graph",
            CheckStatus.FAIL if cycle_findings else CheckStatus.PASS,
            cycle_findings,
        ),
        v3_solvability=CheckResult(
            "Executor M solves each subproblem using predecessor answers",
            CheckStatus.NOT_EVALUATED,
        ),
        v4_faithfulness=CheckResult(
            "The composed answer satisfies all hard constraints",
            CheckStatus.NOT_EVALUATED,
        ),
        v5_composition=CheckResult(
            "Every deliverable has contributors and every sink contributes",
            CheckStatus.FAIL if composition_findings else CheckStatus.PASS,
            tuple(composition_findings),
        ),
        hypothesis_verdicts=CheckResult(
            "Every extracted hypothesis has exactly one verdict",
            CheckStatus.FAIL if verdict_findings else CheckStatus.PASS,
            tuple(verdict_findings),
        ),
        effective_requirements=effective,
    )
