"""Decomposition domain model.

Scientific basis: Definitions 4 and 5 in "Societies of Decomposers:
Social and Organisational Strategies for LLM-Based Prompt Decomposition".

This module represents D=(S,E,kappa). It validates local representation
integrity and references, but deliberately does not decide V1 coverage,
V2 acyclicity, V3 executor solvability, V4 faithfulness or V5 validity.
Those checks belong to the subsequent validation core.
"""
from __future__ import annotations

from dataclasses import dataclass

from .prompt import Constraint, Prompt, Requirement


@dataclass(frozen=True, slots=True)
class Subproblem:
    """s=(q_s, ins, outs, C_s), with requirement coverage metadata."""

    identifier: str
    question: str
    inputs: tuple[str, ...]
    output: str
    local_constraints: tuple[Constraint, ...] = ()
    covered_requirements: tuple[Requirement, ...] = ()

    def __post_init__(self) -> None:
        if not self.identifier.strip():
            raise ValueError("Subproblem.identifier must not be empty")
        if not self.question.strip():
            raise ValueError("Subproblem.question must not be empty")
        if not self.output.strip():
            raise ValueError("Subproblem.output must not be empty")
        if any(not item.strip() for item in self.inputs):
            raise ValueError("Subproblem.inputs must not contain empty values")
        if len(set(self.inputs)) != len(self.inputs):
            raise ValueError("Subproblem.inputs must be unique")
        if len(set(self.local_constraints)) != len(self.local_constraints):
            raise ValueError("Subproblem.local_constraints must be unique")
        if len(set(self.covered_requirements)) != len(self.covered_requirements):
            raise ValueError("Subproblem.covered_requirements must be unique")

    @property
    def cov(self) -> frozenset[Requirement]:
        """The requirements covered by this subproblem, cov(s)."""
        return frozenset(self.covered_requirements)


@dataclass(frozen=True, slots=True)
class Dependency:
    """A directed dependency (source, target): target inputs use source output."""

    source_id: str
    target_id: str

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("Dependency.source_id must not be empty")
        if not self.target_id.strip():
            raise ValueError("Dependency.target_id must not be empty")

    @property
    def pair(self) -> tuple[str, str]:
        return (self.source_id, self.target_id)


@dataclass(frozen=True, slots=True)
class DeliverableComposition:
    """One κ(o) entry: the subproblems contributing to deliverable o."""

    deliverable: str
    contributor_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.deliverable.strip():
            raise ValueError("DeliverableComposition.deliverable must not be empty")
        if any(not item.strip() for item in self.contributor_ids):
            raise ValueError("DeliverableComposition.contributor_ids must not contain empty values")
        if len(set(self.contributor_ids)) != len(self.contributor_ids):
            raise ValueError("DeliverableComposition.contributor_ids must be unique")

    @property
    def contributors(self) -> frozenset[str]:
        return frozenset(self.contributor_ids)


@dataclass(frozen=True, slots=True)
class Decomposition:
    """D=(S,E,kappa), with explicit requirement coverage cov(D)."""

    subproblems: tuple[Subproblem, ...]
    dependencies: tuple[Dependency, ...]
    composition: tuple[DeliverableComposition, ...]

    def __post_init__(self) -> None:
        identifiers = [item.identifier for item in self.subproblems]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Decomposition.subproblems must have unique identifiers")

        dependency_pairs = [edge.pair for edge in self.dependencies]
        if len(dependency_pairs) != len(set(dependency_pairs)):
            raise ValueError("Decomposition.dependencies must not contain duplicate edges")

        deliverables = [item.deliverable for item in self.composition]
        if len(deliverables) != len(set(deliverables)):
            raise ValueError("Decomposition.composition must have unique deliverable keys")

        known_ids = set(identifiers)
        for edge in self.dependencies:
            if edge.source_id not in known_ids:
                raise ValueError(f"Dependency source does not exist: {edge.source_id}")
            if edge.target_id not in known_ids:
                raise ValueError(f"Dependency target does not exist: {edge.target_id}")
        for entry in self.composition:
            unknown = entry.contributors - known_ids
            if unknown:
                raise ValueError(
                    "Composition references unknown subproblem(s): "
                    + ", ".join(sorted(unknown))
                )

    @property
    def S(self) -> frozenset[Subproblem]:
        """Paper notation: the set of subproblems S."""
        return frozenset(self.subproblems)

    @property
    def E(self) -> frozenset[tuple[str, str]]:
        """Paper notation: directed dependency relation E."""
        return frozenset(edge.pair for edge in self.dependencies)

    @property
    def kappa(self) -> dict[str, frozenset[str]]:
        """Read-only-by-convention materialisation of the κ composition map."""
        return {entry.deliverable: entry.contributors for entry in self.composition}

    @property
    def cov(self) -> frozenset[Requirement]:
        """cov(D) = union of cov(s) over all subproblems."""
        return frozenset(
            requirement
            for subproblem in self.subproblems
            for requirement in subproblem.covered_requirements
        )

    def validate_against(
        self,
        prompt: Prompt,
        requirements: tuple[Requirement, ...],
    ) -> None:
        """Validate prompt-relative references, not decomposition validity.

        Ensures local constraints are drawn from C and coverage labels refer
        to the supplied explicit requirement universe. It intentionally does
        not enforce complete coverage, DAG structure or non-empty κ(o).
        """
        allowed_constraints = set(prompt.iota.constraints)
        allowed_requirements = set(requirements)

        for subproblem in self.subproblems:
            invalid_constraints = set(subproblem.local_constraints) - allowed_constraints
            if invalid_constraints:
                raise ValueError(
                    f"Subproblem {subproblem.identifier} uses constraints outside prompt C"
                )
            invalid_requirements = set(subproblem.covered_requirements) - allowed_requirements
            if invalid_requirements:
                raise ValueError(
                    f"Subproblem {subproblem.identifier} covers requirements outside R(P)"
                )

        declared_deliverables = set(prompt.iota.deliverables)
        mapped_deliverables = set(self.kappa)
        unknown_deliverables = mapped_deliverables - declared_deliverables
        if unknown_deliverables:
            raise ValueError(
                "Composition contains undeclared deliverable(s): "
                + ", ".join(sorted(unknown_deliverables))
            )
