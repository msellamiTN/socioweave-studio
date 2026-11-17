import pytest

from sociodec.models.prompt import (
    Constraint,
    ConstraintKind,
    Entity,
    Interpretation,
    Prompt,
    Requirement,
    RequirementType,
    SourceSpan,
)


def sample_prompt() -> Prompt:
    text = "Reduce processing time to 20 days within a nine-month rollout."
    interpretation = Interpretation(
        goal="Redesign the permit process",
        constraints=(
            Constraint("Processing time is at most 20 days", ConstraintKind.HARD),
            Constraint("Prefer a simple citizen experience", ConstraintKind.SOFT),
        ),
        inputs=("Current processing time is 60 days",),
        deliverables=("Process redesign", "Rollout schedule"),
        entities=(Entity("Municipality"), Entity("Citizens")),
    )
    return Prompt(text=text, interpretation=interpretation, identifier="sample-01")


def test_prompt_preserves_original_text_and_interpretation():
    prompt = sample_prompt()
    assert prompt.x == prompt.text
    assert prompt.iota.goal == "Redesign the permit process"
    assert len(prompt.iota.hard_constraints) == 1
    assert len(prompt.iota.soft_constraints) == 1


def test_requirement_source_span_extracts_original_text():
    text = "Reduce processing time to 20 days."
    requirement = Requirement(
        statement="Processing time must be 20 days",
        type=RequirementType.TARGET,
        domain="operational",
        source_span=SourceSpan(0, len(text) - 1),
    )
    requirement.validate_against(text)
    assert requirement.source_span.extract(text) == "Reduce processing time to 20 days"


def test_explicit_requirement_requires_source_span():
    requirement = Requirement(
        statement="A target",
        type=RequirementType.TARGET,
        domain="operational",
    )
    with pytest.raises(ValueError, match="missing its source span"):
        requirement.validate_against("A target")


def test_source_span_rejects_invalid_bounds():
    with pytest.raises(ValueError):
        SourceSpan(5, 5)
    with pytest.raises(ValueError):
        SourceSpan(-1, 2)


def test_requirement_span_must_fit_prompt():
    requirement = Requirement(
        statement="A target",
        type=RequirementType.TARGET,
        domain="operational",
        source_span=SourceSpan(0, 100),
    )
    with pytest.raises(ValueError, match="exceeds"):
        requirement.validate_against("short")


def test_interpretation_rejects_duplicate_entities():
    with pytest.raises(ValueError, match="unique"):
        Interpretation(
            goal="Goal",
            entities=(Entity("Citizen"), Entity("citizen")),
        )
