# Core 13 — Typed Protocol Decoding Test Report

**Status:** PASS — software decoding acceptance.  
**Exact tested code commit:** 64c6cd323d95c6f2d9506469536c1e1c0fb7f3b5  
**Final documentation commit:** 1df83fd84179bcfdde50b4b51e9bff830c14d6b7  
**CI run:** https://github.com/msellamiTN/socioweave-studio/actions/runs/44194445943  
**Environment:** GitHub Actions, Ubuntu latest runner, CPython 3.11  
**Command:** python -m pytest -q (from engine/)  
**Result:** **241 passed in 0.43s; 0 failed; 0 skipped.**

## Verified scope

- Candidate JSON decodes into typed Candidate and Decomposition objects.
- Subproblem identifiers, questions, inputs, outputs, local constraints and requirement coverage are validated.
- Requirement references must match the aggregated explicit extraction by type, domain and normalized statement.
- Local constraint references must match the prompt's declared constraints by kind and normalized statement.
- Dependency endpoints and deliverable contributors are validated by the domain model.
- Kappa keys must cover declared deliverables; missing or undeclared deliverable mappings fail.
- Hypothesis verdicts must refer to extracted hypotheses and use confirmed/rejected values; duplicate and unknown verdicts fail.
- Critique outputs accept only the paper's three typed objection categories: missing subproblem, redundant subproblem and hidden dependency.
- Rank, vote, judge, summarise, split and defend action outputs are parsed into typed ProtocolMessage fields.
- Malformed JSON and unsupported actions fail closed.

## Boundaries

- The JSON wire format is an engineering contract derived from paper objects; it is not a schema prescribed verbatim by the paper.
- Parsing does not apply decision operators, check complete ranking permutations against a live candidate pool, resolve ballots into majority sets, or select/merge final candidates.
- Parsing and local model validation do not prove V1/V2/V5; the structural validator remains authoritative.
- V3 solvability and V4 faithfulness remain NOT_EVALUATED without executor evidence.
- Provider-specific JSON schema enforcement, retries, repair and refusal handling are separate integration concerns.
- Passing tests establish serialization and type/reference integrity, not semantic correctness of LLM output.

## Decision

Core 13 passes the software decoding acceptance gate on the exact tested code commit. All 241 integrated tests passed with no failures or skips. Strategy-specific decision assembly and execution evidence remain separate gates.
