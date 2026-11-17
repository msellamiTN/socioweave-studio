"""Unified final evaluation for adaptive decomposition results.

Structural checks are always recomputed from the selected result and its
retained hypothesis verdicts. V3/V4 are assessed only when explicit executor
evidence is supplied; absence of evidence remains NOT_EVALUATED.
"""
from __future__ import annotations

from dataclasses import dataclass

from sociodec.execution import (
    ExecutionReport, ExecutionRun, FullValidityReport, assess_execution,
    combine_validity,
)
from sociodec.orchestrator import AdaptiveResult
from sociodec.validation import ValidationReport, validate_decomposition


@dataclass(frozen=True, slots=True)
class FinalAdaptiveEvaluation:
    structural: ValidationReport
    execution: ExecutionReport | None
    full_validity: FullValidityReport | None
    strategy_run_id: str | None
    calls_made: int
    budget: int

    @property
    def execution_evaluated(self) -> bool:
        return self.execution is not None

    @property
    def fully_valid(self) -> bool | None:
        return None if self.full_validity is None else self.full_validity.fully_valid


def finalize_adaptive_result(
    result: AdaptiveResult,
    *,
    execution_run: ExecutionRun | None = None,
) -> FinalAdaptiveEvaluation:
    """Revalidate the winner and optionally assess its execution evidence.

    This function does not execute the decomposition. Callers must supply a
    genuine ExecutionRun from the executor to evaluate V3 and V4.
    """
    structural = validate_decomposition(
        result.diagnosis.prompt if hasattr(result.diagnosis, "prompt") else result._prompt,
        result.extraction.requirements,
        result.best,
        hypotheses=result.extraction.hypotheses,
        verdicts=result.best_hypothesis_verdicts,
    )
    if execution_run is None:
        return FinalAdaptiveEvaluation(
            structural, None, None, result.best_strategy_run_id,
            result.calls_made, result.budget,
        )
    execution = assess_execution(
        result._prompt, result.best, execution_run,
    )
    return FinalAdaptiveEvaluation(
        structural, execution, combine_validity(structural, execution),
        result.best_strategy_run_id, result.calls_made, result.budget,
    )
