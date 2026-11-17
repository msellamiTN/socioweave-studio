# Core 13 — Typed Protocol Output Decoding

**Status:** IMPLEMENTED — full acceptance pending CI.  
**Source basis:** Definitions 4–6, Algorithm 1, Section 5.3.1 and Table 4 of the source paper.

## Scope

The protocol decoder is a strict engineering serialization contract derived from the paper's formal objects. The paper defines decomposition and strategy semantics; it does not prescribe this exact JSON wire format.

Files:
- engine/sociodec/protocol_decoding.py
- engine/tests/test_protocol_decoding.py

## Candidate wire contract

A candidate object contains:
- candidate_id
- subproblems: id, question, inputs, output, local_constraints, covered_requirements
- dependencies: source, target
- kappa: deliverable to contributor-ID array

Requirement references use exact triples of type, domain and statement and must resolve to the aggregated explicit requirement set. Constraint references use exact kind and statement and must resolve to the prompt's declared constraints. Unknown references are rejected. Decomposition construction and prompt-relative validation then check local integrity, dangling edges, composition references and declared deliverable keys.

## Protocol action contracts

- draft, revise, merge, check: typed candidate
- critique: typed objections (missing_subproblem, redundant_subproblem, hidden_dependency)
- rank: complete candidate identifier order (completeness checked when applying rank-sum)
- vote: candidate/subproblem references (resolved against pooled candidates by the decision layer)
- judge: selected candidate identifier and rationale
- summarise: summary, agreements and disagreements
- split: explicit agent-to-partition mapping
- defend: defence text

Hypothesis verdicts reference exact members of H-hat and use only confirmed/rejected. Duplicate or unknown verdicts are rejected.

## Boundaries

This module parses and validates typed evidence; it does not decide strategy outcomes. Decision operators remain in decisions.py, and strategy-specific assembly remains in the adapter/decoder layer. V1/V2/V5 are not asserted by parsing alone; the structural validator remains authoritative. V3/V4 still require executor evidence.

The schema is a software contract and must be versioned before external clients depend on it. It is not a scientific claim or a verbatim paper specification.

## Acceptance

Run from engine/:

    python -m pip install -e ".[dev]"
    python -m pytest -q

Acceptance requires the full integrated suite, exact-commit CI and zero skipped tests.
