# Core 11 — End-to-End Adaptive Orchestrator

**Status:** IMPLEMENTED — acceptance pending full CI.  
**Scientific source:** Section 6.1, Algorithm 1; Section 7.3, Algorithm 2; Table 8 and the escalation rules in Section 7.3.

## 1. Purpose

Core 10 produced a deterministic plan. Core 11 adds the end-to-end control flow around injected model and strategy adapters:

1. Run the multi-extractor pipeline once and retain its result.
2. Produce two initial drafts with separate author indices and isolated adapter calls.
3. Diagnose features and calculate the paper's distance, content gap, structure gap and mean coupling.
4. Form the union of the two drafts, remove cycle edges using candidate support counts, and check the result.
5. Apply Table 8 and run selected strategies sequentially.
6. Give every strategy adapter both original drafts as initial seeds; pass the previous strategy result as the single chain seed when chaining.
7. Run Algorithm 1 repair/revalidation for each strategy result.
8. Compare each result with the current best using the paper's lexicographic order.
9. Escalate from the latest failure set, at most three times, and stop when the budget cannot cover the next strategy plus one possible repair call.
10. Return the best decomposition, its failures, strategies not run, actual call count and event trace.

## 2. Adapter contracts

- extract(prompt) returns AggregatedExtraction and the q extractor-level results. Extraction is called once.
- draft(prompt, extraction, author_index) returns a Decomposition. It is called with author indices 0 and 1. The adapter is responsible for independent contexts and, where available, distinct model families. The orchestrator cannot infer isolation from output objects.
- execute_strategy(item, prompt, extraction, initial_drafts, chain_seed, available_calls) returns StrategyOutcome. It builds and executes the selected social strategy, applies its decision operator, and returns its latest decomposition, actual calls, hypothesis verdicts, edge support evidence and optional findings. The adapter must enforce the supplied available-call limit.
- repair_callback(decomposition, findings) returns a Decomposition. It is an optional single-call Algorithm 1 repair adapter.

The orchestrator owns ordering, budget checks, seeding metadata, validation, escalation and result selection. It does not hard-code provider or per-strategy protocol construction.

## 3. Algorithm 2 fidelity and boundaries

- Initial drafts are passed as seeds to the first strategy; the previous strategy's result is passed as the chain seed for the next strategy.
- The initial union receives the paper's rule-only cycle removal and check. It is not sent through the model repair callback; Algorithm 2 lines 5–6 specify a checked union, while Algorithm 1 repair applies to strategy executions.
- Strategy outputs use Algorithm 1: cycle removal by least candidate support, one optional repair callback for remaining non-cycle failures, and final recheck.
- Escalation priority: uncovered requirement or unresolved hypothesis → C2 (Jigsaw then Devil's Advocate); cycle or composition failure → Peer Review; other failures or high stakes without failure → C1 full pipeline. A target already run is not repeated.
- C1 and C2 here refer to the two escalation combinations in Section 7.3, not to the five candidate design-space cells C1–C5. C1 is Algorithm 3 phase composition, not four complete sequential strategy runs; with three agents and one revision it costs nine calls (2n + 3).
- The best-result order is fewest failures, highest coverage, lowest redundancy, lowest coupling.
- The event log records the stage, decision and cumulative call count. It is an execution trace, not a proof of semantic correctness.
- V3 and V4 remain NOT_EVALUATED unless an execution-evidence workflow is separately supplied. This Core does not falsely treat structural validation as execution validation.

## 4. Budget accounting

The orchestrator counts q extraction calls, two initial draft calls, actual calls reported by strategy adapters, and any repair callback call. Before a strategy, it reserves the catalogue cost plus one possible repair call. The adapter receives the actual remaining budget and its reported call count is checked. A strategy or repair that exceeds the budget fails closed with an error; the orchestrator cannot undo external calls already made by a misbehaving adapter.

Catalogue reservation uses the full paper Table 4 call formula, so it is conservative when initial drafts are adopted as seeds and skip calls. C1 uses the Section 7.5 phase-composition cost (2n + 3 for one revision), not the sum of four full strategy costs. Reservations are bounds, not claims that every seeded run consumes that many calls.

## 5. Tests and acceptance

The integration suite checks Rule 0, initial-union escalation, C8 strategy execution, original draft seed forwarding, sequential chain seeding, budget truncation, adapter call-budget enforcement, malformed adapters, best-result preservation and event trace.

Run from engine/:

    python -m pip install -e ".[dev]"
    python -m pytest -q

Acceptance report is published only after the full CI suite passes on the final code commit.
