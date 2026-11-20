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


## Table 13 model-family provenance gate

The paper labels the agent families abstractly as MA, MB and MC; it does not
name concrete model products. The runtime therefore does not invent those
identities. The operator must declare, for every assigned model, a family ID,
provider organization, weight-access class, exact model revision and access
date. Open-weight entries also require a size label.

Before a direct E1 runtime is assembled, the registry now requires:

- a complete agent assignment roster for all thirteen strategies and six
  baselines in both model modes;
- one exact model identity/family across the homogeneous MA roster;
- exactly three heterogeneous agent families, three distinct provider
  organizations, one closed-weight API model and two open-weight models with
  different declared size labels;
- immutable 40-character commit revisions for locally loaded Hugging Face
  models, passed to both tokenizer and model loading; the exact API model ID
  must equal its declared revision;
- at least two distinct families for two-agent strategy rosters and three
  families for rosters with at least three agents;
- judge-family separation from the authors being judged, including the
  independent judge in the multi-agent-debate baseline.

The registry records exact family/provider/revision/access-date metadata in
its non-secret assignment manifest. These checks establish consistency of
operator declarations and routing configuration; they do not independently
verify that a provider's claimed family, organization, weight status, or
revision is truthful. The paper requires exact model versions and access
dates to be reported with results. No concrete MA/MB/MC product identities
are assumed in this repository.
