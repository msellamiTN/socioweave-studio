import pytest

from sociodec.decisions import Candidate, majority
from sociodec.models.decomposition import Decomposition, Subproblem


def sp(identifier, question, output):
    return Subproblem(identifier, question, (), output, (), ())


def candidate(identifier, *items):
    return Candidate(identifier, Decomposition(tuple(items), (), ()))


def test_majority_ballots_use_definition7_equivalence_across_paraphrases():
    a_item = sp("a", "Draft the risk report", "Risk report")
    b_item = sp("b", "Prepare a risk assessment", "risk report")
    rare = sp("rare", "Create a dashboard", "Dashboard")
    candidates = [
        candidate("A", a_item, rare),
        candidate("B", b_item),
        candidate("C", sp("c", "Summarise risks", "RISK REPORT")),
    ]
    result = majority(candidates, {
        "v1": [sp("v1-plan", "Write a report about risks", "Risk report"), rare],
        "v2": [sp("v2-plan", "Prepare risk summary", "risk report")],
        "v3": [sp("v3-plan", "Summarise risks differently", "RISK REPORT")],
    })
    assert len(result.decomposition.subproblems) == 1
    assert result.rationale.endswith("Definition 7 matcher classes.")


def test_majority_semantic_ballot_rejects_unknown_subproblem():
    a = candidate("A", sp("a", "Draft report", "Report"))
    with pytest.raises(ValueError, match="absent from the pooled"):
        majority([a], {"v1": [sp("x", "Build dashboard", "Dashboard")]})


def test_majority_rejects_mixed_semantic_and_legacy_ballot_items():
    a_item = sp("a", "Draft report", "Report")
    a = candidate("A", a_item)
    with pytest.raises(TypeError, match="Do not mix"):
        majority([a], {"v1": [a_item], "v2": [("legacy",)]})
