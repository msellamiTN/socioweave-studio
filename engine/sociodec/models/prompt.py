"""Prompt and requirement domain model.

Scientific basis: Definitions 1 and 2 in
"Societies of Decomposers: Social and Organisational Strategies for
LLM-Based Multi-Agent Prompt Decomposition".

Important boundary: the model stores a declared interpretation of the prompt.
It does not claim to infer the complete set Int(x), nor does it perform
requirement extraction. Those belong to later engine components.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class RequirementType(StrEnum):
    """The three requirement types defined by the paper."""

    TARGET = "target"
    CONSTRAINT = "constraint"
    DELIVERABLE = "deliverable"


class ConstraintKind(StrEnum):
    """Hard constraints must hold; soft constraints express preferences."""

    HARD = "hard"
    SOFT = "soft"


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """A half-open character interval [start, end) in the original prompt."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValueError("SourceSpan.start must be >= 0")
        if self.end <= self.start:
            raise ValueError("SourceSpan.end must be greater than start")

    def extract(self, source: str) -> str:
        if self.end > len(source):
            raise ValueError("SourceSpan exceeds the source text length")
        return source[self.start:self.end]


@dataclass(frozen=True, slots=True)
class Constraint:
    """A constraint classified as hard or soft."""

    statement: str
    kind: ConstraintKind

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("Constraint.statement must not be empty")


@dataclass(frozen=True, slots=True)
class Entity:
    """An actor or object named in the prompt; not itself a requirement."""

    name: str
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Entity.name must not be empty")


@dataclass(frozen=True, slots=True)
class Requirement:
    """An atomic, individually checkable requirement.

    Explicit requirements should carry a source_span. An implicit
    requirement is represented later as an extraction hypothesis and has
    no source span in the prompt.
    """

    statement: str
    type: RequirementType
    domain: str
    source_span: SourceSpan | None = None
    entity_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("Requirement.statement must not be empty")
        if not self.domain.strip():
            raise ValueError("Requirement.domain must not be empty")
        if len(set(self.entity_names)) != len(self.entity_names):
            raise ValueError("Requirement.entity_names must be unique")

    def validate_against(self, prompt_text: str) -> None:
        """Check that an explicit requirement's span is valid for prompt x.

        The paper requires source spans for explicit requirements. This
        method checks span bounds and non-empty extraction; it deliberately
        does not assert semantic equivalence between the span and statement.
        """
        if self.source_span is None:
            raise ValueError("Explicit requirement is missing its source span")
        if not self.source_span.extract(prompt_text).strip():
            raise ValueError("Requirement source span resolves to empty text")


@dataclass(frozen=True, slots=True)
class Interpretation:
    """The interpretation tuple ι = (g, C, I, O) from Definition 1."""

    goal: str
    constraints: tuple[Constraint, ...] = ()
    inputs: tuple[str, ...] = ()
    deliverables: tuple[str, ...] = ()
    entities: tuple[Entity, ...] = ()

    def __post_init__(self) -> None:
        if not self.goal.strip():
            raise ValueError("Interpretation.goal must not be empty")
        if any(not item.strip() for item in self.inputs):
            raise ValueError("Interpretation.inputs must not contain empty values")
        if any(not item.strip() for item in self.deliverables):
            raise ValueError("Interpretation.deliverables must not contain empty values")
        entity_names = [entity.name.casefold() for entity in self.entities]
        if len(entity_names) != len(set(entity_names)):
            raise ValueError("Interpretation.entities must be unique by name")

    @property
    def hard_constraints(self) -> tuple[Constraint, ...]:
        return tuple(c for c in self.constraints if c.kind is ConstraintKind.HARD)

    @property
    def soft_constraints(self) -> tuple[Constraint, ...]:
        return tuple(c for c in self.constraints if c.kind is ConstraintKind.SOFT)


@dataclass(frozen=True, slots=True)
class Prompt:
    """A prompt P = (x, ι): original text and an explicit interpretation."""

    text: str
    interpretation: Interpretation
    identifier: str = "prompt"

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("Prompt.text must not be empty")
        if not self.identifier.strip():
            raise ValueError("Prompt.identifier must not be empty")

    @property
    def x(self) -> str:
        """Paper notation for the user-authored prompt text."""
        return self.text

    @property
    def iota(self) -> Interpretation:
        """Paper notation for the declared interpretation ι."""
        return self.interpretation

    def validate_explicit_requirements(
        self, requirements: tuple[Requirement, ...]
    ) -> None:
        """Validate source-span presence/bounds for explicit requirements."""
        for requirement in requirements:
            requirement.validate_against(self.text)
