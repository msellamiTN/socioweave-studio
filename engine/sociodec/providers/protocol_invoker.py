"""Provider-backed invocation boundary for the visibility-aware protocol runtime.

The runtime supplies a filtered ProtocolContext. This adapter serializes only
that context and routes by the agent's declared model_id. It does not alter
visibility, protocol order, seeds, or decision semantics.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Mapping, TYPE_CHECKING

from sociodec.models.strategy import Agent
if TYPE_CHECKING:
    from sociodec.runtime import ProtocolContext, ProtocolStep
from .base import ChatMessage, GenerationConfig, LLMProvider


@dataclass(frozen=True, slots=True)
class ProtocolCallTrace:
    agent_id: str
    model_id: str
    model_family: str
    provider: str
    returned_model: str
    action: str
    request_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float
    input_sha256: str
    output_sha256: str


class ProviderProtocolInvoker:
    """Route each protocol step to the provider selected by Agent.model_id.

    Model-family labels are explicit configuration, not inferred from model
    names. Distinct model versions can therefore be correctly grouped under
    one family for diversity accounting.
    """

    def __init__(
        self,
        providers: Mapping[str, LLMProvider],
        *,
        model_families: Mapping[str, str],
        generation: GenerationConfig | None = None,
    ) -> None:
        if not providers:
            raise ValueError("At least one model_id -> provider mapping is required")
        if set(providers) != set(model_families):
            raise ValueError("Every configured model_id must have exactly one model family")
        if any(not key.strip() for key in providers):
            raise ValueError("Model identifiers must be non-empty")
        if any(not value.strip() for value in model_families.values()):
            raise ValueError("Model-family labels must be non-empty")
        self.providers = dict(providers)
        self.model_families = dict(model_families)
        self.generation = generation or GenerationConfig()
        self.traces: list[ProtocolCallTrace] = []

    def invoke(
        self,
        agent: Agent,
        step: ProtocolStep,
        context: ProtocolContext,
    ) -> str:
        try:
            provider = self.providers[agent.model_id]
            family = self.model_families[agent.model_id]
        except KeyError:
            raise ValueError(
                f"No provider/model-family configuration for model_id {agent.model_id!r}"
            ) from None

        payload = {
            "agent_id": context.agent_id,
            "role": context.role.value,
            "action": context.action,
            "agent_context": context.agent_context,
            "prompt_view": context.prompt_view,
            "input_ref": context.input_ref,
            "input_content": context.input_content,
            "hypotheses": [
                {
                    "type": item.type.value,
                    "domain": item.domain,
                    "statement": item.statement,
                    "rationale": item.rationale,
                }
                for item in context.hypotheses
            ],
            "visible_history": [
                {
                    "step_index": item.step_index,
                    "author": item.author,
                    "action": item.action,
                    "text": item.text,
                    "from_seed": item.from_seed,
                }
                for item in context.visible_history
            ],
        }
        user_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        messages = [
            ChatMessage(
                "system",
                "You are one agent in a formal multi-agent decomposition protocol. "
                "Follow the assigned role and action. Use only the supplied prompt "
                "view, input, and visible history. Return the structured output "
                "required for this action; do not claim access to hidden agents."
            ),
            ChatMessage("user", user_text),
        ]
        started = time.perf_counter()
        result = provider.generate(messages, self.generation)
        elapsed = (time.perf_counter() - started) * 1000
        if not result.text.strip():
            raise ValueError("Provider returned empty protocol output")
        self.traces.append(ProtocolCallTrace(
            agent.identifier, agent.model_id, family, result.provider,
            result.model, step.action.value, result.request_id,
            result.input_tokens, result.output_tokens, round(elapsed, 3),
            hashlib.sha256(user_text.encode()).hexdigest(),
            hashlib.sha256(result.text.encode()).hexdigest(),
        ))
        return result.text
