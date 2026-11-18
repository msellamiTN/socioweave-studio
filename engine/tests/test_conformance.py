import pytest
from dataclasses import replace

from sociodec.catalogue import StrategyId
from sociodec.conformance import (
    PROFILE_BY_ID, PROFILES, build_and_validate_all, profile_as_dict, validate_blueprint,
)
from sociodec.models.strategy import (
    Action, DecisionRule, ProtocolStep, Role, SocialStrategy, VisibilityRound,
)
from sociodec.strategy_protocols import StrategyBlueprint, build_strategy_blueprint
from sociodec.runtime import run_strategy
from sociodec.models.prompt import Interpretation, Prompt


@pytest.mark.parametrize(
    "n,k,T",
    [(1, 1, 1), (3, 3, 2), (5, 4, 3)],
    ids=["minimum", "typical", "larger"],
)
def test_all_thirteen_profiles_conform_to_blueprints_at_boundary_configurations(n, k, T):
    reports = build_and_validate_all(n=n, k=k, T=T)
    assert len(reports) == 13
    assert {report.strategy_id for report in reports} == set(StrategyId)
    failures = [
        (report.strategy_id.value, finding.invariant, finding.message)
        for report in reports for finding in report.findings
    ]
    assert failures == []


def test_profile_oracle_covers_only_thirteen_established_strategies():
    assert len(PROFILES) == 13
    assert set(PROFILE_BY_ID) == set(StrategyId)
    assert not any(profile.strategy_id.value.startswith("C") for profile in PROFILES)
    assert PROFILE_BY_ID[StrategyId.S11].table4_calls_formula == "5"
    assert PROFILE_BY_ID[StrategyId.S11].runtime_calls_formula == "2+3T"


def prompt():
    return Prompt("Conformance test prompt", Interpretation("Conformance goal"))


def _blueprint(sid=StrategyId.S3):
    return build_strategy_blueprint(sid, n=3, k=3, T=2)


def test_conformance_detects_prompt_view_roster_leak_or_omission():
    blueprint = _blueprint()
    mutated = replace(blueprint, prompt_views={"member-1": "view"})
    report = validate_blueprint(mutated)
    assert any(f.invariant == "prompt-view-roster" for f in report.findings)


def test_conformance_detects_wrong_decision_rule():
    blueprint = _blueprint()
    strategy = replace(blueprint.strategy, decision_rule=DecisionRule.MAJORITY)
    report = validate_blueprint(replace(blueprint, strategy=strategy))
    assert any(f.invariant == "decision-rule" for f in report.findings)


def test_conformance_detects_role_assignment_drift():
    blueprint = _blueprint(StrategyId.S5)
    assignments = list(blueprint.strategy.assignments)
    assignments[0] = replace(assignments[0], role=Role.CRITIC)
    strategy = replace(blueprint.strategy, assignments=tuple(assignments))
    report = validate_blueprint(replace(blueprint, strategy=strategy))
    assert any(f.invariant == "role-assignment" for f in report.findings)


def test_conformance_detects_visibility_mutation():
    blueprint = _blueprint()
    visibility = list(blueprint.strategy.visibility)
    visibility[0] = VisibilityRound(1, (("member-1", "member-1"),
                                        ("member-2", "member-2"),
                                        ("member-3", "member-3"),
                                        ("member-1", "member-2")))
    strategy = replace(blueprint.strategy, visibility=tuple(visibility))
    report = validate_blueprint(replace(blueprint, strategy=strategy))
    assert any(f.invariant == "visibility" for f in report.findings)


def test_conformance_detects_protocol_input_reference_mutation():
    blueprint = _blueprint()
    steps = list(blueprint.strategy.protocol)
    steps[-1] = replace(steps[-1], input_ref="step:999")
    strategy = replace(blueprint.strategy, protocol=tuple(steps))
    report = validate_blueprint(replace(blueprint, strategy=strategy))
    assert any(f.invariant == "protocol-sequence" for f in report.findings)
    assert any(f.invariant == "input-reference" for f in report.findings)


def test_conformance_detects_model_call_accounting_drift():
    blueprint = _blueprint()
    steps = list(blueprint.strategy.protocol)
    steps[0] = replace(steps[0], invokes_model=False)
    strategy = replace(blueprint.strategy, protocol=tuple(steps))
    report = validate_blueprint(replace(blueprint, strategy=strategy))
    assert any(f.invariant == "call-formula" for f in report.findings)


def test_candidate_strategy_is_not_a_paper_profile():
    with pytest.raises(ValueError):
        build_strategy_blueprint("C1")


def test_profile_export_is_machine_readable_and_keeps_paper_and_runtime_costs_distinct():
    profile = profile_as_dict(StrategyId.S11)
    assert profile["strategy_id"] == "S11"
    assert profile["decision_rule"] == "compromise"
    assert profile["table4_calls_formula"] == "5"
    assert profile["runtime_calls_formula"] == "2+3T"
    assert "C1" not in profile.values()


class ConformanceInvoker:
    def invoke(self, agent, step, context):
        if step.action is Action.SUMMARISE:
            return '{"summary":"neutral summary","agreements":["a"],"disagreements":["b"]}'
        if step.action is Action.JUDGE and agent.identifier == "editor":
            return '{"verdict":"accept","rationale":"accepted"}'
        return '{"candidate":{"stable":"candidate"}}'


@pytest.mark.parametrize("sid", list(StrategyId), ids=lambda sid: sid.value)
def test_runtime_execution_reconciles_with_blueprint_and_actual_output_accounting(sid):
    n, k, T = 2, 2, 1
    views = None
    if sid is StrategyId.S1:
        views = {"coordinator": "FULL_PROMPT", "specialist-1": "DOMAIN:1", "specialist-2": "DOMAIN:2"}
    elif sid is StrategyId.S12:
        views = {"expert-1": "FACET:1", "expert-2": "FACET:2", "integrator": "FULL_PROMPT"}
    blueprint = build_strategy_blueprint(sid, n=n, k=k, T=T, prompt_views=views)
    report = validate_blueprint(blueprint, n=n, k=k, T=T)
    assert report.passed, report.findings

    run = run_strategy(
        sid.value, prompt(), blueprint.strategy, ConformanceInvoker(),
        prompt_views=blueprint.prompt_views,
    )
    expected_calls = blueprint.strategy.calls
    if sid is StrategyId.S8:
        expected_calls -= 1  # ACCEPT skips the conditional author revision.
    assert run.calls_made == expected_calls
    assert run.model_invocations == run.calls_made
    assert run.protocol_steps == len(run.outputs)
    assert run.depth_executed == len({item.stage for item in run.outputs})
    assert run.depth_executed <= blueprint.strategy.depth
    assert run.accounting_reconciles


def test_conformance_detects_step_reference_that_violates_visibility():
    blueprint = _blueprint(StrategyId.S7)
    steps = list(blueprint.strategy.protocol)
    # party-1 cannot inspect party-2's draft during the defence stage.
    steps[2] = replace(steps[2], input_ref="step:1")
    strategy = replace(blueprint.strategy, protocol=tuple(steps))
    report = validate_blueprint(replace(blueprint, strategy=strategy))
    assert any(f.invariant == "input-visibility" for f in report.findings)
