"""Algorithm 1 final validation and bounded repair adapter."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Sequence
from sociodec.models.decomposition import Decomposition
from sociodec.models.prompt import Prompt, Requirement
from sociodec.validation import HypothesisVerdict, ValidationReport, find_directed_cycle, validate_decomposition
from sociodec.extraction import Hypothesis

@dataclass(frozen=True, slots=True)
class Algorithm1Result:
    decomposition: Decomposition
    report: ValidationReport
    repair_calls: int
    removed_cycle_edges: tuple[tuple[str, str], ...]

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(f"{f.code}: {f.message}" for f in self.report.failures)

Repair = Callable[[Decomposition, ValidationReport], Decomposition]

class Algorithm1CheckRepairAdapter:
    """V1/V2/V5 check, deterministic cycle removal, one optional repair, re-check."""
    def __init__(
        self, *, prompt: Prompt, requirements: tuple[Requirement, ...],
        hypotheses: tuple[Hypothesis, ...] = (),
        verdicts: tuple[HypothesisVerdict, ...] = (),
        candidate_decompositions: Sequence[Decomposition] = (),
        repair: Repair | None = None,
    ) -> None:
        self.prompt = prompt
        self.requirements = requirements
        self.hypotheses = hypotheses
        self.verdicts = verdicts
        self.candidates = tuple(candidate_decompositions)
        self.repair = repair

    def _check(self, decomposition: Decomposition) -> ValidationReport:
        return validate_decomposition(
            self.prompt, self.requirements, decomposition,
            hypotheses=self.hypotheses, verdicts=self.verdicts,
        )

    def _edge_support(self, edge: tuple[str, str]) -> int:
        return sum(edge in candidate.E for candidate in self.candidates)

    def _break_all_cycles(self, decomposition: Decomposition):
        current = decomposition
        removed: list[tuple[str, str]] = []
        identifiers = tuple(item.identifier for item in current.subproblems)
        while True:
            cycle = find_directed_cycle(identifiers, current.E)
            if cycle is None:
                break
            cycle_edges = tuple(zip(cycle, cycle[1:]))
            # Fewest supporting candidates; lexical tie-break makes it deterministic.
            selected = min(cycle_edges, key=lambda edge: (self._edge_support(edge), edge))
            current = Decomposition(
                current.subproblems,
                tuple(edge for edge in current.dependencies if edge.pair != selected),
                current.composition,
            )
            removed.append(selected)
        return current, tuple(removed)

    def run(self, decomposition: Decomposition) -> Algorithm1Result:
        report = self._check(decomposition)
        current = decomposition
        removed: tuple[tuple[str, str], ...] = ()
        if report.v2_acyclicity.findings:
            current, removed = self._break_all_cycles(current)
            report = self._check(current)

        non_cycle_failures = tuple(
            finding for finding in report.failures
            if finding.code != "dependency_cycle"
        )
        repair_calls = 0
        if non_cycle_failures and self.repair is not None:
            current = self.repair(current, report)
            repair_calls = 1
            report = self._check(current)
        return Algorithm1Result(current, report, repair_calls, removed)
