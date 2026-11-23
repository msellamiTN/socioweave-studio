# SOCIOWEAVE Studio — API slice 0.1

This directory contains the first executable Web Studio backend slice.

## Scope delivered

- Versioned health and capability endpoints.
- Read-only catalogue of the five registered E1 datasets and their expected counts.
- A configuration preview endpoint that calls the existing engine strategy catalogue for the paper-defined method-call formula.
- A same-origin operator UI with responsive configuration controls, dataset selection, call-budget preview, local-source E1 preflight declarations, hash inspection and JSON report export.
- Strict request schema (`extra=forbid`) and validation of registered strategies, dataset IDs and seed indices.

## Deliberate limitations

The E1 dataset/grid preflight UI submits operator-supplied local dataset paths and declarations to the API. The engine validates dataset counts, declared source metadata/license approval, row splits, reference-data presence, frozen snapshot hashes and the complete matched-baseline condition grid. The browser can export the returned report. This is not the complete `DirectE1Runtime.preflight_campaign`: provider rosters, MA/MB/MC family provenance, fixed executor identity, S12 prompt-view configuration, extractor audit quality, token/cost ceiling and runtime connectivity remain separate gates. It does not launch experiments.

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
- `POST /api/v1/config-previews`
- `POST /api/v1/preflights/e1`

The service is a single-process development component, not yet a deployable multi-user service. Dataset paths are read by the API process and must only be supplied by a trusted local operator. Authentication, authorization, filesystem sandboxing, persistence, worker isolation, observability and production security controls remain future gates.
