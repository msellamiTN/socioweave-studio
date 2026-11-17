import pytest

from sociodec.extraction import Hypothesis
from sociodec.models.decomposition import (
    Decomposition, DeliverableComposition, Dependency, Subproblem,
)
from sociodec.models.prompt import (
    Interpretation, Prompt, Requirement, RequirementType,
)
from sociodec.validation import (
    CheckStatus, HypothesisVerdict, HypothesisVerdictValue,
    validate_decomposition,
)


def setup_case():
    prompt = Prompt(
        "Build a permit service.",
        Interpretation(
            "Build a permit service",
            deliverables=("Service plan", "Rollout plan"),
        ),
    )
    r1 = Requirement("Reduce processing time", RequirementType.TARGET, "service")
    r2 = Requirement("Provide a rollout plan", RequirementType.DELIVERABLE, "planning")
    s1 = Subproblem("s1", "Design the service", ("Current process",), "Service design", (), (r1,))
    s2 = Subproblem("s2", "Plan rollout", ("Service design",), "Rollout plan", (), (r2,))
    good = Decomposition(
        (s1, s2),
        (Dependency("s1", "s2"),),
        (
            DeliverableComposition("Service plan", ("s1",)),
            DeliverableComposition("Rollout plan", ("s2",)),
        ),
    )
    return prompt, (r1, r2), s1, s2, good


def test_valid_structure_passes_v1_v2_v5_but_execution_checks_are_not_evaluated():
    prompt, requirements, _, _, decomposition = setup_case()
    report = validate_decomposition(prompt, requirements, decomposition)
    assert report.v1_coverage.status is CheckStatus.PASS
    assert report.v2_acyclicity.status is CheckStatus.PASS
    assert report.v5_composition.status is CheckStatus.PASS
    assert report.v3_solvability.status is CheckStatus.NOT_EVALUATED
    assert report.v4_faithfulness.status is CheckStatus.NOT_EVALUATED
    assert report.structural_valid is True
    assert report.execution_evaluated is False


def test_v1_reports_missing_requirements():
    prompt, requirements, s1, _, _ = setup_case()
    incomplete = Decomposition(
        (s1,), (),
        (
            DeliverableComposition("Service plan", ("s1",)),
            DeliverableComposition("Rollout plan", ("s1",)),
        ),
    )
    report = validate_decomposition(prompt, requirements, incomplete)
    assert report.v1_coverage.status is CheckStatus.FAIL
    finding = report.v1_coverage.findings[0]
    assert finding.code == "uncovered_requirements"
    assert "Provide a rollout plan" in finding.subjects


def test_v2_detects_self_loop_and_multi_node_cycle():
    prompt, requirements, s1, s2, _ = setup_case()
    self_loop = Decomposition(
        (s1,), (Dependency("s1", "s1"),),
        (
            DeliverableComposition("Service plan", ("s1",)),
            DeliverableComposition("Rollout plan", ("s1",)),
        ),
    )
    report = validate_decomposition(prompt, (requirements[0],), self_loop)
    assert report.v2_acyclicity.status is CheckStatus.FAIL
    assert report.v2_acyclicity.findings[0].subjects == ("s1", "s1")

    cyclic = Decomposition(
        (s1, s2),
        (Dependency("s1", "s2"), Dependency("s2", "s1")),
        (
            DeliverableComposition("Service plan", ("s1",)),
            DeliverableComposition("Rollout plan", ("s2",)),
        ),
    )
    report = validate_decomposition(prompt, requirements, cyclic)
    assert report.v2_acyclicity.status is CheckStatus.FAIL
    assert report.v2_acyclicity.findings[0].subjects[0] == report.v2_acyclicity.findings[0].subjects[-1]


def test_v5_reports_unowned_deliverable_and_sink_without_deliverable():
    prompt, requirements, s1, s2, _ = setup_case()
    d = Decomposition(
        (s1, s2), (Dependency("s1", "s2"),),
        (
            DeliverableComposition("Service plan", ("s1",)),
            DeliverableComposition("Rollout plan", ()),
        ),
    )
    report = validate_decomposition(prompt, requirements, d)
    codes = {f.code for f in report.v5_composition.findings}
    assert codes == {"unowned_deliverable", "sink_without_deliverable"}
    assert "Rollout plan" in report.v5_composition.findings[0].subjects


def test_sink_is_node_with_no_outgoing_edges():
    prompt, requirements, s1, s2, _ = setup_case()
    d = Decomposition(
        (s1, s2), (Dependency("s1", "s2"),),
        (
            DeliverableComposition("Service plan", ("s1",)),
            DeliverableComposition("Rollout plan", ("s2",)),
        ),
    )
    report = validate_decomposition(prompt, requirements, d)
    assert report.v5_composition.status is CheckStatus.PASS


def test_confirmed_hypothesis_joins_effective_requirement_universe():
    prompt, requirements, s1, s2, _ = setup_case()
    h = Hypothesis(
        "Maintain an audit trail", RequirementType.CONSTRAINT, "compliance"
    )
    confirmed_requirement = Requirement(
        h.statement, h.type, h.domain, source_span=None, entity_names=()
    )
    s3 = Subproblem(
        "s3", "Define audit trail", ("Service design",),
        "Audit trail design", (), (confirmed_requirement,),
    )
    d = Decomposition(
        (s1, s2, s3),
        (Dependency("s1", "s2"), Dependency("s1", "s3")),
        (
            DeliverableComposition("Service plan", ("s1", "s3")),
            DeliverableComposition("Rollout plan", ("s2",)),
        ),
    )
    report = validate_decomposition(
        prompt, requirements, d,
        hypotheses=(h,),
        verdicts=(HypothesisVerdict(h, HypothesisVerdictValue.CONFIRMED),),
    )
    assert report.hypothesis_verdicts.status is CheckStatus.PASS
    assert confirmed_requirement in report.effective_requirements
    assert report.v1_coverage.status is CheckStatus.PASS


def test_unresolved_hypothesis_is_failure_not_silently_discarded():
    prompt, requirements, _, _, d = setup_case()
    h = Hypothesis("Keep service multilingual", RequirementType.TARGET, "service")
    report = validate_decomposition(prompt, requirements, d, hypotheses=(h,))
    assert report.hypothesis_verdicts.status is CheckStatus.FAIL
    assert report.hypothesis_verdicts.findings[0].code == "missing_hypothesis_verdict"
    assert report.structural_valid is False


def test_rejected_hypothesis_does_not_join_requirement_universe():
    prompt, requirements, _, _, d = setup_case()
    h = Hypothesis("Build a mobile app", RequirementType.DELIVERABLE, "product")
    report = validate_decomposition(
        prompt, requirements, d,
        hypotheses=(h,),
        verdicts=(HypothesisVerdict(h, HypothesisVerdictValue.REJECTED),),
    )
    assert report.hypothesis_verdicts.status is CheckStatus.PASS
    assert all(r.statement != h.statement for r in report.effective_requirements)
    assert report.v1_coverage.status is CheckStatus.PASS


def test_duplicate_and_unknown_hypothesis_verdicts_are_reported():
    prompt, requirements, _, _, d = setup_case()
    h = Hypothesis("Keep service multilingual", RequirementType.TARGET, "service")
    other = Hypothesis("Add analytics", RequirementType.TARGET, "service")
    report = validate_decomposition(
        prompt, requirements, d,
        hypotheses=(h,),
        verdicts=(
            HypothesisVerdict(h, HypothesisVerdictValue.CONFIRMED),
            HypothesisVerdict(h, HypothesisVerdictValue.REJECTED),
            HypothesisVerdict(other, HypothesisVerdictValue.REJECTED),
        ),
    )
    codes = {f.code for f in report.hypothesis_verdicts.findings}
    assert "duplicate_hypothesis_verdict" in codes
    assert "unknown_hypothesis_verdict" in codes


def test_validator_rejects_composition_not_total_for_prompt():
    prompt, requirements, s1, _, _ = setup_case()
    invalid = Decomposition((s1,), (), (DeliverableComposition("Service plan", ("s1",)),))
    with pytest.raises(ValueError, match="missing deliverable key"):
        validate_decomposition(prompt, requirements, invalid)
