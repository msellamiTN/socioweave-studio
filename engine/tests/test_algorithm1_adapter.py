from sociodec.algorithm1_adapter import Algorithm1CheckRepairAdapter
from sociodec.models.decomposition import Decomposition, Dependency, DeliverableComposition
from sociodec.validation import CheckStatus
from test_validation import setup_case

def _adapter(prompt, requirements, candidates=(), repair=None):
    return Algorithm1CheckRepairAdapter(prompt=prompt, requirements=requirements,
        candidate_decompositions=candidates, repair=repair)

def test_cycle_only_is_repaired_without_model_call():
    prompt, requirements, _, _, good = setup_case()
    cyclic = Decomposition(good.subproblems, (Dependency("s1", "s2"), Dependency("s2", "s1")), good.composition)
    calls = []
    result = _adapter(prompt, requirements, candidates=(good,), repair=lambda d, r: calls.append(r) or d).run(cyclic)
    assert result.removed_cycle_edges == (("s2", "s1"),)
    assert result.repair_calls == 0 and calls == []
    assert result.report.v2_acyclicity.status is CheckStatus.PASS
    assert result.report.structural_valid

def test_least_supported_edge_is_removed():
    prompt, requirements, _, _, good = setup_case()
    cyclic = Decomposition(good.subproblems, (Dependency("s1", "s2"), Dependency("s2", "s1")), good.composition)
    result = _adapter(prompt, requirements, candidates=(good, good)).run(cyclic)
    assert result.removed_cycle_edges == (("s2", "s1"),)
    assert result.decomposition.E == frozenset({("s1", "s2")})

def test_non_cycle_failure_invokes_one_repair_then_rechecks():
    prompt, requirements, s1, _, good = setup_case()
    incomplete = Decomposition((s1,), (), (DeliverableComposition("Service plan", ("s1",)), DeliverableComposition("Rollout plan", ("s1",))))
    calls = []
    result = _adapter(prompt, requirements, repair=lambda d, r: calls.append(r) or good).run(incomplete)
    assert len(calls) == result.repair_calls == 1
    assert result.report.structural_valid

def test_failed_repair_is_not_repeated():
    prompt, requirements, s1, _, _ = setup_case()
    incomplete = Decomposition((s1,), (), (DeliverableComposition("Service plan", ("s1",)), DeliverableComposition("Rollout plan", ("s1",))))
    calls = []
    result = _adapter(prompt, requirements, repair=lambda d, r: calls.append(r) or d).run(incomplete)
    assert len(calls) == result.repair_calls == 1
    assert result.report.v1_coverage.status is CheckStatus.FAIL

def test_v3_v4_remain_not_evaluated():
    prompt, requirements, _, _, good = setup_case()
    result = _adapter(prompt, requirements).run(good)
    assert result.report.v3_solvability.status is CheckStatus.NOT_EVALUATED
    assert result.report.v4_faithfulness.status is CheckStatus.NOT_EVALUATED
