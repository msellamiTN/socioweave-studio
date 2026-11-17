# Core 18 — Test Report

**Status:** PASS — evaluation/reporting software acceptance only.  
**Exact tested commit:** 21672ffd4f809041962bf061977368c7a5885d6b  
**CI run:** 44201353152 — https://github.com/msellamiTN/socioweave-studio/actions/runs/44201353152

## Evidence
- Implementation: engine/sociodec/evaluation.py
- Tests: engine/tests/test_evaluation.py
- Notebook: notebooks/colab/SOCIOWEAVE_Core18_Experiment_Runtime.ipynb
- Specification: docs/CORE-18-CAMPAIGN-EVALUATION-COLAB.md
- Environment: GitHub Actions, Ubuntu latest, CPython 3.11.18, pytest 9.2.0
- Command: python -m pytest -q from engine/
- Result: **301 passed in 0.54s; 0 failed; 0 skipped.**

## Regression history
- Initial test run caught a mistaken expected mean in the paired-prompt fixture and a negative test that did not actually pass a metric into a failed observation. Both fixtures were corrected; the implementation contract remained unchanged.
- Full suite rerun on the exact tested commit passed.

## Limitations
- No provider-backed benchmark campaign, human annotation campaign or E1–E9 results are claimed.
- Colab notebook contains an explicit adapter boundary and refuses to fabricate results.
- Synthetic plot data are isolated and labelled demo-only.
- Paired p-values inherit Core 17's tie-corrected normal approximation; exact/permutation sensitivity analysis is not implemented.
- Colab runtime and GPU availability have not been executed/validated in a live Colab session.
