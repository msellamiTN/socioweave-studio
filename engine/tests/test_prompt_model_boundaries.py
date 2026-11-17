import pytest

from sociodec.models.prompt import (
    Constraint, ConstraintKind, Entity, Interpretation, Prompt, Requirement,
    RequirementType, SourceSpan,
)


@pytest.mark.parametrize("start,end", [(-1, 1), (0, 0), (2, 1)])
def test_source_span_rejects_invalid_intervals(start, end):
    with pytest.raises(ValueError):
        SourceSpan(start, end)


def test_source_span_uses_half_open_character_offsets_with_unicode():
    text = "Café — citoyens"
    span = SourceSpan(0, 4)
    assert span.extract(text) == "Café"


def test_source_span_allows_exact_end_of_source():
    text = "target"
    assert SourceSpan(0, len(text)).extract(text) == text


def test_source_span_rejects_end_beyond_source():
    with pytest.raises(ValueError, match="exceeds"):
        SourceSpan(0, 7).extract("target")


@pytest.mark.parametrize("factory", [
    lambda: Constraint("  ", ConstraintKind.HARD),
    lambda: Entity("  "),
    lambda: Requirement("  ", RequirementType.TARGET, "domain"),
    lambda: Requirement("target", RequirementType.TARGET, "  "),
    lambda: Interpretation("  "),
    lambda: Prompt("  ", Interpretation("goal")),
    lambda: Prompt("text", Interpretation("goal"), identifier="  "),
])
def test_domain_objects_reject_blank_required_fields(factory):
    with pytest.raises(ValueError):
        factory()


def test_interpretation_rejects_blank_input_and_deliverable_entries():
    with pytest.raises(ValueError, match="inputs"):
        Interpretation("goal", inputs=("valid", "  "))
    with pytest.raises(ValueError, match="deliverables"):
        Interpretation("goal", deliverables=("report", "  "))


def test_interpretation_partitions_hard_and_soft_constraints_without_reordering():
    hard = Constraint("must", ConstraintKind.HARD)
    soft = Constraint("prefer", ConstraintKind.SOFT)
    other_hard = Constraint("shall", ConstraintKind.HARD)
    interpretation = Interpretation("goal", constraints=(hard, soft, other_hard))
    assert interpretation.hard_constraints == (hard, other_hard)
    assert interpretation.soft_constraints == (soft,)


def test_prompt_notation_aliases_are_read_only_views_of_stored_fields():
    interpretation = Interpretation("goal")
    prompt = Prompt("original text", interpretation, "p-1")
    assert prompt.x is prompt.text
    assert prompt.iota is prompt.interpretation


def test_explicit_requirement_validation_checks_each_requirement():
    prompt = Prompt("A target and a deliverable", Interpretation("goal"))
    requirements = (
        Requirement("target", RequirementType.TARGET, "ops", SourceSpan(2, 8)),
        Requirement("deliverable", RequirementType.DELIVERABLE, "ops", SourceSpan(15, 26)),
    )
    prompt.validate_explicit_requirements(requirements)
    with pytest.raises(ValueError, match="missing its source span"):
        prompt.validate_explicit_requirements((
            Requirement("missing", RequirementType.CONSTRAINT, "ops"),
        ))


def test_requirement_entity_names_must_be_unique():
    with pytest.raises(ValueError, match="unique"):
        Requirement("target", RequirementType.TARGET, "ops",
                    SourceSpan(0, 6), entity_names=("Citizen", "Citizen"))

@pytest.mark.parametrize("text", ["a", "abc", "Café", "東京🙂"])
def test_all_valid_half_open_spans_match_python_slicing(text):
    for start in range(len(text)):
        for end in range(start + 1, len(text) + 1):
            span = SourceSpan(start, end)
            assert span.extract(text) == text[start:end]


def test_frozen_domain_values_cannot_be_mutated():
    prompt = Prompt("text", Interpretation("goal"))
    with pytest.raises((AttributeError, TypeError)):
        prompt.text = "changed"