# SOCIOWEAVE Studio — API slice 0.1

This directory contains the first executable Web Studio backend slice.

## Scope delivered

- Versioned health and capability endpoints.
- Read-only catalogue of the five registered E1 datasets and their expected counts.
- A configuration preview endpoint that calls the existing engine strategy catalogue for the paper-defined method-call formula.
- A same-origin operator UI with responsive configuration controls, dataset selection, call-budget preview and explicit execution-lock messaging.
- Strict request schema (`extra=forbid`) and validation of registered strategies, dataset IDs and seed indices.

## Deliberate limitations

This is **not** a full E1 preflight and does not validate a frozen dataset snapshot, provider roster, model revision, complete matched-baseline grid, executor identity, token/cost ceiling or licensing evidence. The endpoint name is intentionally `config-previews`, not `preflights`.

No run-launch, worker, provider execution, arbitrary code execution, uploads or secret management endpoint is exposed. Capability metadata reports these as disabled. A preview always reports zero live provider calls and cannot create a scientific run.

## Run locally

From the repository root:

```bash
python -m pip install -e "engine[dev]" -e ./studio "httpx>=0.27,<1.0"
uvicorn socioweave_studio.api.app:app --app-dir studio --reload
```

Open `/docs` on the local server for the OpenAPI contract.

## API

- `GET /api/v1/health`
- `GET /api/v1/capabilities`
- `GET /api/v1/datasets`
- `POST /api/v1/config-previews`

The service is a single-process development component, not yet a deployable multi-user service. Authentication, authorization, persistence, worker isolation, observability and production security controls remain future gates.
