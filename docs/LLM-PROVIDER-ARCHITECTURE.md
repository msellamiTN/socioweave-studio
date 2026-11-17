# SOCIOWEAVE LLM Provider Architecture

**Status:** Initial provider abstraction implemented; hardware and model benchmark pending.  
**Scientific authority:** the Societies of Decomposers paper.  
**Implementation scope:** inference adapters; no change to social-strategy semantics.

## 1. Non-negotiable separation

The paper defines agents as a=(m_a,c_a,μ_a), and strategies as σ=(A,R,α,V,π,ω). A provider is an implementation detail of the model component m_a. It must not redefine:

- role assignment α, visibility V or anonymity;
- protocol steps and their order π;
- decision rule ω;
- call-cost and sequential-depth accounting;
- seeds, extraction union/deduplication or decomposition validity checks.

Every model invocation must be attributable to an agent, role, round, protocol step, provider, model identifier and generation configuration. This trace supports reproducibility and E1–E9 analysis.

## 2. Supported execution modes

### A. Local Hugging Face Transformers

Use this mode for controlled experiments, private prompt handling and Colab T4 sessions. The initial implementation is HuggingFaceLocalProvider.

| Tier | Model | Intended use | T4 posture | License |
|---|---|---|---|---|
| Default local baseline | Qwen/Qwen2.5-1.5B-Instruct | Smoke tests, extraction schema iteration and pilot runs | Conservative starting point; profile memory and quality | Apache-2.0 |
| Quality comparison | Qwen/Qwen2.5-7B-Instruct | Stronger local comparison for decomposition and critique | 4-bit NF4, batch size 1, bounded context; actual fit must be tested | Apache-2.0 |
| Additional comparison | Qwen/Qwen2.5-3B-Instruct | Intermediate model-size comparison | Profile peak memory in the actual runtime | License listed as other; inspect terms before use |

A T4 commonly has 16 GB VRAM in Colab, but available memory varies. Fit is not determined by parameter count alone: weights, KV cache, context length, generation length and allocator overhead all consume memory. No model is marked T4-validated until a notebook records GPU name, VRAM, package versions, load success, peak memory, tokens/s and failure behaviour.

For 7B, use Transformers + Accelerate + bitsandbytes 4-bit NF4, double quantization, FP16 compute and batch size 1 as the candidate configuration. This is a memory strategy, not a guarantee of a particular context window or throughput. Begin with a bounded input length such as 4,096 tokens and profile the paper's actual prompts.

### B. Hosted API providers

OpenAICompatibleProvider supports compatible chat-completion endpoints through the OpenAI Python SDK. Examples include the Hugging Face router at https://router.huggingface.co/v1, and compatible endpoints from Together, Groq, Cerebras, Fireworks, DeepInfra or a self-hosted vLLM endpoint, subject to current model and endpoint support.

Hugging Face Inference Providers can route a model to a serving provider or pin a provider. Availability, provider suffixes, price and rate limits must be checked at experiment start and stored in the run manifest. A model name alone is not enough to reproduce an API run.

Example configuration:

    from sociodec.providers import OpenAICompatibleProvider
    provider = OpenAICompatibleProvider(
        provider_name="huggingface-inference-providers",
        model="Qwen/Qwen2.5-7B-Instruct:fastest",
        base_url="https://router.huggingface.co/v1",
        api_key_env="HF_TOKEN",
    )

Use separate environment variables for credentials. Never commit API keys, tokens, personal access tokens or .env files.

## 3. Agent-to-model assignment

The paper's homogeneous condition uses the same underlying model identity; its heterogeneous condition uses different model families/identities. Different temperatures, seeds, prompts or role instructions do not make agents heterogeneous if they share the same underlying model. The executor M_E is fixed across compared strategies in the paper's experimental protocol.

## 4. Experimental reproducibility manifest

Every run should record:

- provider name, endpoint class and exact model ID/revision if available;
- local model and tokenizer revision, quantization settings;
- GPU name, total/free VRAM and peak memory for local inference;
- package versions, CUDA runtime and driver versions;
- temperature, top-p, max output tokens, stop sequences and seed;
- prompt template/version, role, round and protocol-step identifiers;
- call count, input/output tokens, latency, retries and provider errors;
- dataset, prompt ID, strategy ID, executor identity and experiment ID.

API providers may not guarantee deterministic output even at temperature zero. Record provider-side model/version metadata when exposed. Repeated seeds are controls, not a guarantee of identical output.

## 5. Paper settings are not global defaults

The paper's experimental settings include drafting temperature 0.7, critique/review temperature 0.2, decision operations temperature 0, JSON output, decomposition max tokens 1024, other operations max tokens 512, three agents, three reviewers where applicable, at most two rounds, and five seeds per configuration. These are paper protocol settings, not global provider defaults. Strategy-specific call counts, concurrency and protocol steps remain defined by the strategy catalogue.

Provider adapters must accept generation settings from the strategy/run configuration and must not silently override them. If a model lacks reliable constrained JSON decoding, validate output and record malformed-output and repair events rather than pretending constrained generation occurred.

## 6. Evaluation and scientific cautions

- Model size or reputation does not establish decomposition quality.
- Local and API runs are not directly comparable unless call/token budgets, prompt versions, executor, decoding parameters and task sets are controlled.
- Quantization can affect output quality; compare quantized and non-quantized variants where feasible.
- Do not treat agent count as independent evidence when agents share a model family; the paper analyses correlated judgements.
- V1, V2 and structural V5 are programmatically checkable; V3 and V4 require execution. A provider response is not a validity certificate.
- Latency, VRAM, token usage, retries and malformed JSON are supplementary engineering metrics, not substitutes for paper metrics.

## 7. Implementation status

Implemented: provider-neutral message/config/result types; local Hugging Face Transformers adapter with optional 4-bit NF4; OpenAI-compatible hosted API adapter; optional dependency groups.

Pending: provider registry/config loader and UI; secret manager integration; model capability discovery and preflight; request tracing and experiment manifest persistence; Colab T4 benchmark notebook; provider-specific structured-output adapters.

## References

- https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct
- https://huggingface.co/Qwen/Qwen2.5-7B-Instruct
- https://huggingface.co/docs/inference-providers/en/tasks/chat-completion
- https://huggingface.co/docs/inference-providers/en/index
- https://huggingface.co/docs/transformers/en/quantization/bitsandbytes
