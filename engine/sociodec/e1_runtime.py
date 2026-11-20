"""Concrete assembly of the direct E1 provider, method, and executor adapters.

This module wires existing tested components; it does not choose model IDs,
interpret benchmark prompts, or launch a campaign.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from sociodec.direct_baselines import DirectBaselineAdapter
from sociodec.direct_e1 import DirectMethodAdapter
from sociodec.direct_protocol import DirectProtocolStrategyAdapter, PromptViewFactory
from sociodec.e1_protocol import BASELINES, E1Condition
from sociodec.extraction import AggregatedExtraction
from sociodec.models.prompt import Prompt
from sociodec.provider_factory import E1ProviderRegistry
from sociodec.provider_executor import ProviderFixedExecutor
from sociodec.strategy_decoding import DecisionAdjudication
from sociodec.catalogue import StrategyId


@dataclass(frozen=True, slots=True)
class DirectE1Runtime:
    executor: ProviderFixedExecutor
    method_factory: Callable[[E1Condition, Prompt, AggregatedExtraction], DirectMethodAdapter]
    registry: E1ProviderRegistry

    def assignment_manifest(self, condition: E1Condition, agent_ids: tuple[str, ...]) -> dict[str, object]:
        """Expose non-secret routing identities for campaign-level freezing."""
        manifest = self.registry.assignment_manifest(condition, agent_ids)
        manifest["executor_id"] = self.executor.executor_id
        return manifest

    def build_method(
        self, condition: E1Condition, prompt: Prompt,
        extraction: AggregatedExtraction,
    ) -> DirectMethodAdapter:
        return self.method_factory(condition, prompt, extraction)


def build_direct_e1_runtime(
    *,
    registry: E1ProviderRegistry,
    executor_id: str,
    prompt_view_factory: PromptViewFactory | None = None,
    agent_contexts: Mapping[str, str] | None = None,
    adjudications: Mapping[StrategyId | str, DecisionAdjudication] | None = None,
    n: int = 3,
    k: int = 3,
    T: int = 2,
    max_executor_tokens: int = 512,
) -> DirectE1Runtime:
    """Build the common executor and per-condition method adapter factory.

    S12 (Jigsaw) requires an explicit, operator-defined facet prompt-view
    factory. This function refuses to invent domain partitions for it.
    """
    if not executor_id.strip():
        raise ValueError("executor_id must be non-empty")
    registry.validate_complete_roster()
    registry.validate_family_catalogue()
    executor = ProviderFixedExecutor(
        registry.executor_provider(), executor_id=executor_id,
        max_new_tokens=max_executor_tokens,
    )

    def method_factory(
        condition: E1Condition, prompt: Prompt,
        extraction: AggregatedExtraction,
    ) -> DirectMethodAdapter:
        if condition.method_id in BASELINES:
            registry.validate_baseline_assignment(condition, condition.method_id)
            return DirectBaselineAdapter(
                extraction=extraction,
                provider_resolver=registry.baseline_provider_resolver,
                n_nominal=n,
                temperature_draft=0.7,
                temperature_critique=0.2,
            )
        strategy = StrategyId(condition.method_id)
        if strategy is StrategyId.S12 and prompt_view_factory is None:
            raise ValueError("S12 requires an explicit prompt_view_factory; no facet split is inferred")
        return DirectProtocolStrategyAdapter(
            extraction=extraction,
            model_resolver=registry.resolve_models,
            model_family_resolver=registry.resolve_model_families,
            invoker_factory=registry.invoker_factory(condition),
            prompt_view_factory=prompt_view_factory,
            agent_contexts=agent_contexts,
            adjudications=adjudications,
            n=n, k=k, T=T,
        )

    return DirectE1Runtime(executor=executor, method_factory=method_factory, registry=registry)
