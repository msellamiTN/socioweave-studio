# Paper2Code Semantic Audit — Round 1

**Audited source:** uploaded *Societies of Decomposers*, Definitions 1–10, Table 4, Table 9, and Section 8.
**Audited code:** `main` at `868644416d21aa9c0672ca42071d9693f9bbcc35`.
**Purpose:** record concrete semantic risks found by reading source and implementation together. This is not a claim that the full audit is complete.

## Findings

### A1 — Sub-problem equivalence is stricter than Definition 7 (high priority)

**Paper:** Definition 7 says two sub-problems are equivalent when a matcher judges that they ask for the same output under the same local constraints.

**Code:** `engine/sociodec/decisions.py::subproblem_signature` includes:
- normalized question;
- normalized inputs;
- normalized output;
- local constraints;
- covered requirement labels (type, domain and statement).

The implementation's equality therefore requires several fields to match exactly after normalization, including coverage metadata. This is not the source definition. Two sub-problems that ask for the same output under the same local constraints may be treated as different because their wording, input metadata or coverage annotations differ. Conversely, an exact normalized output string does not establish semantic equivalence.

**Impact:** affects Definition 7 distance, stopping conditions, deduplication, union, voting, medoid selection and potentially reported redundancy. It is a central scientific dependency, not a cosmetic matcher detail.

**Required correction:**
1. Separate a paper-level semantic equivalence decision from canonical serialization.
2. Define the matching contract in source terms: same requested output under same local constraints, with explicit handling of context/input needed to interpret that output.
3. Do not use requirement-coverage metadata as an equivalence key.
4. Provide a pluggable semantic matcher with provenance, confidence/abstention and human-audit support.
5. Keep a deterministic matcher for unit tests only, clearly labelled as an approximation.
6. Add adversarial tests: paraphrased equivalent questions; same wording but different outputs; same output under different constraints; same output with different coverage labels; ambiguous/uncertain pairs.
7. Re-run all metrics and experiments affected by equivalence after changing the matcher.

**Status:** confirmed semantic mismatch between the literal source criterion and current exact-signature implementation. A production semantic matcher still needs validation.

### A2 — Distance currently inherits the exact-signature mismatch (high priority)

**Paper:** Equation (2) uses Jaccard similarity over equivalence classes of sub-problems and dependencies.

**Code:** `decomposition_distance` correctly uses the structure (1 - \frac{1}{2}(J_S+J_E)), including the empty/empty Jaccard convention. But its sets are built from `subproblem_signature`, not from a validated semantic equivalence relation.

**Impact:** the equation is implemented, but the equivalence classes are not yet faithful. Stability/consensus thresholds (including ε=0.1) cannot be treated as scientifically validated until A1 is addressed.

**Required correction:** make distance consume equivalence-class assignments produced by the audited matcher; test symmetry, bounds [0,1], identity of indiscernibles relative to the declared equivalence, edge matching, and empty edge sets.

### A3 — Redundancy metric inherits the same equivalence dependency (high priority)

**Paper:** Table 9 defines redundancy as the share of sub-problems equivalent to another one.

**Code:** `decomposition_metrics` counts duplicate `subproblem_signatures`.

**Impact:** arithmetic is straightforward, but the scientific measure is only as valid as the signature/matcher. Current scores can undercount paraphrased duplicates and overcount semantically distinct items with superficial similarity.

**Required correction:** use the validated equivalence relation from A1, define the denominator/duplicate-group counting explicitly, and add reference-labelled test cases.

### A4 — Structural validator correctly leaves V3 and V4 unevaluated (positive evidence)

**Paper:** Definition 6 explicitly states V3 solvability and V4 faithfulness can only be observed by execution; V1, V2 and V5 can be checked programmatically.

**Code:** `validation.py::validate_decomposition` marks V3 and V4 as `NOT_EVALUATED`, while checking V1, V2 and V5 and hypothesis verdict completeness.

**Status:** aligned evidence boundary. Do not weaken this by translating NOT_EVALUATED into PASS. A separate execution validator is still required to establish V3/V4.

### A5 — Decomposition model enforces references but deliberately does not enforce all validity properties (positive evidence with boundary)

**Paper:** Definitions 4–6 distinguish representation from validity.

**Code:** `models/decomposition.py` checks unique IDs, dependency endpoints, composition references and prompt-relative constraints/requirements; it delegates V1/V2/V5 to validation.

**Status:** defensible separation of concerns. Ensure every runtime entry point calls the appropriate validator before a decomposition is accepted or executed.

### A6 — Metric function has no dataset applicability contract (high priority)

**Paper:** Table 12 explicitly excludes coverage for BREAK, StrategyQA and TaskBench; restricts TravelPlanner coverage to annotated constraints; smart-administration supports all Table 9 metrics.

**Code:** `metrics.py::decomposition_metrics` requires a non-empty requirement set and computes coverage generically. Dataset applicability is not represented in this function's contract.

**Impact:** callers can accidentally calculate or compare a metric that the paper says does not apply to that dataset.

**Required correction:** add a dataset/benchmark metric capability declaration and fail closed when a metric is unsupported; make restricted coverage's denominator explicit; tests for each Table 12 dataset.

### A7 — Wilcoxon implementation is a normal approximation, not an exact signed-rank test (medium/high priority)

**Paper:** Table 13 specifies paired-prompt Wilcoxon signed-rank with Holm correction, α=0.05.

**Code:** `metrics.py::wilcoxon_paired` implements a tie-corrected normal approximation with continuity correction, omitting zero differences, plus bootstrap intervals.

**Impact:** this may be a defensible large-sample approximation, but it is not an exact Wilcoxon calculation and the paper does not specify this approximation. It must not be silently presented as exact reproduction.

**Required correction:** document the selected statistical method, compare against a trusted exact/asymptotic implementation on edge cases and benchmark-sized samples, pre-specify the zero/tie policy, and record the method in experiment manifests. If using an approximation, label it explicitly as a deviation unless the source's full statistical protocol supports it.

### A8 — Prompt interpretation is stored, not inferred (intentional boundary)

**Paper:** Definition 1 distinguishes the user text x from interpretation ι and says a decomposer receives x and must choose an element of Int(x).

**Code:** `models/prompt.py` stores a declared interpretation and explicitly does not infer the full set Int(x). Extraction is separate.

**Status:** sound architectural separation, but an end-to-end ambiguity/framing stage must operationalise alternative interpretations for the paper's ambiguous-prompt experiments. A populated Interpretation object alone is not evidence that Int(x) was explored.

### A9 — Requirement extraction uses exact normalized dedup by default (partial approximation)

**Paper:** Definition 3 requires deduplication of equivalent statements and q extractors that may differ by model or seed.

**Code:** `extraction.py::aggregate_extractions` uses normalized exact match by default and accepts a pluggable matcher.

**Impact:** conservative exact dedup is safe for deterministic software tests but does not implement semantic equivalence in the general case.

**Required correction:** treat default dedup as a deterministic baseline only; integrate the same independently validated equivalence/matcher governance required by A1, without conflating requirement equivalence with sub-problem equivalence.

## Priority order from this audit

1. A1–A3: semantic matcher/equivalence foundation (blocks distance, stability, redundancy and several decision rules).
2. A6: dataset-aware metric capabilities (blocks valid E1 comparisons).
3. A7: statistical method specification and verification (blocks final inferential claims).
4. A8–A9: interpretation and extraction validation (blocks ambiguity/hypothesis claims).
5. A4–A5: preserve the current correct separation between structural checks and execution-based validity; implement execution evidence for V3/V4.

## Evidence boundary

This round was a static source/code comparison. It did not execute provider models, benchmark datasets, a Colab runtime or the web application. It did not establish any experimental result. The next implementation should address the high-priority semantic matcher first, with tests designed from the paper's Definition 7 and Table 9.
