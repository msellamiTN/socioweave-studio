"""Direct E1 condition execution, independent of the adaptive selector.

A method adapter executes exactly one predeclared strategy or baseline.
The same fixed executor adapter is then used for every condition. This module
never calls Algorithm 2/run_adaptive and never selects a winning decomposition.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Mapping, Protocol

from sociodec.e1_protocol import E1Condition, BASELINES, e1_metric_obligations
from sociodec.equivalence import DEFAULT_MATCHER, SubproblemMatcher, equivalence_classes
from sociodec.execution import ExecutionRun, assess_execution, combine_validity
from sociodec.models.decomposition import Decomposition
from sociodec.models.prompt import Prompt, Requirement
from sociodec.validation import HypothesisVerdict, ValidationReport, validate_decomposition


@dataclass(frozen=True, slots=True)
class MethodRun:
    """One direct method output; calls count actual model invocations."""
    decomposition: Decomposition
    calls_made: int
    provider_trace: tuple[Mapping[str, object], ...] = ()
    hypothesis_verdicts: tuple[HypothesisVerdict, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.calls_made, bool) or not isinstance(self.calls_made, int) or self.calls_made < 0:
            raise ValueError("method calls_made must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class ExecutorRun:
    """Execution evidence plus actual executor model-call accounting."""
    execution: ExecutionRun
    calls_made: int
    provider_trace: tuple[Mapping[str, object], ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.calls_made, bool) or not isinstance(self.calls_made, int) or self.calls_made < 0:
            raise ValueError("executor calls_made must be a non-negative integer")


class DirectMethodAdapter(Protocol):
    def run(self, *, condition: E1Condition, prompt: Prompt, seed: int) -> MethodRun: ...


class E1FixedExecutor(Protocol):
    @property
    def executor_id(self) -> str: ...
    def execute(self, *, prompt: Prompt, decomposition: Decomposition, seed: int) -> ExecutorRun: ...


@dataclass(frozen=True, slots=True)
class DirectE1Result:
    dataset: str
    example_id: str
    method_id: str
    model_mode: str
    seed: int
    matched_strategy_id: str | None
    executor_id: str
    calls_method: int
    calls_executor: int
    calls_total: int
    call_budget: int
    structural: ValidationReport
    metrics: Mapping[str, float]
    provider_trace: tuple[Mapping[str, object], ...]
    metadata: Mapping[str, object]
    decomposition_sha256: str
    composed_answer_sha256: str


def _depth(decomposition: Decomposition) -> int:
    nodes = {item.identifier for item in decomposition.subproblems}
    if not nodes:
        raise ValueError("E1 decomposition must contain at least one subproblem")
    outgoing = {node: [] for node in nodes}
    indegree = {node: 0 for node in nodes}
    for source, target in decomposition.E:
        outgoing[source].append(target)
        indegree[target] += 1
    queue = sorted(node for node, degree in indegree.items() if degree == 0)
    distance = {node: 1 for node in nodes}
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for target in sorted(outgoing[node]):
            distance[target] = max(distance[target], distance[node] + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
                queue.sort()
    if visited != len(nodes):
        raise ValueError("Depth is undefined for a cyclic decomposition")
    return max(distance.values())


def _canonical_decomposition(decomposition: Decomposition) -> str:
    payload = {
        "subproblems": [{
            "id": item.identifier, "question": item.question,
            "inputs": list(item.inputs), "output": item.output,
            "constraints": sorted((c.kind.value, c.statement) for c in item.local_constraints),
            "coverage": sorted((r.type.value, r.domain, r.statement) for r in item.covered_requirements),
        } for item in decomposition.subproblems],
        "dependencies": sorted([list(edge) for edge in decomposition.E]),
        "composition": {key: sorted(value) for key, value in sorted(decomposition.kappa.items())},
    }
    import json
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def run_direct_e1_condition(
    *,
    condition: E1Condition,
    example_id: str,
    prompt: Prompt,
    requirements: tuple[Requirement, ...],
    hypotheses: tuple = (),
    method: DirectMethodAdapter,
    executor: E1FixedExecutor,
    expected_executor_id: str,
    seed: int,
    matcher: SubproblemMatcher = DEFAULT_MATCHER,
    utility_scorer=None,
) -> DirectE1Result:
    """Run one E1 row as method -> shared executor -> metrics.

    The caller supplies frozen prompt identity and pre-registered condition.
    The method adapter must be specific to condition.method_id; it may not
    delegate to adaptive selection. The fixed executor identity is checked.
    """
    if not example_id.strip():
        raise ValueError("example_id must be non-empty")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if not expected_executor_id.strip() or executor.executor_id != expected_executor_id:
        raise ValueError("fixed executor identity mismatch")
    method_run = method.run(condition=condition, prompt=prompt, seed=seed)
    if not isinstance(method_run, MethodRun):
        raise TypeError("method adapter must return MethodRun")
    if condition.method_id in BASELINES and condition.matched_strategy_id is None:
        raise ValueError("baseline condition must identify its matched strategy")
    if condition.method_id not in BASELINES and condition.matched_strategy_id is not None:
        raise ValueError("strategy condition cannot specify matched_strategy_id")

    structural = validate_decomposition(
        prompt, requirements, method_run.decomposition,
        hypotheses=hypotheses, verdicts=method_run.hypothesis_verdicts,
    )
    executor_run = executor.execute(
        prompt=prompt, decomposition=method_run.decomposition, seed=seed,
    )
    if not isinstance(executor_run, ExecutorRun):
        raise TypeError("fixed executor must return ExecutorRun")
    if executor_run.execution.executor_id != expected_executor_id:
        raise ValueError("ExecutionRun executor identity differs from the preregistered executor")

    calls_total = method_run.calls_made + executor_run.calls_made
    if calls_total > condition.call_budget:
        raise RuntimeError(
            f"E1 call budget exceeded: {calls_total} actual calls > {condition.call_budget} registered calls"
        )
    execution = assess_execution(prompt, method_run.decomposition, executor_run.execution)
    full = combine_validity(structural, execution)
    obligations = e1_metric_obligations(condition.dataset)
    metrics: dict[str, float] = {
        "validity": float(full.fully_valid),
        "redundancy": sum(
            len(group) for group in equivalence_classes(method_run.decomposition.subproblems, matcher)
            if len(group) > 1
        ) / len(method_run.decomposition.subproblems),
        "coupling": len(method_run.decomposition.E) / len(method_run.decomposition.subproblems),
        "depth": float(_depth(method_run.decomposition)),
        "solvability": sum(x.status.value == "solved" for x in executor_run.execution.executions)
            / len(executor_run.execution.executions) if executor_run.execution.executions else 0.0,
    }
    if "coverage" in obligations:
        effective = structural.effective_requirements
        if not effective:
            raise ValueError("Coverage obligation exists but effective requirement set is empty")
        metrics["coverage"] = len(method_run.decomposition.cov & frozenset(effective)) / len(effective)
    if utility_scorer is not None:
        utility = utility_scorer(prompt, executor_run.execution.composed_answer)
        if isinstance(utility, bool) or not isinstance(utility, (int, float)) or not math.isfinite(utility) or not 0 <= utility <= 1:
            raise ValueError("utility_scorer must return a finite value in [0,1]")
        metrics["utility"] = float(utility)

    decomposition_hash = hashlib.sha256(_canonical_decomposition(method_run.decomposition).encode()).hexdigest()
    answer_hash = hashlib.sha256(executor_run.execution.composed_answer.encode("utf-8")).hexdigest()
    trace = tuple(dict(item) for item in (*method_run.provider_trace, *executor_run.provider_trace))
    metadata = {
        "method_metadata": dict(method_run.metadata),
        "v1": structural.v1_coverage.status.value,
        "v2": structural.v2_acyclicity.status.value,
        "v3": execution.v3_solvability.status.value,
        "v4": execution.v4_faithfulness.status.value,
        "v5": structural.v5_composition.status.value,
        "hypothesis_verdicts": structural.hypothesis_verdicts.status.value,
        "trace_entries": len(trace),
        "trace_is_complete": bool(trace) and len(trace) >= calls_total,
    }
    return DirectE1Result(
        condition.dataset, example_id, condition.method_id, condition.model_mode,
        condition.seed, condition.matched_strategy_id, expected_executor_id,
        method_run.calls_made, executor_run.calls_made, calls_total,
        condition.call_budget, structural, metrics, trace, metadata,
        decomposition_hash, answer_hash,
    )
