# E1 provider assignment profile

The provider registry resolves direct E1 model assignments by model mode and
exact agent identifier.

## Configuration contract

- Declare separate homogeneous and heterogeneous agent rosters.
- Every strategy or baseline agent must resolve; missing roles fail closed.
- Homogeneous rosters use exactly one model identity.
- Heterogeneous rosters use at least two model identities.
- The fixed executor uses a separately configured provider and is outside the
  method roster and method-call budget.
- Hosted credentials are referenced by environment-variable name only.
- Provider instances are cached by model mode and agent ID.

Local model example:

    ProviderSpec(backend="huggingface-local",
                 model_id="Qwen/Qwen2.5-1.5B-Instruct",
                 load_in_4bit=True)

Hosted model example:

    ProviderSpec(backend="openai-compatible", model_id="provider/model-id",
                 base_url="https://api.example.invalid/v1",
                 api_key_env="E1_MODEL_API_KEY")

Use resolve_models as the DirectProtocolStrategyAdapter model resolver,
invoker_factory(condition) as its per-agent invoker factory, and
baseline_provider_resolver as the DirectBaselineAdapter provider resolver.

## Scope and non-claims

This profile adds provider assignment and routing only. It does not implement
the fixed executor, infer paper model identities, validate provider licenses,
perform live API calls, or claim E1 measurements. Freeze assignments in the
campaign preregistration before benchmark execution.
