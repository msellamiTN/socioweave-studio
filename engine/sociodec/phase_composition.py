"""Typed phase-composition contract for Definition 11 and Algorithm 3.

This module validates composition structure before execution. It does not
pretend that a typed plan is a completed C1 execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


class PhaseKind(StrEnum):
    GENERATION = "gen"
    EXAMINATION = "exa"
    REVISION = "rev"
    DECISION = "dec"


class PhaseValue(StrEnum):
    PROMPT = "prompt"
    CANDIDATE_SET = "candidate_set"
    OBJECTIONS = "objections"
    DECOMPOSITION = "decomposition"


@dataclass(frozen=True, slots=True)
class CandidateState:
    """Definition 11 candidate attributes: cardinality and independence."""
    size: int
    independent: bool

    def __post_init__(self) -> None:
        if self.size < 1:
            raise ValueError("Candidate set size must be positive")
        if not isinstance(self.independent, bool):
            raise ValueError("independent must be boolean")


@dataclass(frozen=True, slots=True)
class PhaseContract:
    kind: PhaseKind
    name: str
    input_type: PhaseValue
    output_type: PhaseValue
    requires_min_candidates: int = 1
    requires_independence: bool = False
    requires_nonempty_objections: bool = False
    preserves_independence: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Phase name must not be empty")
        if self.requires_min_candidates < 1:
            raise ValueError("requires_min_candidates must be positive")


@dataclass(frozen=True, slots=True)
class PhaseCompositionPlan:
    phases: tuple[PhaseContract, ...]

    def __post_init__(self) -> None:
        validate_phase_chain(self.phases)


@dataclass(frozen=True, slots=True)
class PhaseValidation:
    valid: bool
    errors: tuple[str, ...]


def validate_phase_chain(phases: Iterable[PhaseContract]) -> PhaseValidation:
    """Enforce Definition 11 T1 and T3, plus adjacent type compatibility."""
    items = tuple(phases)
    errors: list[str] = []
    if not items:
        return PhaseValidation(False, ("A composition must contain phases.",))

    if items[0].kind is not PhaseKind.GENERATION:
        errors.append("T1: the first phase must be generation (gen).")

    decisions = [i for i, p in enumerate(items) if p.kind is PhaseKind.DECISION]
    if len(decisions) != 1:
        errors.append("T3: a composition must contain exactly one decision phase.")
    elif decisions[0] != len(items) - 1:
        errors.append("T3: the unique decision phase must be last.")

    allowed = {PhaseKind.GENERATION, PhaseKind.EXAMINATION,
               PhaseKind.REVISION, PhaseKind.DECISION}
    if any(p.kind not in allowed for p in items):
        errors.append("T1: unknown phase kind.")

    expected = [PhaseKind.GENERATION]
    for phase in items[1:-1]:
        expected.append(phase.kind)
    if len(items) >= 2 and items[-1].kind is PhaseKind.DECISION:
        body = [p.kind for p in items[1:-1]]
        if len(body) % 2 != 0 or any(
            body[i:i+2] != [PhaseKind.EXAMINATION, PhaseKind.REVISION]
            for i in range(0, len(body), 2)
        ):
            errors.append("T1: phases must follow gen (exa rev)* dec.")

    for left, right in zip(items, items[1:]):
        if left.output_type is not right.input_type:
            errors.append(
                f"T1: type mismatch between {left.name} "
                f"({left.output_type.value}) and {right.name} "
                f"({right.input_type.value})."
            )

    if items[0].input_type is not PhaseValue.PROMPT:
        errors.append("T1: generation must consume the prompt.")
    if items[0].output_type is not PhaseValue.CANDIDATE_SET:
        errors.append("T1: generation must produce a candidate set.")
    if items[-1].output_type is not PhaseValue.DECOMPOSITION:
        errors.append("T1: decision must return one decomposition.")

    result = PhaseValidation(not errors, tuple(dict.fromkeys(errors)))
    if errors:
        raise ValueError("Invalid phase composition: " + " ".join(result.errors))
    return result


def validate_phase_preconditions(
    phase: PhaseContract,
    candidates: CandidateState,
    *,
    objections_nonempty: bool = False,
) -> None:
    """Enforce T2 using the current candidate-state attributes."""
    if candidates.size < phase.requires_min_candidates:
        raise ValueError(
            f"T2: phase {phase.name} requires at least "
            f"{phase.requires_min_candidates} candidate(s); got {candidates.size}."
        )
    if phase.requires_independence and not candidates.independent:
        raise ValueError(
            f"T2: phase {phase.name} requires independent candidates (ind=1)."
        )
    if phase.requires_nonempty_objections and not objections_nonempty:
        raise ValueError(
            f"T2: phase {phase.name} requires a non-empty objection set."
        )


def transition_candidate_state(
    phase: PhaseContract, state: CandidateState, *, output_size: int | None = None,
) -> CandidateState:
    """Apply the monotone independence attribute transition from Definition 11."""
    size = state.size if output_size is None else output_size
    if size < 1:
        raise ValueError("A phase cannot produce an empty candidate set")
    independent = state.independent and phase.preserves_independence
    return CandidateState(size=size, independent=independent)


def c1_phase_contracts(revision_rounds: int = 1) -> tuple[PhaseContract, ...]:
    """Return the C1 phase skeleton: nominal group, comparison, Delphi, judge.

    The paper's Algorithm 3 permits zero or more compare/revise rounds,
    followed by merge and judge. Merge is an internal aggregator operation
    before the decision phase, not a fifth composition phase.
    """
    if revision_rounds < 0:
        raise ValueError("revision_rounds must be >= 0")
    phases: list[PhaseContract] = [
        PhaseContract(PhaseKind.GENERATION, "nominal-group-generation",
                      PhaseValue.PROMPT, PhaseValue.CANDIDATE_SET,
                      requires_min_candidates=1),
    ]
    for index in range(revision_rounds):
        phases.append(PhaseContract(
            PhaseKind.EXAMINATION, f"draft-comparison-{index + 1}",
            PhaseValue.CANDIDATE_SET, PhaseValue.OBJECTIONS,
            requires_min_candidates=2,
        ))
        phases.append(PhaseContract(
            PhaseKind.REVISION, f"anonymous-delphi-revision-{index + 1}",
            PhaseValue.OBJECTIONS, PhaseValue.CANDIDATE_SET,
            requires_nonempty_objections=True,
            preserves_independence=True,
        ))
    phases.append(PhaseContract(
        PhaseKind.DECISION, "adversarial-judge-decision",
        PhaseValue.CANDIDATE_SET, PhaseValue.DECOMPOSITION,
        requires_min_candidates=1,
    ))
    return tuple(phases)
