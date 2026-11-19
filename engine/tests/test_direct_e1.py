import pytest

from sociodec.direct_e1 import (
    DirectE1Result, ExecutorRun, MethodRun, run_direct_e1_condition,
)
from sociodec.e1_protocol import E1Condition
from sociodec.execution import (
    ConstraintAssessment, ExecutionRun, ExecutionStatus, SubproblemExecution,
)
from sociodec.models.decomposition import Decomposition, DeliverableComposition, Subproblem
from sociodec.models.prompt import (
    Constraint, ConstraintKind, Interpretation, Prompt, Requirement, RequirementType, SourceSpan,
)

REQ = Requirement("Create a report", RequirementType.DELIVERABLE, "report", SourceSpan(0, 16))
HARD = Constraint("Must be accessible", ConstraintKind.HARD)
PROMPT = Prompt("Create a report.", Interpretation(
    "Create a report", constraints=(HARD,), deliverables=("Report",)
))
D = Decomposition(
    (Subproblem("s1", "Create report", (), "Report", (), (REQ,)),),
    (), (DeliverableComposition("Report", ("s1",)),),
)
CONDITION = E1Condition("smart-administration", "S2", "heterogeneous", 0, ("p-001",), 4)


class Method:
    def __init__(self, calls=2):
        self.calls = calls
    def run(self, *, condition, prompt, seed):
        assert condition.method_id == "S2"
        return MethodRun(D, self.calls, ({"call": i} for i in range(self.calls)))


class Executor:
    executor_id = "ME-fixed-v1"
    def __init__(self, calls=1):
        self.calls = calls
    def execute(self, *, prompt, decomposition, seed):
        run = ExecutionRun(
            self.executor_id,
            (SubproblemExecution("s1", ExecutionStatus.SOLVED, "Report completed"),),
            "Accessible report completed.",
            (ConstraintAssessment(HARD, True, "Accessibility checked"),),
        )
        return ExecutorRun(run, self.calls, tuple({"executor_call": i} for i in range(self.calls)))


def test_direct_strategy_runs_without_adaptive_selector_and_uses_fixed_executor():
    result = run_direct_e1_condition(
        condition=CONDITION, example_id="p-001", prompt=PROMPT,
        requirements=(REQ,), method=Method(), executor=Executor(),
        expected_executor_id="ME-fixed-v1", seed=17,
        utility_scorer=lambda prompt, answer: 0.9,
    )
    assert isinstance(result, DirectE1Result)
    assert result.calls_total == 3
    assert result.metrics["coverage"] == 1.0
    assert result.metrics["validity"] == 1.0
    assert result.metrics["utility"] == 0.9
    assert result.metadata["trace_is_complete"] is True


def test_method_calls_must_fit_registered_budget():
    with pytest.raises(RuntimeError, match="method-call budget exceeded"):
        run_direct_e1_condition(
            condition=CONDITION, example_id="p-001", prompt=PROMPT,
            requirements=(REQ,), method=Method(calls=5), executor=Executor(calls=1),
            expected_executor_id="ME-fixed-v1", seed=17,
        )


def test_fixed_executor_calls_are_reported_but_do_not_consume_strategy_budget():
    result = run_direct_e1_condition(
        condition=CONDITION, example_id="p-001", prompt=PROMPT,
        requirements=(REQ,), method=Method(calls=4), executor=Executor(calls=3),
        expected_executor_id="ME-fixed-v1", seed=17,
    )
    assert result.calls_method == 4
    assert result.calls_executor == 3
    assert result.calls_total == 7
    assert result.metadata["method_call_budget"] == 4
    assert result.metadata["executor_calls_excluded_from_method_budget"] == 3


def test_executor_identity_is_fixed_and_verified():
    with pytest.raises(ValueError, match="identity mismatch"):
        run_direct_e1_condition(
            condition=CONDITION, example_id="p-001", prompt=PROMPT,
            requirements=(REQ,), method=Method(), executor=Executor(),
            expected_executor_id="ME-other", seed=17,
        )


def test_baseline_must_be_explicitly_budget_matched():
    baseline = E1Condition(
        "smart-administration", "single_plan_and_solve", "heterogeneous",
        0, ("p-001",), 4, matched_strategy_id="S2",
    )
    class BaselineMethod(Method):
        def run(self, *, condition, prompt, seed):
            return MethodRun(D, 2)
    result = run_direct_e1_condition(
        condition=baseline, example_id="p-001", prompt=PROMPT,
        requirements=(REQ,), method=BaselineMethod(), executor=Executor(),
        expected_executor_id="ME-fixed-v1", seed=17,
    )
    assert result.matched_strategy_id == "S2"
