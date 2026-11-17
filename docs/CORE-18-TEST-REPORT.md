# Core 18 — Test Report

**Status:** Pending full CI verification.  
**Scope:** Evaluation aggregation/reporting software. The Colab notebook is an operator workflow, not evidence of a completed campaign.

- Implementation: engine/sociodec/evaluation.py
- Tests: engine/tests/test_evaluation.py
- Notebook: notebooks/colab/SOCIOWEAVE_Core18_Experiment_Runtime.ipynb
- Specification: docs/CORE-18-CAMPAIGN-EVALUATION-COLAB.md
- Command: python -m pytest -q from engine/
- Exact commit, environment, test count and CI URL: record after final workflow inspection.

## Limitations
No provider-backed benchmark campaign or E1–E9 results are claimed. Notebook plotting smoke test uses synthetic values only. Wilcoxon method is the Core 17 normal approximation.
