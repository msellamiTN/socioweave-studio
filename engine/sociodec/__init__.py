"""SocioDec Engine: formal core for SOCIOWEAVE.

Exports the paper-aligned prompt, requirement and decomposition models.
"""
from .models.decomposition import (
    Decomposition,
    DeliverableComposition,
    Dependency,
    Subproblem,
)
from .models.prompt import (
    Constraint,
    ConstraintKind,
    Entity,
    Interpretation,
    Prompt,
    Requirement,
    RequirementType,
    SourceSpan,
)

__all__ = [
    "Constraint",
    "ConstraintKind",
    "Decomposition",
    "DeliverableComposition",
    "Dependency",
    "Entity",
    "Interpretation",
    "Prompt",
    "Requirement",
    "RequirementType",
    "SourceSpan",
    "Subproblem",
]
