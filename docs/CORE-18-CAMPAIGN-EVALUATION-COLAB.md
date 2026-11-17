# Core 18 — Campaign Evaluation & Google Colab Experiment Runtime

**Status:** Submitted for full CI acceptance.  
**Scientific basis:** Paper Sections 8.1–8.2, Tables 9, 12, 13 and 14; experiments E1–E9.

## Scope
Core 16 provides reproducible trial execution; Core 17 provides metric and statistical functions. Core 18 aggregates campaign observations, performs paired prompt-level comparisons, applies Holm correction and provides a Google Colab workflow for real campaign execution and plotting.

## Evaluation contracts
- Each observation is keyed by dataset, example, strategy and repeat; duplicate keys are rejected.
- Failed trials remain in denominators and are reported as failures. They are not silently discarded.
- Metric summaries report available sample count and missing count.
- Paired comparisons average successful repeats within each prompt and strategy, then pair the strategy and baseline on identical prompt IDs. Missing pairs are counted and never imputed.
- Holm correction is applied to the explicitly supplied family of comparisons.
- Wilcoxon p-values use Core 17's tie-corrected normal approximation, not an exact small-sample test.
- Equal-budget equivalence must be established by campaign configuration and recorded call/token cost; the evaluator does not infer it.

## Colab notebook
notebooks/colab/SOCIOWEAVE_Core18_Experiment_Runtime.ipynb provides:
1. Python/runtime and optional GPU inspection, Google Drive persistence.
2. Installation from an exact Git commit.
3. Licensed JSONL dataset ingestion and identity checks.
4. Paper-aligned configuration (five repeats; n=3, k=3, T≤2; temperatures 0.7/0.2/0; token limits 1024/512; fixed executor).
5. An explicit provider-backed adapter boundary. It stops with NotImplementedError until a reviewed adapter is supplied; it does not fabricate campaign results.
6. Ingestion of real observation JSONL, aggregation, paired tests and Holm adjustment.
7. JSON/CSV/JSONL export and Matplotlib plots for metric means, calls-vs-utility and failure rates.
8. A separate synthetic plotting smoke test, prominently labelled and never merged into experiment observations.

## Scientific limits
No model calls, benchmark downloads, annotations or E1–E9 campaigns are run at build time. A real campaign requires licensed dataset snapshots, human reference annotations where specified, validated matcher, provider-backed strategies and a fixed executor. GPU availability does not imply a selected model fits the accelerator. Results depend on annotation, matching and execution validity.
