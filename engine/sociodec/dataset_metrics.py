"""Dataset-specific metric applicability from Table 12 of the paper.

This registry is deliberately declarative: it does not calculate metrics or
claim that a dataset artifact has been obtained. It prevents experiment
reports from treating unavailable reference information as a zero score.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping


TABLE9_METRICS = frozenset({
    "validity", "coverage", "redundancy", "coupling", "solvability",
    "utility", "cost", "reference_agreement", "stability", "process_gain",
})


@dataclass(frozen=True, slots=True)
class DatasetMetricProfile:
    dataset: str
    applicable_metrics: frozenset[str]
    validity_components: frozenset[str] = frozenset()
    coverage_scope: str | None = None
    reference_agreement_scope: str | None = None
    additional_metrics: frozenset[str] = frozenset()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.dataset.strip():
            raise ValueError("dataset must be non-empty")
        unknown = (self.applicable_metrics | self.additional_metrics) - TABLE9_METRICS - {"hypothesis_verdicts"}
        if unknown:
            raise ValueError(f"unknown metric(s): {sorted(unknown)}")
        if "coverage" in self.applicable_metrics and not self.coverage_scope:
            raise ValueError("coverage requires an explicit scope")
        if "reference_agreement" in self.applicable_metrics and not self.reference_agreement_scope:
            raise ValueError("reference agreement requires an explicit reference scope")


_ALL = TABLE9_METRICS
_PROFILES = {
    "BREAK": DatasetMetricProfile(
        "BREAK",
        frozenset({"reference_agreement", "redundancy", "coupling", "validity", "stability", "cost"}),
        validity_components=frozenset({"V2", "V5"}),
        reference_agreement_scope="gold decomposition into ordered steps",
        notes=("Coverage does not apply: no requirement list.",),
    ),
    "StrategyQA": DatasetMetricProfile(
        "StrategyQA",
        frozenset({"reference_agreement", "utility", "process_gain", "stability", "cost"}),
        reference_agreement_scope="recall of annotated implicit reasoning steps",
        notes=("Coverage does not apply: no requirement list.",),
    ),
    "TaskBench": DatasetMetricProfile(
        "TaskBench",
        frozenset({"reference_agreement", "validity", "coupling", "stability", "cost"}),
        validity_components=frozenset({"V2", "V5"}),
        reference_agreement_scope="reference sub-tasks and dependency graph",
        notes=("Coverage does not apply: no requirement list.",),
    ),
    "TravelPlanner": DatasetMetricProfile(
        "TravelPlanner",
        frozenset({"utility", "solvability", "process_gain", "validity", "coverage", "stability", "cost"}),
        validity_components=frozenset({"V2", "V5"}),
        coverage_scope="annotated constraints only",
        notes=("No reference decomposition.",),
    ),
    "smart-administration": DatasetMetricProfile(
        "smart-administration",
        _ALL,
        validity_components=frozenset({"V1", "V2", "V5"}),
        coverage_scope="full author-reviewed requirement list",
        reference_agreement_scope="author-reviewed reference decompositions",
        additional_metrics=frozenset({"hypothesis_verdicts"}),
        notes=("All Table 9 metrics apply.",),
    ),
}

DATASET_METRIC_PROFILES: Mapping[str, DatasetMetricProfile] = MappingProxyType(_PROFILES)


def get_metric_profile(dataset: str) -> DatasetMetricProfile:
    try:
        return DATASET_METRIC_PROFILES[dataset]
    except KeyError as exc:
        raise ValueError(f"No Table 12 metric profile for dataset: {dataset}") from exc


def validate_reported_metrics(dataset: str, reported_metrics: Iterable[str]) -> None:
    """Reject metrics Table 12 says cannot be computed for this dataset."""
    profile = get_metric_profile(dataset)
    reported = set(reported_metrics)
    allowed = profile.applicable_metrics | profile.additional_metrics
    unsupported = reported - allowed
    if unsupported:
        raise ValueError(
            f"Metric(s) not applicable to {dataset} under Table 12: {sorted(unsupported)}"
        )
