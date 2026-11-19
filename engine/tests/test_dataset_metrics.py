import pytest

from sociodec.dataset_metrics import (
    DATASET_METRIC_PROFILES, get_metric_profile, validate_reported_metrics,
)


def test_table12_dataset_metric_profiles_match_paper_applicability():
    assert "coverage" not in get_metric_profile("BREAK").applicable_metrics
    assert "coverage" not in get_metric_profile("StrategyQA").applicable_metrics
    assert "coverage" not in get_metric_profile("TaskBench").applicable_metrics
    travel = get_metric_profile("TravelPlanner")
    assert travel.coverage_scope == "annotated constraints only"
    assert "reference_agreement" not in travel.applicable_metrics
    smart = get_metric_profile("smart-administration")
    assert smart.applicable_metrics == {
        "validity", "coverage", "redundancy", "coupling", "solvability",
        "utility", "cost", "reference_agreement", "stability", "process_gain",
    }
    assert "hypothesis_verdicts" in smart.additional_metrics


def test_table12_validity_components_are_not_misreported_as_full_v1_v5():
    for dataset in ("BREAK", "TaskBench", "TravelPlanner"):
        assert get_metric_profile(dataset).validity_components == {"V2", "V5"}
    assert get_metric_profile("smart-administration").validity_components == {"V1", "V2", "V5"}


def test_report_validation_rejects_non_applicable_coverage():
    with pytest.raises(ValueError, match="not applicable"):
        validate_reported_metrics("BREAK", ["coverage"])


def test_report_validation_allows_travelplanner_restricted_coverage():
    validate_reported_metrics("TravelPlanner", ["coverage", "utility"])


def test_unknown_dataset_has_no_assumed_metric_profile():
    with pytest.raises(ValueError, match="No Table 12 metric profile"):
        get_metric_profile("unknown")


def test_profile_registry_covers_all_five_paper_datasets():
    assert set(DATASET_METRIC_PROFILES) == {
        "BREAK", "StrategyQA", "TaskBench", "TravelPlanner", "smart-administration"
    }
