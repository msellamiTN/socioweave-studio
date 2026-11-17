"""Adapter for OpenAI-compatible hosted chat-completion APIs."""
from __future__ import annotations
import os
from .base import ChatMessage, GenerationConfig, GenerationResult

class OpenAICompatibleProvider:
    def __init__(self, *, model: str, base_url: str, api_key_env: str,
                 provider_name: str = "openai-compatible",
                 timeout_seconds: float = 120.0) -> None:
        if not model.strip() or not base_url.strip() or not api_key_env.strip():
            raise ValueError("model, base_url and api_key_env are required")
        self._model, self._base_url = model, base_url.rstrip("/")
        self._api_key_env, self._provider_name = api_key_env, provider_name
        self._timeout = timeout_seconds

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, messages: list[ChatMessage],
                 config: GenerationConfig | None = None) -> GenerationResult:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install API dependencies: pip install -e '.[api]'") from exc
        api_key = os.getenv(self._api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API credential in {self._api_key_env}")
        cfg = config or GenerationConfig()
        client = OpenAI(api_key=api_key, base_url=self._base_url, timeout=self._timeout)
        response = client.chat.completions.create(
            model=self._model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=cfg.temperature, top_p=cfg.top_p,
            max_tokens=cfg.max_new_tokens, seed=cfg.seed,
            stop=list(cfg.stop) or None,
        )
        choice, usage = response.choices[0], response.usage
        return GenerationResult(
            text=choice.message.content or "", provider=self._provider_name,
            model=self._model,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            finish_reason=choice.finish_reason,
            request_id=getattr(response, "id", None),
            raw_metadata={"system_fingerprint": getattr(response, "system_fingerprint", None)},
        )
