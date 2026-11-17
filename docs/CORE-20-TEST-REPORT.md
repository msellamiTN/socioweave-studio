# Core 20 Test Report

## Scope
Fixed-executor identity contract, execution evidence integration with Core 15, V3/V4 propagation, decomposition metrics, optional utility scoring and trial outcome construction.

## Test coverage
- Executor identity mismatch fails before execution.
- Valid execution evidence yields V3/V4/full validity.
- Failed execution and violated hard constraint are reflected in metrics.
- Utility is omitted without an independent scorer and rejects invalid scores.
- Cyclic DAG depth fails closed.
- Provider trace and hashed composed-answer metadata are retained without raw answer text.

## CI evidence
Pending full engine CI on the exact implementation and documentation commit. No PASS status or test count is asserted before completion.

## Scientific boundary
Software tests do not establish semantic executor quality, verifier independence, benchmark performance or strategy effectiveness.
