import pytest

from sociodec.models.decomposition import (
    Decomposition,
    DeliverableComposition,
    Dependency,
    Subproblem,
)
from sociodec.models.prompt import (
    Constraint,
    ConstraintKind,
    Interpretation,
    Prompt,
    Requirement,
    RequirementType,
)


def fixtures():
    constraint = Constraint("No external data transfer", ConstraintKind.HARD)
    r1 = Requirement("Reduce processing time", RequirementType.TARGET, "service")
    r2 = Requirement("Provide rollout schedule", RequirementType.DELIVERABLE, "planning")
    prompt = Prompt(
        "Redesign the permit service.",
        Interpretation(
            goal="Redesign the permit service",
            constraints=(constraint,),
            deliverables=("Process redesign", "Rollout schedule"),
        ),
    )
    s1 = Subproblem(
        "s1", "Analyse current process", ("Current process records",),
        "As-is analysis", (constraint,), (r1,),
    )
    s2 = Subproblem(
        "s2", "Prepare rollout schedule", ("As-is analysis",),
        "Rollout schedule", (), (r2,),
    )
    return prompt, constraint, r1, r2, s1, s2


def test_subproblem_represents_definition_4_and_coverage():
    _, _, r1, _, s1, _ = fixtures()
    assert s1.question == "Analyse current process"
    assert s1.inputs == ("Current process records",)
    assert s1.output == "As-is analysis"
    assert s1.cov == frozenset({r1})


def test_decomposition_represents_s_e_kappa_and_union_coverage():
    _, _, r1, r2, s1, s2 = fixtures()
    d = Decomposition(
        (s1, s2),
        (Dependency("s1", "s2"),),
        (
            DeliverableComposition("Process redesign", ("s1",)),
            DeliverableComposition("Rollout schedule", ("s2",)),
        ),
    )
    assert d.S == frozenset({s1, s2})
    assert d.E == frozenset({("s1", "s2")})
    assert d.kappa == {
        "Process redesign": frozenset({"s1"}),
        "Rollout schedule": frozenset({"s2"}),
    }
    assert d.cov == frozenset({r1, r2})


def test_empty_contributor_set_is_representable_for_later_v5_validation():
    _, _, _, _, s1, _ = fixtures()
    d = Decomposition(
        (s1,), (), (DeliverableComposition("Process redesign", ()),)
    )
    assert d.kappa["Process redesign"] == frozenset()


def test_self_dependency_is_representable_for_later_acyclicity_validation():
    _, _, _, _, s1, _ = fixtures()
    d = Decomposition((s1,), (Dependency("s1", "s1"),), ())
    assert ("s1", "s1") in d.E


@pytest.mark.parametrize("kwargs, message", [
    ({"identifier": " ", "question": "Q", "inputs": (), "output": "O"},
     "identifier"),
    ({"identifier": "s", "question": " ", "inputs": (), "output": "O"},
     "question"),
    ({"identifier": "s", "question": "Q", "inputs": (), "output": " "},
     "output"),
    ({"identifier": "s", "question": "Q", "inputs": ("",), "output": "O"},
     "inputs"),
    ({"identifier": "s", "question": "Q", "inputs": ("x", "x"), "output": "O"},
     "inputs must be unique"),
])
def test_subproblem_rejects_invalid_fields(kwargs, message):
    with pytest.raises(ValueError, match=message):
        Subproblem(**kwargs)


def test_subproblem_rejects_duplicate_local_constraints_and_coverage():
    _, constraint, r1, _, _, _ = fixtures()
    with pytest.raises(ValueError, match="local_constraints must be unique"):
        Subproblem("s", "Q", (), "O", (constraint, constraint))
    with pytest.raises(ValueError, match="covered_requirements must be unique"):
        Subproblem("s", "Q", (), "O", (), (r1, r1))


def test_dependency_rejects_blank_endpoints():
    with pytest.raises(ValueError, match="source_id"):
        Dependency(" ", "s2")
    with pytest.raises(ValueError, match="target_id"):
        Dependency("s1", " ")


def test_composition_rejects_blank_and_duplicate_contributors():
    with pytest.raises(ValueError, match="deliverable"):
        DeliverableComposition(" ", ())
    with pytest.raises(ValueError, match="must not contain empty"):
        DeliverableComposition("D", ("s1", " "))
    with pytest.raises(ValueError, match="must be unique"):
        DeliverableComposition("D", ("s1", "s1"))


def test_decomposition_rejects_duplicate_subproblem_ids_edges_and_keys():
    _, _, _, _, s1, s2 = fixtures()
    with pytest.raises(ValueError, match="unique identifiers"):
        Decomposition((s1, s1), (), ())
    with pytest.raises(ValueError, match="duplicate edges"):
        Decomposition((s1, s2), (Dependency("s1", "s2"), Dependency("s1", "s2")), ())
    with pytest.raises(ValueError, match="unique deliverable keys"):
        Decomposition(
            (s1,), (),
            (DeliverableComposition("D", ("s1",)), DeliverableComposition("D", ())),
        )


def test_decomposition_rejects_dangling_dependency_and_composition_references():
    _, _, _, _, s1, _ = fixtures()
    with pytest.raises(ValueError, match="source does not exist"):
        Decomposition((s1,), (Dependency("missing", "s1"),), ())
    with pytest.raises(ValueError, match="target does not exist"):
        Decomposition((s1,), (Dependency("s1", "missing"),), ())
    with pytest.raises(ValueError, match="unknown subproblem"):
        Decomposition((s1,), (), (DeliverableComposition("D", ("missing",)),))


def test_validate_against_accepts_prompt_relative_constraints_and_requirements():
    prompt, _, r1, r2, s1, s2 = fixtures()
    d = Decomposition(
        (s1, s2), (Dependency("s1", "s2"),),
        (
            DeliverableComposition("Process redesign", ("s1",)),
            DeliverableComposition("Rollout schedule", ("s2",)),
        ),
    )
    d.validate_against(prompt, (r1, r2))


def test_validate_against_rejects_constraint_outside_prompt_C():
    prompt, _, r1, _, _, _ = fixtures()
    foreign = Constraint("Use a private cloud", ConstraintKind.SOFT)
    s = Subproblem("s", "Q", (), "O", (foreign,), (r1,))
    d = Decomposition((s,), (), ())
    with pytest.raises(ValueError, match="outside prompt C"):
        d.validate_against(prompt, (r1,))


def test_validate_against_rejects_coverage_outside_explicit_requirement_set():
    prompt, _, r1, r2, _, _ = fixtures()
    s = Subproblem("s", "Q", (), "O", (), (r2,))
    d = Decomposition((s,), (), ())
    with pytest.raises(ValueError, match="outside R\\(P\\)"):
        d.validate_against(prompt, (r1,))


def test_validate_against_rejects_undeclared_deliverable_key():
    prompt, _, r1, _, s1, _ = fixtures()
    d = Decomposition((s1,), (), (DeliverableComposition("Unknown", ("s1",)),))
    with pytest.raises(ValueError, match="undeclared deliverable"):
        d.validate_against(prompt, (r1,))


def test_validate_against_does_not_enforce_v1_v2_or_v5():
    prompt, _, r1, _, s1, _ = fixtures()
    d = Decomposition(
        (s1,), (Dependency("s1", "s1"),),
        (DeliverableComposition("Process redesign", ()),),
    )
    d.validate_against(prompt, (r1,))
