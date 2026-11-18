import pytest

from sociodec.catalogue import STRATEGIES, StrategyId, get_strategy
from sociodec.strategy_protocols import build_strategy_blueprint


def explicit_views(strategy_id, n):
    if strategy_id is StrategyId.S1:
        return {
            "coordinator": "full",
            **{f"specialist-{i}": f"domain-{i}" for i in range(1, n + 1)},
        }
    if strategy_id is StrategyId.S12:
        return {
            **{f"expert-{i}": f"facet-{i}" for i in range(1, n + 1)},
            "integrator": "full",
        }
    return None


@pytest.mark.parametrize("definition", STRATEGIES, ids=lambda item: item.identifier.value)
@pytest.mark.parametrize("n,k,T", [(1, 1, 1), (2, 1, 2), (3, 2, 3)])
def test_catalogue_calls_and_depth_match_protocol_across_parameter_grid(definition, n, k, T):
    blueprint = build_strategy_blueprint(
        definition.identifier,
        n=n, k=k, T=T,
        prompt_views=explicit_views(definition.identifier, n),
    )
    strategy = blueprint.strategy
    catalogue = get_strategy(definition.identifier)

    assert strategy.calls == catalogue.calls(n=n, k=k, T=T)
    assert strategy.depth == catalogue.depth(n=n, k=k, T=T)
    assert sum(step.invokes_model for step in strategy.protocol) == catalogue.calls(
        n=n, k=k, T=T
    )
    assert len({step.stage for step in strategy.protocol}) == catalogue.depth(
        n=n, k=k, T=T
    )
