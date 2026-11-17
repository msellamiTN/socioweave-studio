import pytest

from sociodec.decisions import (
    Candidate, authority, compromise, consensus_medoid, decomposition_distance,
    majority, rank_sum, synthesis, union,
)
from sociodec.models.decomposition import (
    Decomposition, DeliverableComposition, Dependency, Subproblem,
)
from sociodec.models.prompt import Requirement, RequirementType


def req(statement):
    return Requirement(statement, RequirementType.DELIVERABLE, "domain")


def candidate(identifier, subproblems, edges=(), composition=None):
    items = tuple(subproblems)
    return Candidate(identifier, Decomposition(
        items,
        tuple(Dependency(a, b) for a, b in edges),
        tuple(DeliverableComposition(k, tuple(v)) for k, v in (composition or {}).items()),
    ))


def s(identifier, question, covered=()):
    return Subproblem(identifier, question, (), f"Output {question}", (), tuple(covered))


def test_rank_sum_selects_lowest_total_rank_not_majority_of_items():
    a = candidate("A", [s("a", "A")])
    b = candidate("B", [s("b", "B")])
    c = candidate("C", [s("c", "C")])
    result = rank_sum([a, b, c], {
        "v1": ("A", "B", "C"),
        "v2": ("B", "C", "A"),
        "v3": ("B", "A", "C"),
    })
    assert result.selected_candidate_id == "B"


def test_rank_sum_rejects_incomplete_or_duplicate_rankings():
    a, b = candidate("A", [s("a", "A")]), candidate("B", [s("b", "B")])
    with pytest.raises(ValueError, match="complete permutation"):
        rank_sum([a, b], {"v": ("A",)})
    with pytest.raises(ValueError, match="complete permutation"):
        rank_sum([a, b], {"v": ("A", "A")})


def test_authority_selects_only_existing_candidate_with_rationale():
    a, b = candidate("A", [s("a", "A")]), candidate("B", [s("b", "B")])
    result = authority([a, b], judge_id="neutral", selected_candidate_id="B", rationale="better coverage")
    assert result.decomposition == b.decomposition
    with pytest.raises(ValueError, match="only a supplied candidate"):
        authority([a, b], judge_id="neutral", selected_candidate_id="C", rationale="x")


def test_union_preserves_all_subproblems_and_merges_equivalent_items():
    r = req("deliverable")
    a = candidate("A", [s("a", "Plan", (r,)), s("b", "Review")],
                  [("a", "b")], {"out": ("b",)})
    b = candidate("B", [s("x", " plan ", (r,)), s("y", "Audit")],
                  [("x", "y")], {"out": ("y",)})
    result = union([a, b]).decomposition
    assert len(result.subproblems) == 3
    assert len(result.dependencies) == 2
    assert len(result.kappa["out"]) == 2
    assert result.cov == frozenset({r})


def test_union_does_not_hide_cycle_created_by_combining_candidates():
    a = candidate("A", [s("a", "A"), s("b", "B")], [("a", "b")])
    b = candidate("B", [s("x", "A"), s("y", "B")], [("y", "x")])
    result = union([a, b]).decomposition
    assert len(result.dependencies) == 2
    assert any(edge.source_id == edge.target_id for edge in result.dependencies) is False
    # Both directions remain; the structural checker is responsible for flagging the cycle.
    from sociodec.validation import find_directed_cycle
    assert find_directed_cycle(tuple(x.identifier for x in result.subproblems), result.E) is not None


def test_majority_votes_on_individual_subproblems_and_drops_minority_item():
    r = req("required")
    a = candidate("A", [s("a", "Common", (r,)), s("rare-a", "Rare")])
    b = candidate("B", [s("b", "Common", (r,))])
    c = candidate("C", [s("c", "Common", (r,))])
    signatures = {
        item.question: next(
            sig for sig in [__import__("sociodec.decisions", fromlist=["subproblem_signature"]).subproblem_signature(x)
                            for x in a.decomposition.subproblems + b.decomposition.subproblems + c.decomposition.subproblems]
            if sig[0] == item.question.casefold()
        )
        for item in []
    }
    from sociodec.decisions import subproblem_signature
    common = subproblem_signature(a.decomposition.subproblems[0])
    rare = subproblem_signature(a.decomposition.subproblems[1])
    result = majority([a, b, c], {
        "v1": frozenset({common, rare}),
        "v2": frozenset({common}),
        "v3": frozenset({common}),
    }).decomposition
    assert len(result.subproblems) == 1
    assert result.subproblems[0].question == "Common"


def test_majority_uses_strictly_more_than_half_and_rejects_unknown_items():
    a = candidate("A", [s("a", "A")])
    from sociodec.decisions import subproblem_signature
    sig = subproblem_signature(a.decomposition.subproblems[0])
    result = majority([a], {"v1": frozenset(), "v2": frozenset({sig})})
    assert result.decomposition.subproblems == ()
    with pytest.raises(ValueError, match="absent from pooled"):
        majority([a], {"v1": frozenset({("unknown",)})})


def test_synthesis_and_compromise_require_explicit_agent_produced_result():
    a = candidate("A", [s("a", "A")])
    b = candidate("B", [s("b", "B")])
    combined = Decomposition((s("z", "Combined"),), (), ())
    assert synthesis([a, b], combined, synthesizer_id="synth", rationale="merged").decomposition == combined
    assert compromise([a, b], combined, mediator_id="med", rationale="tradeoff").decomposition == combined
    with pytest.raises(ValueError, match="exactly two"):
        compromise([a], combined, mediator_id="med", rationale="x")


def test_consensus_medoid_uses_paper_distance_and_deterministic_tie_break():
    a = candidate("A", [s("a", "A")])
    b = candidate("B", [s("b", "A")])
    c = candidate("C", [s("c", "C")])
    assert decomposition_distance(a.decomposition, b.decomposition) == 0.0
    result = consensus_medoid([a, b, c])
    assert result.selected_candidate_id in {"A", "B"}


def test_empty_decomposition_distance_uses_jaccard_empty_empty_one():
    empty = Decomposition((), (), ())
    nonempty = Decomposition((s("a", "A"),), (), ())
    assert decomposition_distance(empty, empty) == 0.0
    assert decomposition_distance(empty, nonempty) == 0.5
