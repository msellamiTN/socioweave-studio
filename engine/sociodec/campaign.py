"""Fixed-executor evaluation adapter for adaptive SocioDec trials.

This module executes the selected decomposition with a caller-configured,
fixed executor and passes its evidence through Core 15 finalization. It does
not infer utility or faithfulness from the model's own unverified claims.
"""
from __future__ import annotations

import hashlib
from collections import Counter, defaultdict, deque
from typing import Callable, Protocol

from sociodec.decisions import subproblem_signature
from sociodec.execution import ExecutionRun
from sociodec.finalization import FinalAdaptiveEvaluation, finalize_adaptive_result
from sociodec.metrics import process_gain
from sociodec.orchestrator import AdaptiveResult
from sociodec.experiments import TrialOutcome
from sociodec.models.prompt import Prompt


class FixedExecutor(Protocol):
    """Executor identity is fixed across all strategy conditions in a study."""
    @property
    def executor_id(self) -> str: ...
    def execute(self, prompt: Prompt, decomposition, *, seed: int) -> ExecutionRun: ...


UtilityScorer = Callable[[Prompt, str], float]


def _dag_depth(decomposition) -> int:
    ids = [item.identifier for item in decomposition.subproblems]
    if not ids:
        raise ValueError("Cannot compute depth for an empty decomposition")
    outgoing = defaultdict(list)
    indegree = {identifier: 0 for identifier in ids}
    for source, target in decomposition.E:
        outgoing[source].append(target)
        indegree[target] += 1
    queue = deque(sorted(identifier for identifier, degree in indegree.items() if degree == 0))
    distance = {identifier: 1 for identifier in ids}
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for target in sorted(outgoing[node]):
            distance[target] = max(distance[target], distance[node] + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if visited != len(ids):
        raise ValueError("Depth is undefined for a cyclic dependency graph")
    return max(distance.values())


def _redundancy(decomposition) -> float:
    signatures = [subproblem_signature(item) for item in decomposition.subproblems]
    counts = Counter(signatures)
    return sum(count for count in counts.values() if count > 1) / len(signatures)


def evaluate_adaptive_trial(
    result: AdaptiveResult,
    executor: FixedExecutor,
    *,
    seed: int,
    expected_executor_id: str,
    utility_scorer: UtilityScorer | None = None,
    provider_trace: tuple[dict[str, object], ...] = (),
) -> tuple[TrialOutcome, FinalAdaptiveEvaluation]:
    """Run one fixed-executor evaluation and produce auditable trial metrics.

    V3/V4 are emitted only from ExecutionRun evidence. Utility is omitted
    unless a separate scorer evaluates the composed answer. The executor
    identity is checked against the experiment's predeclared fixed identity.
    """
    if not expected_executor_id.strip():
        raise ValueError("expected_executor_id must be non-empty")
    if executor.executor_id != expected_executor_id:
        raise ValueError(
            f"Executor mismatch: expected {expected_executor_id!r}, "
            f"received {executor.executor_id!r}"
        )
    run = executor.execute(result.prompt, result.best, seed=seed)
    if not isinstance(run, ExecutionRun):
        raise TypeError("FixedExecutor.execute must return ExecutionRun")
    if run.executor_id != expected_executor_id:
        raise ValueError("ExecutionRun.executor_id differs from the fixed executor identity")

    final = finalize_adaptive_result(result, execution_run=run)
    structural = final.structural
    effective = structural.effective_requirements
    if not effective:
        raise ValueError("Coverage is undefined when the effective requirement set is empty")
    covered = result.best.cov & frozenset(effective)
    metrics: dict[str, float] = {
        "coverage": len(covered) / len(effective),
        "redundancy": _redundancy(result.best),
        "coupling": len(result.best.E) / len(result.best.subproblems),
        "depth": float(_dag_depth(result.best)),
        "structural_valid": float(structural.structural_valid),
        "v3_solvability": float(final.execution.v3_solvability.status.value == "pass"),
        "v4_faithfulness": float(final.execution.v4_faithfulness.status.value == "pass"),
        "fully_valid": float(bool(final.fully_valid)),
        "subproblem_solvability": sum(
            item.status.value == "solved" for item in run.executions
        ) / len(run.executions) if run.executions else 0.0,
    }
    if utility_scorer is not None:
        utility = utility_scorer(result.prompt, run.composed_answer)
        if isinstance(utility, bool) or not isinstance(utility, (int, float)) or not 0.0 <= float(utility) <= 1.0:
            raise ValueError("utility_scorer must return a finite score in [0, 1]")
        metrics["utility"] = float(utility)

    answer_hash = hashlib.sha256(run.composed_answer.encode("utf-8")).hexdigest()
    metadata = {
        "executor_id": expected_executor_id,
        "strategy_run_id": result.best_strategy_run_id,
        "orchestrator_calls": result.calls_made,
        "orchestrator_budget": result.budget,
        "execution_records": len(run.executions),
        "execution_failures": sum(item.status.value == "failed" for item in run.executions),
        "composed_answer_sha256": answer_hash,
        "v3_status": final.execution.v3_solvability.status.value,
        "v4_status": final.execution.v4_faithfulness.status.value,
        "v3_findings": [item.code for item in final.execution.v3_solvability.findings],
        "v4_findings": [item.code for item in final.execution.v4_faithfulness.findings],
        "provider_trace_count": len(provider_trace),
    }
    return TrialOutcome(metrics, provider_trace, metadata), final
