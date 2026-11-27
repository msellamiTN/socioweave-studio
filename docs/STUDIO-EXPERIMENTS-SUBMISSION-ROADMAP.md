# SOCIOWEAVE Studio and Experiments — Delivery Roadmap

**Baseline commit:** `d6ffd202c99ce9752404375c0abfbbe0d2e4309c`  
**Purpose:** close the product and empirical-evidence gaps required to submit *Societies of Decomposers*.  
**Status:** roadmap; no new run-launch capability or scientific result is implied by this document.

## 1. Product contract

SOCIOWEAVE Studio is the researcher's control, audit and evidence plane. The SocioDec Engine remains the sole authority for strategy semantics, protocol execution, decomposition validation and metric definitions.

The Studio must never make an experiment appear scientifically complete merely because configuration validation or a software test passed. Every screen and exported artifact must distinguish:

- `CODE_CI_ONLY`: software tests passed; no empirical campaign evidence.
- `PREFLIGHT_BLOCKED`: one or more prerequisites are absent or invalid.
- `PREFLIGHT_VALIDATED`: declared configuration and local inputs pass the checks actually performed; this is not a license approval or scientific readiness attestation.
- `READY_FOR_OPERATOR_APPROVAL`: all machine-checkable gates pass; explicit operator authorization remains required.
- `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`: actual execution lifecycle states.
- `ANALYSIS_PENDING`, `ANALYSIS_COMPLETE`: analysis lifecycle states.
- `SCIENTIFICALLY_REPORTABLE`: only after protocol, provenance, annotation, execution, metric applicability and statistical review gates pass.

No status may be promoted by UI logic alone. State transitions must be backed by API-side evidence and immutable records.

## 2. Existing baseline (verified in repository)

### Studio already present
- FastAPI v1 health, capabilities, strategy and dataset catalogues.
- Strategy configuration preview and paper-call-budget calculation.
- Local dataset snapshot / condition-grid preflight.
- Engine-backed provider campaign configuration preflight.
- Registered S12 policy identity and SHA-256 binding.
- Static same-origin browser UI for configuration and preflight.
- Explicit zero-provider-call boundary.

### Studio capabilities intentionally absent
- No `POST /runs` launch endpoint or worker.
- No persistent run/job store, event stream, cancellation or resume API.
- No trace explorer or results workspace.
- No authentication/authorization or multi-user isolation.
- No production-grade filesystem sandboxing, secret management or deployment hardening.

### Experiment/evaluation components already present
- Typed trial/configuration primitives, deterministic seed derivation and JSONL records.
- Dataset registry and strict local snapshot loader.
- Provider-backed campaign configuration and fixed-executor contracts.
- Metric/statistical functions and campaign aggregation / paired comparison utilities.
- Colab runtime notebooks, including a provider adapter boundary that intentionally refuses to fabricate results.
- Dataset source-intake audit and freeze-manifest requirements.

### Scientific status
- No completed E1–E9 benchmark campaign is established by these components.
- Dataset source, rights, exact revision, split/selection and annotation gates remain unresolved.
- The 60-prompt smart-administration artifact and practitioner-review evidence remain necessary for the complete five-dataset protocol.
- Software CI, T4 smoke tests, synthetic plotting tests and configuration preflights are engineering evidence only.

## 3. Target Studio information architecture

1. **Overview** — active campaign, pinned commit, evidence state, outstanding gates, recent runs.
2. **Datasets** — source identity, release/revision, split, selection protocol, eligible population, selected IDs, rights review, annotations, reference schema, file/hash validation.
3. **Experiment Builder** — paper experiment (E1–E9), strategy/baseline roster, model mode, agent/provider assignments, n/k/T, seeds/repeats, generation settings, fixed executor, call/token/time budgets.
4. **Preflight** — machine checks, operator attestations, blockers, warnings, evidence references, config and snapshot hashes.
5. **Runs** — immutable run list, lifecycle, progress, per-condition status, method/executor call separation, tokens, latency, errors, cancellation.
6. **Trace Explorer** — ordered protocol events, role and round, visibility policy, input/output hashes, model/provider identity, decision outputs, validation/repair outcomes. Secret values and raw credentials must never be recorded.
7. **Results** — paper metric applicability, denominators/missingness, paired prompt-level observations, confidence intervals, Wilcoxon/Holm results, effect sizes, robustness/sensitivity and export.
8. **Reproducibility** — run manifest, code SHA, dependency lock hash, dataset snapshot hash, provider/model provenance, seed derivation, raw records and analysis version.
9. **Submission Export** — tables/figures, methods/evaluation text, machine-readable evidence bundle and a claim-to-evidence map.

## 4. Experiment lifecycle and API boundary

### Phase A — design and preflight (safe, no provider calls)
- Immutable typed `ExperimentSpec`.
- Validate paper experiment ID and exact condition grid against the engine's E1–E9 protocol.
- Validate dataset snapshot, annotation/reference requirements, model roster, family provenance, fixed executor, S12 policy and budgets.
- Produce a signed-by-hash preflight report with explicit check coverage and unresolved operator attestations.
- Do not instantiate provider clients.

### Phase B — controlled execution (disabled until gates pass)
- Accept only an immutable preflight report and explicit operator approval.
- Create an immutable `Run` with exact code/config/dataset/provider manifest hashes.
- Execute through a bounded worker interface; never accept arbitrary Python, shell, imports, notebook code or credentials in API payloads.
- Persist append-only run events and redacted traces.
- Enforce concurrency, request/token/cost/time ceilings and cancellation.
- A failed trial is recorded as failed; no silent retry or denominator deletion.
- Resume only from a verified checkpoint with the same immutable configuration; otherwise create a new run.

### Phase C — analysis
- Validate observation schema and identity against the run manifest.
- Reject duplicate observation keys and unregistered metric names.
- Preserve failures and missingness explicitly.
- Apply paired comparisons only to identical prompt IDs and valid paired observations.
- Record comparison family before Holm correction.
- Export raw observations and derived aggregates separately.
- Never mix synthetic smoke data with empirical observations.

### Proposed API surface (not implemented by this roadmap)
| Method | Route | Responsibility |
|---|---|---|
| GET | `/api/v1/campaigns` | List immutable campaign specifications |
| POST | `/api/v1/campaigns` | Create a draft campaign specification |
| GET | `/api/v1/campaigns/{id}` | Read exact specification and hash |
| POST | `/api/v1/campaigns/{id}/preflight` | Run zero-call machine validation |
| POST | `/api/v1/campaigns/{id}/approve` | Record explicit operator approval |
| POST | `/api/v1/runs` | Launch an approved, immutable campaign |
| GET | `/api/v1/runs/{id}` | Read run state and counters |
| GET | `/api/v1/runs/{id}/events` | Read ordered lifecycle events |
| GET | `/api/v1/runs/{id}/traces` | Read redacted trace events |
| POST | `/api/v1/runs/{id}/cancel` | Request cooperative cancellation |
| GET | `/api/v1/runs/{id}/artifacts` | Read immutable artifact index |
| POST | `/api/v1/analyses` | Analyse a completed, validated run |
| GET | `/api/v1/analyses/{id}` | Read analysis and provenance |
| GET | `/api/v1/analyses/{id}/export` | Export report bundle |

All proposed routes require schemas, API tests, access control and audit logging before implementation. This table is a target contract, not a statement that routes exist.

## 5. Delivery gates

### STUDIO-1 — Research workspace and state model
- Refactor current page into Overview, Datasets, Experiment Builder and Preflight views without changing engine semantics.
- Display evidence state and check coverage persistently.
- Add API schemas for campaign specification and preflight report.
- Add contract tests for unknown fields, invalid strategy/dataset IDs, invalid grid and secret rejection.
- Acceptance: all views render from API responses; zero provider calls; no false E1-ready state.

### EXP-1 — Dataset freeze and annotation governance
- Resolve each source's canonical identity, revision, applicable dataset terms, split, selection protocol and eligible population.
- Preserve dataset-native reference fields losslessly.
- Supply smart-administration prompts, reference decompositions, hypotheses and two-practitioner review evidence.
- Freeze selected IDs, file SHA-256, row hashes, source/license evidence and annotation version.
- Acceptance: complete five-dataset manifest passes deterministic validation; unresolved rights are not silently approved.

### EXP-2 — Protocol and provider roster readiness
- Finish source-to-runtime conformance for all 13 strategies.
- Validate both prompt-view and secondary input channels for S1/S12 visibility.
- Reconcile S10 moderator no-objection semantics with the paper.
- Freeze provider/model-family provenance and fixed executor identity; validate all required condition rosters.
- Acceptance: all protocol conformance tests pass; every declared condition has a reproducible roster; no unknown or unverified model identity is promoted.

### EXP-3 — Controlled campaign execution
- Implement a persistent run store and bounded worker.
- Add append-only event and trace records, redaction, cancellation, checkpoint/resume policy and resource ceilings.
- Implement an explicit provider-backed adapter for the fixed E1 protocol; no placeholder or synthetic adapter may be accepted as empirical.
- Acceptance: integration tests with a deterministic fake provider verify lifecycle and accounting; a separately labelled, small live-provider smoke run verifies connectivity only and is not included in E1 results.

### EXP-4 — Scientific analysis and evidence exports
- Validate raw observations against immutable manifests.
- Compute only metrics applicable to each dataset and experiment.
- Preserve failed trials and missing pairs; report denominators and exclusions.
- Verify paired tests, effect sizes, confidence intervals and Holm correction against independent reference calculations.
- Acceptance: analysis output is deterministic from frozen inputs; synthetic fixtures are visibly segregated; exports include raw data, code/config/data provenance and analysis version.

### EXP-5 — Manuscript integration and submission
- Reconcile all paper claims with implementation and measured evidence.
- Regenerate tables/figures from versioned analysis outputs.
- Report negative, null and inconclusive results without selective omission.
- Include limitations for model correlation, annotation uncertainty, metric applicability, provider nondeterminism and external validity.
- Acceptance: every empirical claim maps to an observation artifact; every algorithm and complexity claim maps to source and conformance evidence; all artifacts reproduce from the pinned release.

## 6. Scientific integrity rules

1. A preflight is not an experiment.
2. CI is not a benchmark result.
3. A GPU runtime is not evidence of model execution.
4. A synthetic fixture is not a benchmark observation.
5. A provider smoke test is not an E1 result.
6. A configuration hash is not proof that external model weights or provider behavior are immutable.
7. An operator's license declaration is an attestation, not independent legal verification.
8. A metric implementation is not evidence that its inputs are valid.
9. Failed trials and missing observations remain visible in denominators and reports.
10. A paper claim must be supported by traceable source, proof, test, or empirical artifact according to the claim type.

## 7. Immediate implementation order

1. STUDIO-1: restructure the current static page into an explicit research workflow and evidence-state dashboard.
2. EXP-1: resolve and freeze data/annotation provenance; do not launch full E1 before this passes.
3. EXP-2: close remaining paper-to-runtime protocol obligations.
4. EXP-3: implement run lifecycle and controlled provider execution behind readiness gates.
5. EXP-4: validate analysis and export reproducibility.
6. EXP-5: generate the submission package from pinned evidence.

The critical path is **dataset and annotation freeze + protocol conformance + fixed executor**, not UI polish. Studio work may proceed in parallel, but it must expose these blockers rather than bypass them.
