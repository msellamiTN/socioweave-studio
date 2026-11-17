"""Provider-neutral inference contract.

Providers implement transport and model loading only. They must not alter
SocioDec protocol order, visibility, decision rules, seeds or paper metrics.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str
    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant"}:
            raise ValueError(f"Unsupported chat role: {self.role}")
        if not isinstance(self.content, str):
            raise TypeError("ChatMessage.content must be a string")

@dataclass(frozen=True, slots=True)
class GenerationConfig:
    temperature: float = 0.0
    max_new_tokens: int = 512
    top_p: float = 1.0
    seed: int | None = None
    stop: tuple[str, ...] = ()
    response_format: str | None = None
    def __post_init__(self) -> None:
        if self.temperature < 0:
            raise ValueError("temperature must be >= 0")
        if not 0.0 < self.top_p <= 1.0:
            raise ValueError("top_p must be in (0, 1]")
        if self.max_new_tokens < 1:
            raise ValueError("max_new_tokens must be >= 1")

@dataclass(frozen=True, slots=True)
class GenerationResult:
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    request_id: str | None = None
    raw_metadata: dict[str, object] = field(default_factory=dict)

@runtime_checkable
class LLMProvider(Protocol):
    @property
    def provider_name(self) -> str: ...
    @property
    def model_name(self) -> str: ...
    def generate(self, messages: list[ChatMessage],
                 config: GenerationConfig | None = None) -> GenerationResult: ...
