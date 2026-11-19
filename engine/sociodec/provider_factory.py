"""Explicit, auditable provider routing for direct E1 conditions."""
from __future__ import annotations
from dataclasses import dataclass
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

    def __post_init__(self) -> None:
        if self.backend not in {"huggingface-local", "openai-compatible"}:
            raise ValueError("unsupported provider backend")
        if not self.model_id.strip():
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

ProviderBuilder = Callable[[ProviderSpec], LLMProvider]

def _build_provider(spec: ProviderSpec) -> LLMProvider:
    if spec.backend == "huggingface-local":
        return HuggingFaceLocalProvider(model_id=spec.model_id,
            load_in_4bit=spec.load_in_4bit, max_input_tokens=spec.max_input_tokens)
    return OpenAICompatibleProvider(model=spec.model_id, base_url=spec.base_url or "",
        api_key_env=spec.api_key_env or "", provider_name=spec.provider_name,
        timeout_seconds=spec.timeout_seconds)

class E1ProviderRegistry:
    """Resolve exact agent assignments and create instrumented invokers."""
    def __init__(self, *, assignments: Mapping[str, Mapping[str, ProviderSpec]],
        executor: ProviderSpec, provider_builder: ProviderBuilder = _build_provider,
        draft_temperature: float = 0.7, critique_temperature: float = 0.2,
        decision_temperature: float = 0.0, max_tokens_decomposition: int = 1024,
        max_tokens_other: int = 512) -> None:
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
            raise ValueError(f"No provider assignment for model_mode={mode!r}, agent_id={agent_id!r}") from exc

    def resolve_models(self, condition: E1Condition, agent_ids: tuple[str, ...]) -> dict[str, str]:
        if not agent_ids or len(agent_ids) != len(set(agent_ids)):
            raise ValueError("agent_ids must be non-empty and unique")
        models = {agent: self._spec(condition.model_mode, agent).model_id for agent in agent_ids}
        distinct = set(models.values())
        if condition.model_mode == "homogeneous" and len(distinct) != 1:
            raise ValueError("homogeneous E1 roster must use exactly one model identity")
        if condition.model_mode == "heterogeneous" and len(distinct) < 2:
            raise ValueError("heterogeneous E1 roster must use at least two model identities")
        return models

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
            return ProviderProtocolInvoker(self.provider_for(condition, agent.identifier),
                draft_temperature=self._temperatures[0],
                critique_temperature=self._temperatures[1],
                decision_temperature=self._temperatures[2],
                max_tokens_decomposition=self._token_limits[0],
                max_tokens_other=self._token_limits[1], seed=seed)
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
        return {"model_mode": condition.model_mode, "method_id": condition.method_id,
            "agent_model_ids": models, "distinct_method_models": sorted(set(models.values())),
            "executor_model_id": self.executor_spec.model_id, "executor_backend": self.executor_spec.backend}
