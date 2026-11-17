import pytest

from sociodec.catalogue import STRATEGIES, StrategyId, get_strategy


def test_catalogue_contains_exactly_thirteen_paper_strategies():
    assert len(STRATEGIES) == 13
    assert {item.identifier for item in STRATEGIES} == set(StrategyId)


def test_table_4_costs_and_depths_at_n3_k3_t2():
    expected = {
        StrategyId.S1: (5, 3),
        StrategyId.S12: (4, 2),
        StrategyId.S2: (4, 2),
        StrategyId.S3: (6, 2),
        StrategyId.S4: (8, 4),
        StrategyId.S9: (6, 2),
        StrategyId.S5: (4, 4),
        StrategyId.S6: (3, 3),
        StrategyId.S8: (6, 4),
        StrategyId.S13: (4, 4),
        StrategyId.S7: (5, 3),
        StrategyId.S11: (5, 3),
        StrategyId.S10: (7, 7),
    }
    for identifier, pair in expected.items():
        strategy = get_strategy(identifier)
        assert (strategy.calls(n=3, k=3, T=2), strategy.depth(n=3, k=3, T=2)) == pair


def test_parameterized_cost_formulas():
    assert get_strategy("S4").calls(n=5, T=3) == 18
    assert get_strategy("S8").calls(k=5) == 8
    assert get_strategy("S10").depth(n=4, T=3) == 13
    with pytest.raises(ValueError, match="n must"):
        get_strategy("S3").calls(n=0)
    with pytest.raises(ValueError, match="T must"):
        get_strategy("S4").depth(T=0)
