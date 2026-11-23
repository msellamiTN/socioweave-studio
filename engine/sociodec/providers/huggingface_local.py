"""Local Hugging Face Transformers adapter for constrained GPUs (e.g. T4)."""
from __future__ import annotations
from .base import ChatMessage, GenerationConfig, GenerationResult

class HuggingFaceLocalProvider:
    def __init__(self, *, model_id: str = "Qwen/Qwen2.5-1.5B-Instruct",
                 revision: str | None = None,
                 load_in_4bit: bool = False, max_input_tokens: int = 4096) -> None:
        self._model_id, self._revision, self._load_in_4bit = model_id, revision, load_in_4bit
        self._max_input_tokens = max_input_tokens
        self._tokenizer = self._model = None

    @property
    def provider_name(self) -> str:
        return "huggingface-local"

    @property
    def model_name(self) -> str:
        return self._model_id

    def load(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("Install local dependencies: pip install -e '.[local]'") from exc
        kwargs = {"device_map": "auto"}
        if self._load_in_4bit:
            if not torch.cuda.is_available():
                raise RuntimeError("4-bit bitsandbytes loading requires CUDA")
            from transformers import BitsAndBytesConfig
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.float16,
            )
        else:
            kwargs["torch_dtype"] = torch.float16 if torch.cuda.is_available() else torch.float32
        self._tokenizer = AutoTokenizer.from_pretrained(self._model_id, revision=self._revision)
        self._model = AutoModelForCausalLM.from_pretrained(
            self._model_id, revision=self._revision, **kwargs,
        )
        self._model.eval()

    def generate(self, messages: list[ChatMessage],
                 config: GenerationConfig | None = None) -> GenerationResult:
        if self._model is None or self._tokenizer is None:
            self.load()
        import torch
        cfg = config or GenerationConfig()
        serialised = [{"role": m.role, "content": m.content} for m in messages]
        encoded = self._tokenizer.apply_chat_template(
            serialised, tokenize=True, add_generation_prompt=True,
            return_tensors="pt", return_dict=True,
        )
        input_length = int(encoded["input_ids"].shape[-1])
        if input_length > self._max_input_tokens:
            raise ValueError(f"Input has {input_length} tokens; limit is {self._max_input_tokens}")
        device = next(self._model.parameters()).device
        encoded = {key: value.to(device) for key, value in encoded.items()}
        kwargs = {"max_new_tokens": cfg.max_new_tokens,
                  "do_sample": cfg.temperature > 0,
                  "pad_token_id": self._tokenizer.eos_token_id}
        if cfg.temperature > 0:
            kwargs.update(temperature=cfg.temperature, top_p=cfg.top_p)
        if cfg.seed is not None:
            torch.manual_seed(cfg.seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(cfg.seed)
        with torch.inference_mode():
            output = self._model.generate(**encoded, **kwargs)
        new_tokens = output[0, input_length:]
        return GenerationResult(
            text=self._tokenizer.decode(new_tokens, skip_special_tokens=True),
            provider=self.provider_name, model=self._model_id,
            input_tokens=input_length, output_tokens=int(new_tokens.shape[-1]),
            finish_reason="stop",
        )
