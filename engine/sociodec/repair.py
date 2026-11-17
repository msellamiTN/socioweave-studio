"""Structural repair phase from Algorithm 1.

Cycles are removed without model calls, one edge at a time, using candidate
support counts. Remaining non-cycle failures may be passed to one injected
repair callback. The result is always revalidated; repair is not correctness.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from sociodec.extraction import Hypothesis
from sociodec.models.decomposition import Decomposition, Dependency
from sociodec.models.prompt import Prompt, Requirement
from sociodec.validation import (
    HypothesisVerdict,
    ValidationFinding,
    ValidationReport,
    find_directed_cycle,
    validate_decomposition,
)


RepairCallback = Callable[
    [Decomposition, tuple[ValidationFinding, ...]], Decomposition
]


@dataclass(frozen=True, slots=True)
class RepairResult:
    decomposition: Decomposition
    initial_report: ValidationReport
    final_report: ValidationReport
    removed_edges: tuple[tuple[str, str], ...]
    repair_call_made: bool


def remove_least_supported_cycle_edge(
    decomposition: Decomposition,
    cycle_nodes: tuple[str, ...],
    candidate_support_counts: Mapping[tuple[str, str], int],
) -> tuple[Decomposition, tuple[str, str]]:
    """Remove the least-supported edge on a reported cycle.

    A missing support count is an error: the paper's rule depends on evidence
    from candidates, so the implementation must not invent a default count.
    Ties are broken lexicographically by (source_id, target_id), an explicit
    deterministic engineering convention because the paper leaves ties open.
    """
    if len(cycle_nodes) < 2 or cycle_nodes[0] != cycle_nodes[-1]:
        raise ValueError("cycle_nodes must describe a closed directed cycle")
    cycle_edges = tuple(zip(cycle_nodes[:-1], cycle_nodes[1:]))
    if not cycle_edges:
        raise ValueError("cycle_nodes must contain at least one edge")

    known_edges = decomposition.E
    for edge in cycle_edges:
        if edge not in known_edges:
            raise ValueError(f"Cycle references an edge absent from decomposition: {edge}")
        if edge not in candidate_support_counts:
            raise ValueError(f"Missing candidate support count for cycle edge: {edge}")
        count = candidate_support_counts[edge]
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(f"Candidate support count must be a non-negative integer: {edge}")

    selected = min(cycle_edges, key=lambda edge: (candidate_support_counts[edge], edge))
    revised = Decomposition(
        subproblems=decomposition.subproblems,
        dependencies=tuple(
            edge for edge in decomposition.dependencies if edge.pair != selected
        ),
        composition=decomposition.composition,
    )
    return revised, selected


def repair_decomposition(
    prompt: Prompt,
    requirements: tuple[Requirement, ...],
    decomposition: Decomposition,
    candidate_support_counts: Mapping[tuple[str, str], int],
    *,
    hypotheses: tuple[Hypothesis, ...] = (),
    verdicts: tuple[HypothesisVerdict, ...] = (),
    repair_callback: RepairCallback | None = None,
) -> RepairResult:
    """Apply Algorithm 1's cycle rule and at most one non-cycle repair call."""
    initial = validate_decomposition(
        prompt, requirements, decomposition,
        hypotheses=hypotheses, verdicts=verdicts,
    )
    current = decomposition
    removed: list[tuple[str, str]] = []

    while True:
        cycle = find_directed_cycle(
            tuple(item.identifier for item in current.subproblems), current.E
        )
        if cycle is None:
            break
        current, edge = remove_least_supported_cycle_edge(
            current, cycle, candidate_support_counts
        )
        removed.append(edge)

    after_cycle_repair = validate_decomposition(
        prompt, requirements, current,
        hypotheses=hypotheses, verdicts=verdicts,
    )
    repair_call_made = False
    non_cycle_failures = tuple(
        finding for finding in after_cycle_repair.failures
        if finding.code != "dependency_cycle"
    )
    if non_cycle_failures and repair_callback is not None:
        repaired = repair_callback(current, non_cycle_failures)
        if not isinstance(repaired, Decomposition):
            raise TypeError("repair_callback must return a Decomposition")
        current = repaired
        repair_call_made = True

    final = validate_decomposition(
        prompt, requirements, current,
        hypotheses=hypotheses, verdicts=verdicts,
    )
    return RepairResult(
        decomposition=current,
        initial_report=initial,
        final_report=final,
        removed_edges=tuple(removed),
        repair_call_made=repair_call_made,
    )
