# Core 21 — End-to-end provider-backed campaign integration

## Objective

Provide a concrete callable adapter from a resumable benchmark trial to the complete SOCIOWEAVE pipeline:

1. Build a declared Prompt (P=(x,ι)) from a benchmark item.
2. Run q requirement extractors and aggregate their outputs.
3. Generate two independent initial drafts.
4. Run Core 11 adaptive orchestration with the configured social-strategy executor.
5. Execute the selected decomposition with the fixed executor through Core 20.
6. Persist metrics, evidence metadata and provider traces through Core 19 resumable checkpoints.

## New implementation

- `engine/sociodec/provider_campaign.py`
  - `ProviderInitialDrafter`: two separate provider instances/calls, no peer history, typed candidate parsing.
  - `provider_extraction_runner`: q extractor execution and union/dedup.
  - `ProviderBackedTrialAdapter`: composes Core 11 and Core 20; conforms to `TrialContext -> TrialOutcome`.
  - `run_provider_backed_campaign`: delegates to the fsync-per-trial Core 19 checkpoint runner.
  - `CampaignPolicy`: explicit call budget and semantic selector flags.
- `engine/tests/test_provider_campaign.py`
- `docs/CORE-21-PROVIDER-BACKED-CAMPAIGN.md`
- `docs/CORE-21-TEST-REPORT.md`

## Scientific and semantic safeguards

- A benchmark item stores raw prompt text only. A mandatory PromptFactory supplies the declared interpretation; the factory must preserve exact prompt text.
- Initial drafts use separate provider instances and no shared history. Independence of underlying model errors is not inferred from distinct calls or model names.
- Extractor outputs remain hypotheses/explicit requirements as defined by the paper; no hidden requirements are silently promoted.
- Strategy adapter and composite strategy executor remain injected and must implement the paper's visibility, roles, decision rules and composition protocols.
- The same predeclared fixed executor ID is checked by Core 20.
- V3/V4 are reported only from supplied ExecutionRun evidence.
- Utility remains absent unless an independent scorer is supplied.
- Provider traces are optional metadata supplied by the configured trace collector. No raw prompt or completion text is written by this adapter's default trace path.

## Integration contract

The adapter can be passed directly to `run_provider_backed_campaign(config, examples, adapter, checkpoint_path)`. It uses Core 19's config/prompt/seed validation and fsync after each trial. A failed trial is recorded and not silently retried under the same configuration.

## What remains externally configured

- Real provider credentials and model deployments.
- A reviewed PromptFactory for each benchmark domain.
- q independently configured extractors.
- A ConcreteStrategyAdapter with domain prompt-view factory and explicit composite executors for C8/C1/C2.
- A fixed executor and independent hard-constraint verifier.
- Optional utility scorer and provider trace supplier.

## Limitations

This core is an integration seam, not proof that a live hosted campaign has been run. No benchmark results, strategy superiority, verifier independence or E1–E9 findings are claimed. Real-provider smoke tests and a Colab pilot remain separate acceptance gates.
