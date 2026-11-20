<div align="center">
  <img src="assets/brand/socioweave-symbol.svg" width="112" height="112" alt="SocioWeave symbol" />
  <h1>SOCIOWEAVE</h1>
  <p><strong>SocioWeave Studio</strong></p>
  <p><em>From complex prompts to collaborative intelligence.</em></p>
  <p>
    <img alt="Status" src="https://img.shields.io/badge/status-research%20implementation-7567D8?style=flat-square" />
    <img alt="Scientific scope" src="https://img.shields.io/badge/core-paper--faithful-178F88?style=flat-square" />
    <img alt="License" src="https://img.shields.io/badge/license-TBD-lightgrey?style=flat-square" />
  </p>
</div>

---

## What is SocioWeave?

**SocioWeave** is a research-oriented studio for designing, executing and evaluating social and organisational strategies for LLM-based multi-agent prompt decomposition.

The name combines:

- **Socio** — the social and organisational structures through which agents divide work, exchange information, disagree and make decisions.
- **Weave** — the deliberate interconnection of agents, roles, protocols, visibility rules, decisions and task dependencies.

The product is **SocioWeave Studio**. Its scientific execution core is the **SocioDec Engine**.

> **From complex prompts to collaborative intelligence.**

## Research foundation

The initial implementation is governed by the paper:

*Societies of Decomposers: Social and Organisational Strategies for LLM-Based Multi-Agent Prompt Decomposition.*

The paper-faithful core models a strategy as:

\[
\sigma = (A, R, \alpha, V, \pi, \omega)
\]

and a decomposition as:

\[
D = (S, E, \kappa)
\]

The implementation roadmap covers the thirteen strategies in the paper, the five explicitly labelled candidate strategies, adaptive strategy selection, typed strategy composition, validity checks and the paper's E1–E9 experimental programme.

**Scientific integrity:** paper-defined strategies and claims are kept separate from experimental candidates and future extensions. A strategy's execution does not by itself guarantee decomposition correctness.

## Brand identity

| Element | Definition |
|---|---|
| Brand | **SOCIOWEAVE** |
| Product | **SocioWeave Studio** |
| Engine | **SocioDec Engine** |
| Category | Multi-agent prompt decomposition research studio |
| Tagline | From complex prompts to collaborative intelligence |
| Personality | Scholarly, precise, collaborative, transparent |
| Primary colour | Weave Indigo — `#6257C5` |
| Secondary colour | Deep Navy — `#111827` |
| Accent | Teal — `#18A999` |
| Canvas | Soft Mist — `#F5F7FB` |

See [Brand Guide](docs/BRAND_GUIDE.md) and [Brand Assets](assets/brand/).

## Repository map

```text
socioweave-studio/
├── assets/                # Brand assets
├── docs/                  # Research, conformance and implementation records
├── engine/
│   ├── sociodec/           # Python research engine and E1 execution components
│   └── tests/              # Deterministic unit and integration tests
└── README.md
```

The repository now contains an executable research implementation in `engine/`, including the paper's strategy/runtime contracts, provider-backed execution interfaces, conformance checks, and a no-call E1 campaign harness. The README is a high-level orientation only; consult the research and test reports in `docs/` for the exact scope and evidence status.

## Repository topics

Suggested GitHub topics: `multi-agent-systems`, `llm-agents`, `prompt-decomposition`, `agent-orchestration`, `research-platform`, `socioweave`.

## Status and evidence boundary

- **Implemented:** brand foundation, Python engine, strategy/runtime conformance checks, E1 dataset intake and snapshot hashing, provider/model provenance gates, and campaign preflight/checkpoint contracts.
- **Software validation:** report only the exact commit and CI run recorded in the relevant test report. Deterministic tests and mock providers establish software behavior, not empirical model performance.
- **Not yet established:** live provider smoke tests, the complete approved five-dataset benchmark bundle, the practitioner-reviewed smart-administration annotations, and empirical E1–E9 results.
- **Pending analysis:** dataset-specific reference adapters and paired computation of reference agreement, stability and process gain.

No benchmark result, provider execution, or scientific conclusion should be inferred from the presence of the harness alone.

---

<div align="center">
  <img src="assets/brand/socioweave-wordmark.svg" alt="SocioWeave" width="280" />
  <p><sub>Research with structure. Collaboration with purpose.</sub></p>
</div>
