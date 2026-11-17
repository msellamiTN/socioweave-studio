# Core 19 — Provider-backed execution, tracing and resumable campaigns

## Status

Implementation submitted for CI acceptance. Software tests validate provider bridging and checkpoint mechanics; they do not validate model quality, strategy effectiveness, or the live Colab GPU environment.

## Objective

Connect real LLM providers to the existing SocioDec protocol runtime without changing paper-defined strategy semantics, and make long-running campaigns recoverable after interruption.

## Components

- `sociodec.provider_runtime.ProviderProtocolInvoker`: implements the runtime's `ProtocolInvoker` contract using the provider-neutral `LLMProvider`.
- `protocol_messages`: serialises only the `ProtocolContext` supplied by the visibility-aware runtime. It cannot retrieve hidden peer outputs.
- `ProviderCallTrace`: records provider/model identity, agent/role/action, round/stage, generation settings, seed, token counts, latency, request ID, and SHA-256 hashes of request payload and completion. Raw prompt/completion text is not persisted by default.
- `sociodec.resumable.run_resumable_campaign`: append-only JSONL checkpointing, fsync per trial, strict config/prompt/seed validation, duplicate detection, and skip of already completed successes and failures.

## Integration recipe

1. Construct `OpenAICompatibleProvider` or `HuggingFaceLocalProvider`.
2. Wrap it in `ProviderProtocolInvoker`.
3. Supply that invoker to `ConcreteStrategyAdapter`.
4. Supply a typed `StrategyDecoder` and, for composite plans C8/C2/C1, an explicit composite executor.
5. Supply the resulting adapter, extraction runner and two independent initial drafters to `run_adaptive`.
6. Capture `invoker.trace_dicts()` as `TrialOutcome.provider_trace`; retain the strategy run ID and exact provider/model identifiers.
7. Use `run_resumable_campaign` for trial-level checkpointing.

The provider bridge is a protocol invoker, not a semantic decoder. Model completions must pass the existing typed protocol decoder and decision assembly. The five candidate design-space cells are not promoted to established strategies.

## Fixed executor and V3/V4

The fixed executor must be configured independently from decomposition agents and held constant across compared strategies. Each executor run must be converted to the existing `ExecutionRun` contract and passed to Core 15 finalization. Without that evidence, V3/V4 remain `NOT_EVALUATED`. A model-generated assertion that a constraint is satisfied is evidence supplied by the verifier, not an independent proof of semantic truth.

## Experimental protocol safeguards

- Keep paper settings and executor fixed within each paired comparison.
- Record provider, exact model identifier, model revision where available, generation config, request ID, usage, latency, seed and errors.
- Do not equate a seed with deterministic hosted inference.
- Never mix synthetic demo observations with actual provider runs.
- Failed trials remain in the denominator and are checkpointed.
- Changing config or prompt bytes invalidates resume against the existing checkpoint.
- Run a small pilot before scaling to the paper's E1–E9 campaign.
- Use exact/permutation sensitivity analysis for small paired samples; the Core 17 normal-approximation Wilcoxon result must not be represented as exact.

## Acceptance tests

- Provider bridge maps role/action/context and generation settings correctly.
- Trace captures model identity, usage, latency, request ID and hashes without storing raw text.
- Visibility-limited history is the only history serialised.
- Empty completions fail closed.
- Resume skips completed trials, validates config and prompt hashes, rejects duplicate keys and preserves failed trials.
- Full engine suite passes on the exact code commit.

## Limitations

- No live provider call or benchmark campaign is claimed by the unit tests.
- A typed strategy decoder and explicit composition executor remain required dependencies.
- A fixed executor adapter and independent verifier must be configured by the campaign; Core 19 does not treat LLM self-attestation as proof of V3/V4.
- Provider usage fields may be absent or provider-specific.
- Colab T4 memory, model compatibility, quantisation and throughput require a live runtime test.
- This core provides trial-level resume, not distributed multi-worker locking. Run one writer per checkpoint file.
