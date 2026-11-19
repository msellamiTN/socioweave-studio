import pytest

from sociodec.equivalence import ExactOutputConstraintMatcher, equivalence_classes
from sociodec.decisions import decomposition_distance, union
from sociodec.models.decomposition import Decomposition, Subproblem
from sociodec.models.prompt import Constraint, ConstraintKind


def sp(identifier, question, output, constraints=(), covered=()):
    return Subproblem(identifier, question, (), output, tuple(constraints), tuple(covered))


def dec(*items):
    return Decomposition(tuple(items), (), ())


def test_definition7_ignores_question_wording_and_coverage_metadata():
    matcher = ExactOutputConstraintMatcher()
    a = sp("a", "Draft the report", "A risk report")
    b = sp("b", "Prepare a risk assessment", "a risk report")
    assert matcher.equivalent(a, b)
    assert equivalence_classes([a, b], matcher) == (0, 0)


def test_definition7_requires_same_output_and_same_local_constraints():
    matcher = ExactOutputConstraintMatcher()
    hard_a = Constraint("Use EUR", ConstraintKind.HARD)
    hard_b = Constraint("Use USD", ConstraintKind.HARD)
    a = sp("a", "Prepare report", "Report", [hard_a])
    different_output = sp("b", "Prepare report", "Dashboard", [hard_a])
    different_constraint = sp("c", "Prepare report", "Report", [hard_b])
    assert not matcher.equivalent(a, different_output)
    assert not matcher.equivalent(a, different_constraint)


def test_definition7_matcher_must_be_an_equivalence_relation():
    class NonTransitive:
        def equivalent(self, a, b):
            return a == b or {a, b} in ({"a", "b"}, {"b", "c"})
    with pytest.raises(ValueError, match="transitivity"):
        equivalence_classes(["a", "b", "c"], NonTransitive())


def test_definition7_rejects_asymmetric_matcher():
    class Asymmetric:
        def equivalent(self, a, b):
            return a <= b
    with pytest.raises(ValueError, match="symmetry"):
        equivalence_classes([1, 2], Asymmetric())


def test_distance_uses_equivalence_classes_not_question_or_requirement_metadata():
    left = dec(sp("a", "Draft report", "Risk report"))
    right = dec(sp("b", "Prepare risk assessment", "risk report"))
    assert decomposition_distance(left, right) == 0.0


def test_union_uses_the_same_definition7_equivalence_classes():
    from sociodec.decisions import Candidate
    left = Candidate("left", dec(sp("a", "Draft report", "Risk report")))
    right = Candidate("right", dec(sp("b", "Prepare risk assessment", "risk report")))
    result = union([left, right]).decomposition
    assert len(result.subproblems) == 1
