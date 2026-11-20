# Direct E1 runtime assembly

`build_direct_e1_runtime` connects the existing components into the
`DirectE1CampaignRunner` constructor contract:

- `E1ProviderRegistry` supplies exact model routing for method agents.
- `DirectProtocolStrategyAdapter` runs registered paper strategies directly.
- `DirectBaselineAdapter` runs the six versioned baseline profiles.
- `ProviderFixedExecutor` is created once and shared across all conditions.

The returned `DirectE1Runtime.method_factory` can be passed directly to
`DirectE1CampaignRunner`, together with `runtime.executor`.

The runtime assembly deliberately requires an explicit prompt-view factory
for S12/Jigsaw. It does not infer facets or invent a partition from domain
labels. Model rosters and executor identity remain operator-supplied and must
be frozen before a campaign.

This is wiring and test coverage, not a live benchmark campaign. Dataset
provenance, prompt interpretation/extraction, model revision pinning,
human annotation, and actual T4 execution remain separate prerequisites.


## Reproducibility and heterogeneity boundary

`DirectE1Runtime.assignment_manifest(condition, agent_ids)` exposes the
non-secret agent model IDs, model mode, executor model/backend and executor ID
so the caller can persist them alongside the campaign configuration. It does
not expose API keys. The caller must persist this manifest before execution.

The current `heterogeneous` guard verifies at least two distinct model
identifiers in the roster. It does **not** independently verify distinct model
families, training lineages, or provider organizations. A heterogeneous
condition must not be described as a three-family comparison until those
family identities are explicitly declared and validated in a separate
provider/model provenance layer. No live calls are made by the assembly tests.
