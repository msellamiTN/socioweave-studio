# SOCIOWEAVE Studio — API slice 0.1

This directory contains the first executable Web Studio backend slice.

## Scope delivered

- Versioned health and capability endpoints.
- Read-only catalogue of the five registered E1 datasets and their expected counts.
- A configuration preview endpoint that calls the existing engine strategy catalogue for the paper-defined method-call formula.
- A same-origin operator UI with responsive configuration controls, dataset selection, call-budget preview, local-source E1 preflight declarations, hash inspection and JSON report export.
- Strict request schema (`extra=forbid`) and validation of registered strategies, dataset IDs and seed indices.

## Deliberate limitations

The first E1 preflight validates dataset counts, declared source metadata/license approval, row splits, reference-data presence, frozen snapshot hashes and the complete matched-baseline condition grid. The full campaign preflight additionally reconstructs an `E1ProviderRegistry` from a canonical non-secret provider manifest and invokes `DirectE1Runtime.preflight_campaign` directly. It checks all 38 method/model-mode rosters, MA/MB/MC family/provider consistency, heterogeneous judge separation, fixed executor identity and the complete 4,550-row grid. The S12 factory identifier and SHA-256 are declarations only: the callback is not loaded or executed. Both endpoints make zero live calls and do not launch experiments. Neither result is `E1_READY`; independent source/license verification, annotation/extractor audits, S12 implementation tests, budget approval, T4/provider smoke and statistical analysis remain required.

No run-launch, worker, provider execution, arbitrary code execution, uploads or secret management endpoint is exposed. The campaign preflight accepts only a non-secret manifest; hosted-provider `api_key_env` values are environment-variable names, never credentials. An identity-only provider stub is used by the API so no client or model is initialized. Capability metadata reports these as disabled. Both configuration preview and E1 preflight make zero live provider calls and cannot create a scientific run.

## Run locally

From the repository root:

```bash
python -m pip install -e "engine[dev]" -e ./studio "httpx>=0.27,<1.0"
uvicorn socioweave_studio.api.app:app --app-dir studio --reload
```

To create the canonical provider manifest, construct the operator's validated
`E1ProviderRegistry` and call `registry.campaign_manifest(executor_id=...)`
(or `runtime.campaign_manifest()` after `build_direct_e1_runtime`). Serialize
that return value as JSON and paste it into the Studio. The manifest includes
non-secret provider routing settings and environment-variable *names* only;
it must never contain credential values. Hosted-provider environment variables
must be configured in the API process only if/when execution is later enabled.
The no-call preflight uses an identity-only provider stub and does not read
those variables or initialize model clients.

The S12 factory ID and SHA-256 are loaded from the registered
`paper-s12-3facet-v1` engine policy. The policy groups target+deliverable,
constraint and actor/resource facets; the grouping is a versioned
operationalization of the paper's Figure 3(b) example. Empty facets are
removed without provider calls. The API preflight binds the policy hash but
does not execute prompt-specific view generation. Per-prompt facet audit and
the paper's 20% human extraction audit remain required.

Open `/docs` on the local server for the OpenAPI contract.

## API

- `GET /api/v1/health`
- `GET /api/v1/capabilities` (advertises `engine_campaign_preflight=true`, while `full_e1_preflight=false` and `run_launch=false` remain deliberate)

- `GET /api/v1/datasets`
- `POST /api/v1/config-previews`
- `POST /api/v1/preflights/e1` — dataset snapshot and condition-grid preflight only.
- `POST /api/v1/preflights/e1/campaign` — engine-backed full campaign configuration preflight, including the 38 provider/model-mode rosters, MA/MB/MC provenance consistency, heterogeneous judge separation, fixed executor identity and S12 factory declaration.

The service is a single-process development component, not yet a deployable multi-user service. Dataset paths are read by the API process and must only be supplied by a trusted local operator. Authentication, authorization, filesystem sandboxing, persistence, worker isolation, observability and production security controls remain future gates.
