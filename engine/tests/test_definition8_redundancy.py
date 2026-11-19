import pytest

from sociodec.metrics import decomposition_metrics
from sociodec.models.decomposition import Subproblem
from sociodec.models.prompt import Constraint, ConstraintKind


def sp(identifier, question, output, constraints=()):
    return Subproblem(identifier, question, (), output, tuple(constraints), ())


def test_definition8_redundancy_uses_definition7_matcher_classes():
    items = [
        sp("a", "Draft the report", "Risk report"),
        sp("b", "Prepare a risk assessment", "risk report"),
        sp("c", "Create dashboard", "Dashboard"),
    ]
    result = decomposition_metrics(
        requirements={"r"}, covered_requirements={"r"}, subproblem_items=items,
        edges=[], acyclic=True, composition_complete=True,
    )
    assert result.redundancy == pytest.approx(2 / 3)


def test_definition8_redundancy_separates_different_local_constraints():
    items = [
        sp("a", "Prepare report", "Report", [Constraint("Use EUR", ConstraintKind.HARD)]),
        sp("b", "Prepare report", "Report", [Constraint("Use USD", ConstraintKind.HARD)]),
    ]
    result = decomposition_metrics(
        requirements={"r"}, covered_requirements={"r"}, subproblem_items=items,
        edges=[], acyclic=True, composition_complete=True,
    )
    assert result.redundancy == 0.0


def test_definition8_redundancy_legacy_signature_path_remains_available():
    result = decomposition_metrics(
        requirements={"r"}, covered_requirements={"r"},
        subproblem_signatures=["same", "same", "other"], edges=[],
        acyclic=True, composition_complete=True,
    )
    assert result.redundancy == pytest.approx(2 / 3)
