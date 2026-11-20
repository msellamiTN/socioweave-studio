"""Explicit, auditable provider routing and model-family provenance for direct E1."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Mapping

from sociodec.e1_protocol import E1Condition
from sociodec.provider_runtime import ProviderProtocolInvoker
from sociodec.providers.base import LLMProvider
from sociodec.providers.huggingface_local import HuggingFaceLocalProvider
from sociodec.providers.openai_compatible import OpenAICompatibleProvider


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    backend: str
    model_id: str
    base_url: str | None = None
    api_key_env: str | None = None
    provider_name: str = "openai-compatible"
    load_in_4bit: bool = False
    max_input_tokens: int = 4096
    timeout_seconds: float = 120.0
    # Operator-declared provenance; mandatory when an E1 campaign is validated.
    family_id: str | None = None
    provider_org: str | None = None
    weight_access: str | None = None
    model_size: str | None = None
    model_revision: str | None = None
    access_date: str | None = None

    def __post_init__(self) -> None:
        if self.backend not in {"huggingface-local", "openai-compatible"}:
            raise ValueError("unsupported provider backend")
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id must be non-empty")
        if self.max_input_tokens < 1 or self.timeout_seconds <= 0:
            raise ValueError("provider limits must be positive")
        if self.backend == "openai-compatible" and (
            not self.base_url or not self.base_url.strip()
            or not self.api_key_env or not self.api_key_env.strip()
        ):
            raise ValueError("hosted providers require base_url and api_key_env")
        if self.backend == "huggingface-local" and (self.base_url or self.api_key_env):
            raise ValueError("local providers must not declare hosted endpoint credentials")
        provenance = (
            self.family_id, self.provider_org, self.weight_access,
            self.model_revision, self.access_date,
        )
        if any(value is not None for value in provenance) or self.model_size is not None:
            if any(not isinstance(value, str) or not value.strip() for value in provenance):
                raise ValueError("model provenance requires family_id, provider_org, weight_access, model_revision and access_date")
            if self.weight_access not in {"closed-weight", "open-weight"}:
                raise ValueError("weight_access must be closed-weight or open-weight")
            if self.weight_access == "open-weight" and (
                not isinstance(self.model_size, str) or not self.model_size.strip()
            ):
                raise ValueError("open-weight models require a non-empty model_size label")
            if self.weight_access == "closed-weight" and self.model_size is not None:
                raise ValueError("model_size is only declared for open-weight model families")
            try:
                date.fromisoformat(self.access_date)
            except ValueError as exc:
                raise ValueError("access_date must use ISO YYYY-MM-DD format") from exc
            if self.weight_access == "closed-weight" and self.backend != "openai-compatible":
                raise ValueError("closed-weight E1 models must be accessed through the API backend")

    def provenance_dict(self) -> dict[str, str]:
        """Return non-secret operator-declared model provenance."""
        required = {
            "family_id": self.family_id,
            "provider_org": self.provider_org,
            "weight_access": self.weight_access,
            "model_revision": self.model_revision,
            "access_date": self.access_date,
        }
        if any(value is None for value in required.values()):
            raise ValueError("complete model provenance is required for E1")
        result = {key: str(value) for key, value in required.items()}
        if self.model_size is not None:
            result["model_size"] = self.model_size
        return result


ProviderBuilder = Callable[[ProviderSpec], LLMProvider]


def _build_provider(spec: ProviderSpec) -> LLMProvider:
    if spec.backend == "huggingface-local":
        return HuggingFaceLocalProvider(
            model_id=spec.model_id, load_in_4bit=spec.load_in_4bit,
            max_input_tokens=spec.max_input_tokens,
        )
    return OpenAICompatibleProvider(
        model=spec.model_id, base_url=spec.base_url or "",
        api_key_env=spec.api_key_env or "", provider_name=spec.provider_name,
        timeout_seconds=spec.timeout_seconds,
    )


class E1ProviderRegistry:
    """Resolve exact agent assignments and validate Table 13 model provenance."""

    def __init__(
        self, *, assignments: Mapping[str, Mapping[str, ProviderSpec]],
        executor: ProviderSpec, provider_builder: ProviderBuilder = _build_provider,
        draft_temperature: float = 0.7, critique_temperature: float = 0.2,
        decision_temperature: float = 0.0, max_tokens_decomposition: int = 1024,
        max_tokens_other: int = 512,
    ) -> None:
        if set(assignments) != {"homogeneous", "heterogeneous"}:
            raise ValueError("assignments must declare homogeneous and heterogeneous modes")
        if any(not roster for roster in assignments.values()):
            raise ValueError("each model mode requires a non-empty agent roster")
        self.assignments = {mode: dict(roster) for mode, roster in assignments.items()}
        self.executor_spec = executor
        self.provider_builder = provider_builder
        self._providers: dict[tuple[str, str], LLMProvider] = {}
        self._executor_provider: LLMProvider | None = None
        self._temperatures = (draft_temperature, critique_temperature, decision_temperature)
        self._token_limits = (max_tokens_decomposition, max_tokens_other)
        if any(x < 0 for x in self._temperatures) or any(x < 1 for x in self._token_limits):
            raise ValueError("invalid generation configuration")

    def _spec(self, mode: str, agent_id: str) -> ProviderSpec:
        try:
            return self.assignments[mode][agent_id]
        except KeyError as exc:
            raise ValueError(
                f"No provider assignment for model_mode={mode!r}, agent_id={agent_id!r}"
            ) from exc

    @staticmethod
    def _require_provenance(spec: ProviderSpec, label: str) -> dict[str, str]:
        try:
            return spec.provenance_dict()
        except ValueError as exc:
            raise ValueError(f"Missing or invalid E1 model provenance for {label}: {exc}") from exc

    def validate_family_catalogue(self) -> dict[str, ProviderSpec]:
        """Validate MA/MB/MC as three distinct provider families.

        The values are declarations supplied by the experiment operator. This
        validates internal consistency, not external truth of provider claims.
        """
        family_specs: dict[str, ProviderSpec] = {}
        family_signatures: dict[str, tuple[str, ...]] = {}
        for agent_id, spec in self.assignments["heterogeneous"].items():
            provenance = self._require_provenance(spec, f"heterogeneous/{agent_id}")
            family_id = provenance["family_id"]
            signature = (
                provenance["provider_org"], provenance["weight_access"],
                provenance.get("model_size", ""), provenance["model_revision"],
                provenance["access_date"], spec.model_id, spec.backend,
            )
            previous = family_signatures.get(family_id)
            if previous is not None and previous != signature:
                raise ValueError(
                    f"heterogeneous family {family_id!r} maps to inconsistent provider/model revisions"
                )
            family_signatures[family_id] = signature
            family_specs[family_id] = spec

        if len(family_specs) != 3:
            raise ValueError(
                f"Table 13 requires exactly three declared agent model families; found {len(family_specs)}"
            )
        provenances = {family: self._require_provenance(spec, family) for family, spec in family_specs.items()}
        providers = [item["provider_org"] for item in provenances.values()]
        if len(set(providers)) != 3:
            raise ValueError("the three E1 model families must declare three distinct provider organizations")
        closed = [family for family, item in provenances.items() if item["weight_access"] == "closed-weight"]
        opened = [family for family, item in provenances.items() if item["weight_access"] == "open-weight"]
        if len(closed) != 1 or len(opened) != 2:
            raise ValueError("Table 13 requires one closed-weight API model and two open-weight models")
        open_sizes = [provenances[family].get("model_size") for family in opened]
        if len(set(open_sizes)) != 2:
            raise ValueError("the two open-weight model families must declare different size labels")
        self._require_provenance(self.executor_spec, "fixed executor ME")
        return family_specs

    def resolve_models(self, condition: E1Condition, agent_ids: tuple[str, ...]) -> dict[str, str]:
        if not agent_ids or len(agent_ids) != len(set(agent_ids)):
            raise ValueError("agent_ids must be non-empty and unique")
        models = {agent: self._spec(condition.model_mode, agent).model_id for agent in agent_ids}
        distinct = set(models.values())
        if condition.model_mode == "homogeneous" and len(distinct) != 1:
            raise ValueError("homogeneous E1 roster must use exactly one model identity")
        if condition.model_mode == "heterogeneous" and len(distinct) < min(3, len(agent_ids)):
            raise ValueError("heterogeneous E1 roster must use up to three distinct model identities")
        return models

    def resolve_model_families(self, condition: E1Condition, agent_ids: tuple[str, ...]) -> dict[str, str]:
        self.validate_family_catalogue()
        families = {
            agent: self._require_provenance(self._spec(condition.model_mode, agent), agent)["family_id"]
            for agent in agent_ids
        }
        distinct = set(families.values())
        required = 1 if condition.model_mode == "homogeneous" else min(3, len(agent_ids))
        if len(distinct) < required:
            raise ValueError(
                f"{condition.model_mode} roster requires at least {required} distinct model families"
            )
        if condition.model_mode == "homogeneous" and len({
            self._spec(condition.model_mode, agent).model_id for agent in agent_ids
        }) != 1:
            raise ValueError("homogeneous E1 roster must use one exact model identity")
        return families

    def validate_baseline_assignment(self, condition: E1Condition, baseline_id: str) -> dict[str, str]:
        rosters = {
            "single_plan_and_solve": ("single-decomposer",),
            "single_self_refinement": ("self-refiner",),
            "single_self_consistency": ("self-consistency-sampler",),
            "decomposer_plus_evaluator": ("decomposer", "separate-evaluator"),
            "multi_agent_debate": ("debater-1", "debater-2", "independent-judge"),
            "nominal_multi_agent": ("nominal-member-1", "nominal-member-2", "nominal-member-3"),
        }
        try:
            agent_ids = rosters[baseline_id]
        except KeyError as exc:
            raise ValueError(f"Unknown E1 baseline: {baseline_id}") from exc
        families = self.resolve_model_families(condition, agent_ids)
        if baseline_id == "multi_agent_debate" and families["independent-judge"] in {
            families["debater-1"], families["debater-2"]
        }:
            raise ValueError("multi-agent debate judge must use a family distinct from both authors")
        return families

    def provider_for(self, condition: E1Condition, agent_id: str) -> LLMProvider:
        spec = self._spec(condition.model_mode, agent_id)
        key = (condition.model_mode, agent_id)
        if key not in self._providers:
            provider = self.provider_builder(spec)
            if provider.model_name != spec.model_id:
                raise ValueError("provider_builder returned a provider with a different model identity")
            self._providers[key] = provider
        return self._providers[key]

    def baseline_provider_resolver(self, condition: E1Condition, agent_id: str) -> LLMProvider:
        return self.provider_for(condition, agent_id)

    def invoker_factory(self, condition: E1Condition):
        def build(agent, seed: int) -> ProviderProtocolInvoker:
            return ProviderProtocolInvoker(
                self.provider_for(condition, agent.identifier),
                draft_temperature=self._temperatures[0],
                critique_temperature=self._temperatures[1],
                decision_temperature=self._temperatures[2],
                max_tokens_decomposition=self._token_limits[0],
                max_tokens_other=self._token_limits[1], seed=seed,
            )
        return build

    def executor_provider(self) -> LLMProvider:
        if self._executor_provider is None:
            provider = self.provider_builder(self.executor_spec)
            if provider.model_name != self.executor_spec.model_id:
                raise ValueError("executor provider model identity mismatch")
            self._executor_provider = provider
        return self._executor_provider

    def assignment_manifest(self, condition: E1Condition, agent_ids: tuple[str, ...]) -> dict[str, object]:
        models = self.resolve_models(condition, agent_ids)
        families = self.resolve_model_families(condition, agent_ids)
        provenance = {
            agent: self._require_provenance(self._spec(condition.model_mode, agent), agent)
            for agent in agent_ids
        }
        return {
            "model_mode": condition.model_mode,
            "method_id": condition.method_id,
            "agent_model_ids": models,
            "agent_model_families": families,
            "agent_model_provenance": provenance,
            "distinct_method_models": sorted(set(models.values())),
            "executor_model_id": self.executor_spec.model_id,
            "executor_backend": self.executor_spec.backend,
            "executor_provenance": self._require_provenance(self.executor_spec, "fixed executor ME"),
        }
