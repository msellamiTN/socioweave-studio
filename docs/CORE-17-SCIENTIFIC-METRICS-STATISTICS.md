# Core 17 — Scientific Metrics and Statistical Analysis

**Status:** Implementation submitted for full CI acceptance. Metric implementation is not an empirical result.  
**Scientific basis:** Paper Definitions 7–8, Table 9, Sections 7.4 and 8.1–8.2, and E1–E9.

## Scope
Deterministic calculations for requirement extraction quality, span entailment, decomposition quality, process gain, paired comparisons, confidence intervals and multiple-comparison correction. Inputs are gold annotations and execution outputs; this Core does not infer those labels or call models.

## Metric contracts
- Extraction precision, recall and F1 use set-based TP/FP/FN against a human reference set. Empty/empty is treated as perfect agreement; empty prediction against non-empty gold yields zero.
- Span entailment is the fraction of explicit extracted requirements whose source spans are judged to entail the statements. Assessments must be supplied as booleans by annotation or a separately validated verifier.
- Coverage = |covered requirements ∩ reference requirements| / |reference requirements|.
- Redundancy is the share of subproblems having at least one equivalent peer. Caller-supplied equivalence-class signatures make matcher decisions explicit.
- Coupling = |unique dependency edges| / |subproblems|.
- Depth is supplied from the validated DAG's longest path, measured in vertices as in the paper.
- Structural validity is acyclicity ∧ complete requirement coverage (V1) ∧ complete composition (V5). V3/V4 are not inferred here.
- Solvability is the share of executed subproblems marked solved. Utility is supplied task success in [0,1]. Both remain undefined without execution evidence.
- Process gain = strategy utility − same-budget baseline utility.

## Statistical contracts
- Paired Wilcoxon signed-rank calculation removes zero paired differences, ranks absolute differences with average ranks for ties, and reports W+, two-sided tie-corrected normal-approximation p-value with continuity correction, rank-biserial effect size, median and mean paired difference, and deterministic percentile-bootstrap 95% CI for the mean difference.
- The p-value is explicitly a normal approximation, not an exact test. Small-sample campaigns should add exact/permutation sensitivity analysis where appropriate.
- Holm step-down correction controls family-wise error across the supplied family of p-values.
- Bootstrap intervals are percentile intervals for the mean paired difference; seed and resample count must be recorded.

## Paper alignment and limits
The paper requires paired Wilcoxon tests with Holm correction and positive, significant, seed/order-stable process gain before declaring a strategy preferable for a prompt case. This Core supplies calculations but does not encode the complete scientific decision rule. Reference agreement is 1 − dist(D*, Dref), using the existing decomposition-distance implementation and a versioned equivalence matcher.

Metrics are conditional on annotation and extraction quality. Coverage inherits errors in the requirement set. V3/V4 require actual execution and verifier evidence. Latency, VRAM, tokens, retries and malformed outputs are supplementary engineering telemetry, not substitutes for Table 9 metrics.

## Acceptance evidence
See CORE-17-TEST-REPORT.md after CI. No benchmark campaign, human annotation, provider-backed run, significance result or strategy ranking is claimed.
