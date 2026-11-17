# Core 21 Test Report

## Scope
Provider-backed initial draft decoding, q-extractor aggregation, PromptFactory boundary, Core 11 orchestration composition, Core 20 fixed-executor evaluation and trial outcome metadata.

## Test coverage
- Two independent provider instances receive one initial-draft request each.
- Typed candidate output is decoded against extracted requirements and prompt constraints.
- Invalid provider JSON fails closed.
- q extractors aggregate through the paper-aligned union/dedup path.
- End-to-end trial adapter runs orchestration and fixed-executor evaluation.
- PromptFactory cannot mutate the benchmark prompt text.
- Campaign policy validates minimum call budget.

## Acceptance evidence
Pending full engine CI on the exact implementation and documentation commit.

## Scientific boundary
Unit tests use fake providers and executor fixtures. They establish integration behavior only; they do not establish hosted-model output quality, model independence, verifier correctness or strategy effectiveness.
