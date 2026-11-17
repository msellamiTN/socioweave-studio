# Core 19 Test Report

## Scope

Provider protocol bridge, metadata-only call tracing, visibility-bound request serialisation, and append-only resumable campaign checkpoints.

## Test coverage

- Provider protocol invocation and generation parameter mapping.
- Trace identity, token usage, request ID, latency and payload/completion hashes.
- Visibility-bound message construction and empty-output rejection.
- Trial checkpoint creation, idempotent resume, config/prompt mismatch rejection, duplicate detection, and failed-trial persistence.

## Execution evidence

Pending GitHub Actions full-suite run on the exact commit containing this report. No test count or PASS status is asserted until CI completes.

## Scientific boundary

These are software contract tests. They do not establish extraction accuracy, decomposition validity on real tasks, strategy effectiveness, executor correctness, or any E1–E9 result. No real model calls are represented by fake-provider tests.
