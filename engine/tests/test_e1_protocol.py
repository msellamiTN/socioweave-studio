import pytest
from sociodec.e1_protocol import ALL_DATASETS, BASELINES, EXPECTED_PROMPTS, E1Condition, e1_metric_obligations, validate_e1_manifest, build_e1_conditions
from sociodec.catalogue import STRATEGIES

def frozen_ids():
    return {d:tuple(f"{d}-{i:03d}" for i in range(EXPECTED_PROMPTS[d])) for d in ALL_DATASETS}

def test_e1_metric_obligations_follow_table12():
    assert "coverage" not in e1_metric_obligations("BREAK")
    assert "coverage" not in e1_metric_obligations("StrategyQA")
    assert "coverage" not in e1_metric_obligations("TaskBench")
    assert "coverage" in e1_metric_obligations("TravelPlanner")
    assert "hypothesis_verdicts" in e1_metric_obligations("smart-administration")

def test_baseline_must_name_compared_strategy():
    with pytest.raises(ValueError, match="Only baseline rows"):
        E1Condition("BREAK",BASELINES[0],"heterogeneous",0,("p1",),4)

def test_strategy_cannot_declare_baseline_match():
    with pytest.raises(ValueError, match="Only baseline rows"):
        E1Condition("BREAK",STRATEGIES[0].identifier.value,"heterogeneous",0,("p1",),4,"S1")

def test_e1_requires_five_seed_indices():
    with pytest.raises(ValueError, match="five seed indices"):
        validate_e1_manifest([E1Condition("BREAK","S1","heterogeneous",5,frozen_ids()["BREAK"],5)],expected_prompt_ids=frozen_ids(),require_complete_grid=False)

def test_e1_requires_exact_paper_prompt_counts():
    ids=frozen_ids(); ids["BREAK"]=("only-one",)
    with pytest.raises(ValueError, match="100 unique frozen prompt IDs"):
        validate_e1_manifest([],expected_prompt_ids=ids,require_complete_grid=False)

def test_e1_detects_baseline_budget_mismatch():
    ids=frozen_ids(); rows=[E1Condition("BREAK","S1","heterogeneous",0,ids["BREAK"],5),E1Condition("BREAK",BASELINES[0],"heterogeneous",0,ids["BREAK"],4,"S1")]
    errors=validate_e1_manifest(rows,expected_prompt_ids=ids,require_complete_grid=False)
    assert any("does not match" in e for e in errors)

def test_e1_reports_missing_grid_cells():
    errors=validate_e1_manifest([],expected_prompt_ids=frozen_ids(),require_complete_grid=False)
    assert any("missing strategy condition" in e for e in errors)
    assert any("missing budget-matched baseline" in e for e in errors)

def test_e1_requires_all_five_datasets():
    with pytest.raises(ValueError, match="all five paper datasets"):
        validate_e1_manifest([],expected_prompt_ids={"BREAK":frozen_ids()["BREAK"]},require_complete_grid=False)


def test_build_e1_conditions_creates_complete_budget_matched_paper_grid():
    conditions = build_e1_conditions(expected_prompt_ids=frozen_ids())
    assert len(conditions) == 5 * 2 * 5 * len(STRATEGIES) * (1 + len(BASELINES))
    errors = validate_e1_manifest(
        conditions, expected_prompt_ids=frozen_ids(), require_complete_grid=True,
    )
    assert errors == ()
    by_key = {
        (row.dataset, row.method_id, row.model_mode, row.seed, row.matched_strategy_id): row
        for row in conditions
    }
    for row in conditions:
        if row.method_id in BASELINES:
            matched = by_key[(
                row.dataset, row.matched_strategy_id, row.model_mode,
                row.seed, None,
            )]
            assert row.call_budget == matched.call_budget
            assert row.prompt_ids == matched.prompt_ids


@pytest.mark.parametrize("n,k,T", [(0, 3, 2), (3, 0, 2), (3, 3, 0)])
def test_build_e1_conditions_rejects_invalid_strategy_parameters(n, k, T):
    with pytest.raises(ValueError, match="n, k and T"):
        build_e1_conditions(expected_prompt_ids=frozen_ids(), n=n, k=k, T=T)
