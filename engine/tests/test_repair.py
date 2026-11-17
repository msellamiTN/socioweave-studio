import pytest

from sociodec.models.decomposition import (
    Decomposition, DeliverableComposition, Dependency, Subproblem,
)
from sociodec.models.prompt import Interpretation, Prompt, Requirement, RequirementType
from sociodec.repair import remove_least_supported_cycle_edge, repair_decomposition


def case():
    prompt = Prompt(
        "Create a service plan.",
        Interpretation("Create a service plan", deliverables=("Service plan",)),
    )
    r1 = Requirement("Create a service plan", RequirementType.DELIVERABLE, "service")
    a = Subproblem("a", "Analyse", (), "Analysis", (), (r1,))
    b = Subproblem("b", "Design", ("Analysis",), "Design", (), (r1,))
    c = Subproblem("c", "Review", ("Design",), "Review", (), (r1,))
    d = Decomposition(
        (a, b, c),
        (Dependency("a", "b"), Dependency("b", "c"), Dependency("c", "a")),
        (DeliverableComposition("Service plan", ("a", "b", "c")),),
    )
    return prompt, (r1,), a, b, c, d


def test_remove_least_supported_cycle_edge():
    _, _, _, _, _, d = case()
    revised, removed = remove_least_supported_cycle_edge(
        d, ("a", "b", "c", "a"),
        {("a", "b"): 3, ("b", "c"): 1, ("c", "a"): 2},
    )
    assert removed == ("b", "c")
    assert revised.E == frozenset({("a", "b"), ("c", "a")})


def test_cycle_support_tie_uses_lexicographic_edge_order():
    _, _, _, _, _, d = case()
    _, removed = remove_least_supported_cycle_edge(
        d, ("a", "b", "c", "a"),
        {("a", "b"): 1, ("b", "c"): 1, ("c", "a"): 2},
    )
    assert removed == ("a", "b")


def test_cycle_repair_requires_evidence_for_every_cycle_edge():
    _, _, _, _, _, d = case()
    with pytest.raises(ValueError, match="Missing candidate support count"):
        remove_least_supported_cycle_edge(
            d, ("a", "b", "c", "a"), {("a", "b"): 1}
        )


def test_cycle_repair_rejects_negative_or_boolean_support_count():
    _, _, _, _, _, d = case()
    with pytest.raises(ValueError, match="non-negative integer"):
        remove_least_supported_cycle_edge(
            d, ("a", "b", "c", "a"),
            {("a", "b"): -1, ("b", "c"): 1, ("c", "a"): 2},
        )
    with pytest.raises(ValueError, match="non-negative integer"):
        remove_least_supported_cycle_edge(
            d, ("a", "b", "c", "a"),
            {("a", "b"): True, ("b", "c"): 1, ("c", "a"): 2},
        )


def test_repair_decomposition_removes_cycle_without_callback_when_only_cycle_failure():
    prompt, requirements, _, _, _, d = case()
    result = repair_decomposition(
        prompt, requirements, d,
        {("a", "b"): 3, ("b", "c"): 1, ("c", "a"): 2},
    )
    assert result.removed_edges == (("b", "c"),)
    assert result.repair_call_made is False
    assert result.final_report.v2_acyclicity.status.value == "pass"


def test_non_cycle_failures_trigger_exactly_one_repair_callback():
    prompt, requirements, a, b, c, d = case()
    # Cycle support is sufficient; the callback is given the post-cycle failures.
    calls = []

    def repair(current, failures):
        calls.append(failures)
        # Repair the empty coverage of no requirement by ensuring a's output
        # contributes to the sole deliverable while preserving acyclicity.
        return Decomposition(
            current.subproblems,
            current.dependencies,
            (DeliverableComposition("Service plan", ("a", "b", "c", "z")),),
        )

    # The fixture has a cycle; after removing one edge, V5 may still pass.
    # Add an isolated sink not mapped to a deliverable to force V5.
    isolated = Subproblem("z", "Archive", (), "Archive record", (), ())
    d2 = Decomposition(
        (*d.subproblems, isolated),
        d.dependencies,
        d.composition,
    )
    result = repair_decomposition(
        prompt, requirements, d2,
        {("a", "b"): 3, ("b", "c"): 1, ("c", "a"): 2},
        repair_callback=repair,
    )
    assert len(calls) == 1
    assert result.repair_call_made is True
    assert result.final_report.v5_composition.status.value == "pass"


def test_repair_callback_is_not_retried_when_failures_remain():
    prompt, requirements, _, _, _, d = case()
    calls = []

    def no_op(current, failures):
        calls.append(failures)
        return current

    result = repair_decomposition(
        prompt, requirements, d,
        {("a", "b"): 3, ("b", "c"): 1, ("c", "a"): 2},
        repair_callback=no_op,
    )
    assert len(calls) == 1
    assert result.repair_call_made is True


def test_repair_callback_return_type_is_enforced():
    prompt, requirements, _, _, _, d = case()

    def invalid(current, failures):
        return None

    # Force a non-cycle finding by adding an unowned sink.
    orphan = Subproblem("orphan", "Orphan", (), "Unused", (), ())
    d2 = Decomposition(
        (*d.subproblems, orphan), d.dependencies, d.composition
    )
    with pytest.raises(TypeError, match="must return a Decomposition"):
        repair_decomposition(
            prompt, requirements, d2,
            {("a", "b"): 3, ("b", "c"): 1, ("c", "a"): 2},
            repair_callback=invalid,
        )
