"""Concrete assembly of the direct E1 provider, method, and executor adapters.

This module wires existing tested components; it does not choose model IDs,
interpret benchmark prompts, or launch a campaign.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from sociodec.experiments import content_hash
from sociodec.datasets import E1FrozenSnapshot, e1_prompt_id_map
from sociodec.e1_protocol import validate_e1_manifest
from sociodec.catalogue import get_strategy
from sociodec.strategy_protocols import build_strategy_blueprint
from sociodec.models.strategy import Role

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
class E1CampaignPreflightReport:
    dataset_snapshot_sha256: str
    provider_manifest_sha256: str
    conditions_sha256: str
    condition_count: int
    prompt_count: int
    provider_rosters_validated: int
    model_modes: tuple[str, ...]
    readiness: str = "configuration_validated_no_live_calls"
    live_provider_calls: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "e1-campaign-preflight-v1",
            "readiness": self.readiness,
            "dataset_snapshot_sha256": self.dataset_snapshot_sha256,
            "provider_manifest_sha256": self.provider_manifest_sha256,
            "conditions_sha256": self.conditions_sha256,
            "condition_count": self.condition_count,
            "prompt_count": self.prompt_count,
            "provider_rosters_validated": self.provider_rosters_validated,
            "model_modes": list(self.model_modes),
            "live_provider_calls": self.live_provider_calls,
        }


@dataclass(frozen=True, slots=True)
class DirectE1Runtime:
    executor: ProviderFixedExecutor
    method_factory: Callable[[E1Condition, Prompt, AggregatedExtraction], DirectMethodAdapter]
    registry: E1ProviderRegistry
    n: int = 3
    k: int = 3
    T: int = 2
    supports_jigsaw_facets: bool = False

    def assignment_manifest(self, condition: E1Condition, agent_ids: tuple[str, ...]) -> dict[str, object]:
        """Expose non-secret routing identities for one method condition."""
        manifest = self.registry.assignment_manifest(condition, agent_ids)
        manifest["executor_id"] = self.executor.executor_id
        return manifest

    def campaign_manifest(self) -> dict[str, object]:
        """Return the full model/executor identity manifest to freeze with E1."""
        return self.registry.campaign_manifest(executor_id=self.executor.executor_id)


    def preflight_campaign(
        self,
        *,
        snapshot: E1FrozenSnapshot,
        conditions: tuple[E1Condition, ...],
    ) -> E1CampaignPreflightReport:
        """Validate the complete frozen E1 design and provider routing without calls."""
        if not isinstance(snapshot, E1FrozenSnapshot):
            raise TypeError("snapshot must be a validated E1FrozenSnapshot")
        if snapshot.manifest.get("schema_version") != "e1-frozen-benchmark-snapshot-v1":
            raise ValueError("snapshot manifest schema is not the frozen E1 schema")
        snapshot_sha256 = snapshot.manifest.get("snapshot_sha256")
        if not isinstance(snapshot_sha256, str) or len(snapshot_sha256) != 64:
            raise ValueError("snapshot manifest must include a SHA-256 fingerprint")
        expected_ids = e1_prompt_id_map(snapshot)
        examples_by_dataset = {
            dataset: tuple(
                example.example_id for example in snapshot.examples
                if example.dataset == dataset
            )
            for dataset in expected_ids
        }
        for dataset, ids in expected_ids.items():
            if len(examples_by_dataset[dataset]) != len(ids) or set(examples_by_dataset[dataset]) != set(ids):
                raise ValueError(f"snapshot examples do not match frozen prompt IDs for {dataset}")
        validate_e1_manifest(
            conditions, expected_prompt_ids=expected_ids, require_complete_grid=True,
        )

        seen_rosters: set[tuple[str, str]] = set()
        condition_rows: list[dict[str, object]] = []
        for condition in conditions:
            strategy_id = (
                condition.matched_strategy_id
                if condition.method_id in BASELINES else condition.method_id
            )
            expected_budget = get_strategy(strategy_id).calls(n=self.n, k=self.k, T=self.T)
            if condition.call_budget != expected_budget:
                raise ValueError(
                    f"condition {condition.method_id}/{condition.dataset} budget "
                    f"{condition.call_budget} differs from paper formula {expected_budget}"
                )
            condition_rows.append({
                "dataset": condition.dataset, "method_id": condition.method_id,
                "model_mode": condition.model_mode, "seed": condition.seed,
                "prompt_ids": list(condition.prompt_ids), "call_budget": condition.call_budget,
                "matched_strategy_id": condition.matched_strategy_id,
            })
            roster_key = (condition.method_id, condition.model_mode)
            if roster_key in seen_rosters:
                continue
            seen_rosters.add(roster_key)
            if condition.method_id in BASELINES:
                self.registry.validate_baseline_assignment(condition, condition.method_id)
                continue
            strategy = StrategyId(condition.method_id)
            if strategy is StrategyId.S12 and not self.supports_jigsaw_facets:
                raise ValueError("S12 preflight requires an explicit Jigsaw facet prompt-view factory")
            blueprint = build_strategy_blueprint(
                strategy, n=self.n, k=self.k, T=self.T,
            )
            agent_ids = tuple(agent.identifier for agent in blueprint.strategy.agents)
            self.registry.resolve_models(condition, agent_ids)
            families = self.registry.resolve_model_families(condition, agent_ids)
            if condition.model_mode == "heterogeneous":
                for assignment in blueprint.strategy.assignments:
                    if assignment.role is not Role.JUDGE:
                        continue
                    authors = {
                        item.agent_id for item in blueprint.strategy.assignments
                        if item.round == assignment.round and item.role is Role.DECOMPOSER
                    }
                    if families[assignment.agent_id] in {families[author] for author in authors}:
                        raise ValueError(
                            f"judge {assignment.agent_id} shares a model family with an author in {strategy.value}"
                        )

        provider_hash = content_hash(self.campaign_manifest())
        conditions_hash = content_hash(condition_rows)
        return E1CampaignPreflightReport(
            dataset_snapshot_sha256=snapshot_sha256,
            provider_manifest_sha256=provider_hash,
            conditions_sha256=conditions_hash,
            condition_count=len(conditions),
            prompt_count=sum(len(ids) for ids in expected_ids.values()),
            provider_rosters_validated=len(seen_rosters),
            model_modes=("heterogeneous", "homogeneous"),
        )

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
    registry.validate_complete_roster(n=n, k=k)
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

    return DirectE1Runtime(
        executor=executor, method_factory=method_factory, registry=registry,
        n=n, k=k, T=T, supports_jigsaw_facets=prompt_view_factory is not None,
    )
