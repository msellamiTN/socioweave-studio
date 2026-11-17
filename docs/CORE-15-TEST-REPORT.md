# Core 15 — Test Report

**Status:** PASS — unified software validation/finalization acceptance.

## Tested implementation

- Commit: `5e3b4df53bb166f855cee648912d8689d30819e4`
- CI run: https://github.com/msellamiTN/socioweave-studio/actions/runs/44197037514
- Environment: GitHub Actions, Ubuntu latest runner, CPython 3.11.18, pytest 9.2.0
- Install: `python -m pip install -e ".[dev]"`
- Test command: `python -m pytest -q`
- Result: **259 passed in 0.25s; 0 failed; 0 skipped.**

## Coverage added

- Winning strategy run identity, hypothesis verdicts and candidate support evidence are retained with AdaptiveResult.
- Final structural validation is recomputed from the selected decomposition and its own hypothesis verdicts.
- V3/V4 remain NOT_EVALUATED when no ExecutionRun is supplied.
- Explicit execution evidence is passed to the Core 06 assessor and combined with structural validity.
- End-to-end mock-provider path covers extraction, initial drafts, strategy decision, repair/validation and finalization.

## Limitations

- No real LLM provider or executor was used in this acceptance test.
- Execution evidence checks trace consistency; it does not prove semantic correctness of natural-language answers.
- No extraction-quality or E1–E9 strategy-effectiveness measurements are claimed.
