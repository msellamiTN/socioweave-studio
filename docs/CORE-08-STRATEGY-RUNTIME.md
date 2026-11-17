# Core 08 — Strategy Runtime

**Status:** PASS — visibility-aware runtime software acceptance on commit `23045d97814994c7f448db97b6c86eeb5c75052f`.  
**Scientific source:** Definition 10 and Algorithm 1's protocol execution loop.

## 1. Paper contract

The runtime applies the protocol (pi) of a strategy (sigma=(A,R,alpha,V,pi,omega)). Each protocol step invokes an agent with its assigned role, action, input and the context permitted by its view of the prompt and visibility relation. Agents always see their own outputs. Anonymity hides author names. Hypotheses are passed to agents. Seeds may replace one agent's first-round draft call and must not be shown to other agents unless visibility permits it.

## 2. Software realization

- The caller supplies a `ProtocolInvoker`; provider selection remains external.
- `run_strategy` dispatches protocol steps in stage order and records each output.
- Each stage uses a history snapshot so an agent cannot observe a peer's output from the same parallel stage. Its own earlier output remains visible.
- Prompt views can be supplied per agent; otherwise the original prompt text is used.
- Only outputs from authors visible to the observer are placed in context. The anonymity flag replaces author IDs with the label `anonymous`.
- Hypotheses are included in every protocol context.
- A seed is adopted only for that agent's first round-1 draft; it skips the model call.
- Non-model protocol steps require a caller-supplied precomputed output.
- Calls made and stages executed are recorded separately.
- Protocol steps must be ordered by round/stage, and one stage cannot span multiple rounds.

## 3. Scope boundary

The runtime dispatches serially for deterministic reproducibility, even when multiple steps share a stage. Stage snapshots preserve the paper's information-flow semantics, but this implementation does not claim parallel latency. It does not apply the decision rule (omega), build the final decomposition, perform structural repair or select strategies. Those remain separate components.

## 4. Acceptance evidence

From `engine/`:

    python -m pip install -e '.[dev]'
    python -m pytest -q

**Result:** 134 passed in 0.22s; 0 failed; 0 skipped.  
**Exact tested commit:** `23045d97814994c7f448db97b6c86eeb5c75052f`.  
**CI:** [Workflow run 44187520064](https://github.com/msellamiTN/socioweave-studio/actions/runs/44187520064).  
See [CORE-08-TEST-REPORT.md](CORE-08-TEST-REPORT.md) for detailed scope and limitations.

This acceptance is software-level runtime validation only; it is not evidence of strategy effectiveness, parallel runtime performance or model quality.
