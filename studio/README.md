# SOCIOWEAVE Studio — API slice 0.1

This directory contains the first executable Web Studio backend slice.

## Scope delivered

- Versioned health and capability endpoints.
- Read-only catalogue of the five registered E1 datasets and their expected counts.
- A configuration preview endpoint that calls the existing engine strategy catalogue for the paper-defined method-call formula.\n- A zero-provider-call E1 preflight endpoint that freezes operator-supplied local JSONL dataset files and validates the complete paper condition grid through the engine.
- A same-origin operator UI with responsive configuration controls, dataset selection, call-budget preview and explicit execution-lock messaging.
- Strict request schema (`extra=forbid`) and validation of registered strategies, dataset IDs and seed indices.

## Deliberate limitations

The E1 preflight validates operator-supplied local dataset files, declared provenance/license approval, paper prompt counts, reference-data presence, frozen snapshot hashes and the complete matched-baseline condition grid. It does not validate provider/model family truth, executor identity, token/cost ceiling, extractor audit quality or runtime connectivity. It does not launch experiments.

No run-launch, worker, provider execution, arbitrary code execution, uploads or secret management endpoint is exposed. Capability metadata reports these as disabled. Both configuration preview and E1 preflight make zero live provider calls and cannot create a scientific run.

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
- `POST /api/v1/config-previews`\n- `POST /api/v1/preflights/e1`

The service is a single-process development component, not yet a deployable multi-user service. Authentication, authorization, persistence, worker isolation, observability and production security controls remain future gates.
