"""End-to-end adaptive orchestration around the paper's Algorithm 2.

LLM/provider and strategy-specific protocol construction remain injected
adapters. This module owns sequencing, budget accounting, seeding, structural
validation/repair, escalation, result comparison and an auditable trace.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

from sociodec.extraction import AggregatedExtraction
from sociodec.models.decomposition import Decomposition
from sociodec.models.prompt import Prompt
from sociodec.repair import RepairCallback, repair_decomposition
from sociodec.selector import PlanItem, Diagnosis, diagnose_features, plan_strategy_chain
from sociodec.validation import (
    HypothesisVerdict, ValidationFinding, ValidationReport,
)


@dataclass(frozen=True, slots=True)
class StrategyOutcome:
    """Result of one fully executed social strategy adapter."""
    decomposition: Decomposition
    calls_made: int
    hypothesis_verdicts: tuple[HypothesisVerdict, ...] = ()
    candidate_support_counts: tuple[tuple[tuple[str, str], int], ...] = ()
    findings: tuple[ValidationFinding, ...] = ()
    strategy_run_id: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.calls_made, bool) or not isinstance(self.calls_made, int) or self.calls_made < 0:
            raise ValueError("calls_made must be a non-negative integer")
        keys = [edge for edge, _ in self.candidate_support_counts]
        if len(keys) != len(set(keys)):
            raise ValueError("candidate support edge counts must be unique")
        for edge, count in self.candidate_support_counts:
            if len(edge) != 2 or not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError("candidate support counts require edge pairs and non-negative integers")


class InitialDrafter(Protocol):
    def __call__(self, prompt: Prompt, extraction: AggregatedExtraction, author_index: int) -> Decomposition: ...


class StrategyExecutor(Protocol):
    def __call__(
        self, item: PlanItem, prompt: Prompt, extraction: AggregatedExtraction,
        initial_drafts: tuple[Decomposition, Decomposition],
        chain_seed: Decomposition | None,
        available_calls: int,
    ) -> StrategyOutcome: ...


class ExtractionRunner(Protocol):
    def __call__(self, prompt: Prompt) -> AggregatedExtraction: ...


@dataclass(frozen=True, slots=True)
class OrchestrationEvent:
    sequence: int
    kind: str
    detail: str
    calls_after_event: int


@dataclass(frozen=True, slots=True)
class StrategyExecutionRecord:
    item: PlanItem
    seed_supplied: bool
    outcome: StrategyOutcome
    validation: ValidationReport
    repair_calls: int
    removed_edges: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class AdaptiveResult:
    best: Decomposition
    best_validation: ValidationReport
    best_failures: tuple[ValidationFinding, ...]
    extraction: AggregatedExtraction
    diagnosis: Diagnosis
    initial_union: Decomposition
    initial_validation: ValidationReport
    strategy_records: tuple[StrategyExecutionRecord, ...]
    strategies_not_run: tuple[PlanItem, ...]
    calls_made: int
    budget: int
    events: tuple[OrchestrationEvent, ...]
    terminated_reason: str


def _item_cost(item: PlanItem, *, n: int, k: int, T: int) -> int:
    from sociodec.catalogue import StrategyId, get_strategy
    if item is PlanItem.C8_BRAINSTORM_THEN_REVIEW:
        ids = (StrategyId.S2, StrategyId.S8)
    elif item is PlanItem.COMBO_JIGSAW_THEN_CRITIC:
        ids = (StrategyId.S12, StrategyId.S5)
    elif item is PlanItem.COMBO_FULL_PIPELINE:
        ids = (StrategyId.S3, StrategyId.S6, StrategyId.S4, StrategyId.S7)
    else:
        ids = (StrategyId(item.value),)
    return sum(get_strategy(identifier).calls(n=n, k=k, T=T) for identifier in ids)


def _failure_codes(findings: Iterable[ValidationFinding]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.code for item in findings))


def _escalation_target(
    findings: Iterable[ValidationFinding], high_stakes: bool,
    already_run: set[PlanItem],
) -> PlanItem | None:
    codes = set(_failure_codes(findings))
    if codes & {"uncovered_requirements", "missing_hypothesis_verdict"}:
        target = PlanItem.COMBO_JIGSAW_THEN_CRITIC
    elif codes & {
        "dependency_cycle", "unowned_deliverable", "sink_without_deliverable",
        "coverage_outside_requirement_set",
    }:
        target = PlanItem.S8
    elif codes or high_stakes:
        target = PlanItem.COMBO_FULL_PIPELINE
    else:
        return None
    return None if target in already_run else target


def _quality_key(
    decomposition: Decomposition,
    findings: tuple[ValidationFinding, ...],
    requirements: tuple,
) -> tuple[int, int, int, float]:
    """Paper lexicographic order: fewest failures, coverage, redundancy, coupling."""
    signatures = [
        (item.output.strip().casefold(),
         tuple(sorted(x.statement.strip().casefold() for x in item.covered_requirements)))
        for item in decomposition.subproblems
    ]
    duplicates = len(signatures) - len(set(signatures))
    covered = len(decomposition.cov & frozenset(requirements))
    coupling = len(decomposition.E) / max(1, len(decomposition.subproblems))
    return (-len(findings), covered, -duplicates, -coupling)


def run_adaptive(
    prompt: Prompt,
    *,
    extract: ExtractionRunner,
    draft: InitialDrafter,
    execute_strategy: StrategyExecutor,
    budget: int,
    high_stakes: bool,
    model_families: int,
    open_prompt: bool = False,
    stakeholder_values: bool = False,
    justified_plan: bool = False,
    epsilon: float = 0.1,
    theta_c: int = 5,
    n: int = 3,
    k: int = 3,
    T: int = 2,
    repair_callback: RepairCallback | None = None,
) -> AdaptiveResult:
    """Run diagnose, select, sequential chaining and escalation within budget.

    The draft adapter is called twice with author indices 0 and 1; it must
    provide isolated contexts. The strategy adapter constructs/runs the
    relevant SocialStrategy and applies its decision operator.
    """
    if budget < 0:
        raise ValueError("budget must be non-negative")
    if model_families < 1:
        raise ValueError("model_families must be >= 1")

    events: list[OrchestrationEvent] = []
    records: list[StrategyExecutionRecord] = []
    not_run: list[PlanItem] = []
    calls = 0

    def emit(kind: str, detail: str) -> None:
        events.append(OrchestrationEvent(len(events) + 1, kind, detail, calls))

    extraction = extract(prompt)
    if not isinstance(extraction, AggregatedExtraction):
        raise TypeError("extract adapter must return AggregatedExtraction")
    q = len(extraction.extractor_results)
    if q < 1:
        raise ValueError("Algorithm 2 requires at least one extractor result")
    calls += q
    emit("extraction", f"Aggregated {q} extractor result(s)")

    if calls + 2 > budget:
        raise ValueError("Budget cannot cover extraction and two mandatory initial drafts")
    draft_a = draft(prompt, extraction, 0)
    if not isinstance(draft_a, Decomposition):
        raise TypeError("initial drafter must return Decomposition")
    calls += 1
    emit("initial_draft", "Initial isolated draft Da produced by author 0")
    draft_b = draft(prompt, extraction, 1)
    if not isinstance(draft_b, Decomposition):
        raise TypeError("initial drafter must return Decomposition")
    calls += 1
    emit("initial_draft", "Initial isolated draft Db produced by author 1")

    diagnosis = diagnose_features(
        extraction, draft_a, draft_b, high_stakes=high_stakes,
        model_families=model_families, open_prompt=open_prompt,
        stakeholder_values=stakeholder_values, justified_plan=justified_plan,
    )
    emit("diagnosis", f"dist={diagnosis.initial_distance:.6f}; gapS={diagnosis.features.content_gap:.6f}; gapE={diagnosis.features.structure_gap:.6f}; rho={diagnosis.features.mean_coupling:.6f}")

    initial = diagnosis.initial_union
    support = {
        edge: int(edge in draft_a.E) + int(edge in draft_b.E)
        for edge in initial.E
    }
    initial_repair = repair_decomposition(
        prompt, extraction.requirements, initial, support,
        hypotheses=extraction.hypotheses, verdicts=(),
        repair_callback=None,
    )
    calls += int(initial_repair.repair_call_made)
    initial_validation = initial_repair.final_report
    best = initial_repair.decomposition
    best_validation = initial_validation
    best_findings = initial_validation.failures
    effective_requirements = initial_validation.effective_requirements
    emit("initial_union", f"Union checked; removed {len(initial_repair.removed_edges)} cycle edge(s); failures={len(best_findings)}")

    plan = plan_strategy_chain(
        diagnosis.features, initial_distance=diagnosis.initial_distance,
        failures=(), budget=budget, extraction_calls=q,
        epsilon=epsilon, theta_c=theta_c, n=n, k=k, T=T,
    )
    queue = list(plan.items)
    not_run.extend(plan.not_run)
    already_run: set[PlanItem] = set()
    seed: Decomposition | None = None
    escalation_count = 0
    if not queue:
        initial_target = _escalation_target(best_findings, high_stakes, already_run)
        if initial_target is not None:
            queue = [initial_target]
            escalation_count += 1
            emit("escalation", f"Scheduled {initial_target.value} after initial union check")
    terminated_reason = "strategy chain completed"

    while queue:
        item = queue.pop(0)
        if item in already_run:
            continue
        reserved = _item_cost(item, n=n, k=k, T=T) + 1
        if calls + reserved > budget:
            not_run.append(item)
            not_run.extend(queue)
            terminated_reason = "budget exhausted before next strategy"
            emit("budget_stop", f"Strategy {item.value} and remaining chain not run")
            break

        available_strategy_calls = budget - calls - 1
        outcome = execute_strategy(item, prompt, extraction, (draft_a, draft_b), seed, available_strategy_calls)
        if not isinstance(outcome, StrategyOutcome):
            raise TypeError("execute_strategy must return StrategyOutcome")
        if outcome.calls_made > available_strategy_calls:
            raise RuntimeError("Strategy adapter exceeded the remaining call budget reserved before repair")
        calls += outcome.calls_made
        repaired = repair_decomposition(
            prompt, extraction.requirements, outcome.decomposition,
            dict(outcome.candidate_support_counts),
            hypotheses=extraction.hypotheses,
            verdicts=outcome.hypothesis_verdicts,
            repair_callback=repair_callback,
        )
        repair_calls = int(repaired.repair_call_made)
        calls += repair_calls
        if calls > budget:
            raise RuntimeError("Repair exceeded the remaining call budget")
        findings = tuple((*repaired.final_report.failures, *outcome.findings))
        records.append(StrategyExecutionRecord(
            item, seed is not None, outcome, repaired.final_report,
            repair_calls, repaired.removed_edges,
        ))
        already_run.add(item)
        emit("strategy", f"{item.value}: calls={outcome.calls_made}, repair_calls={repair_calls}, failures={len(findings)}")

        if _quality_key(repaired.decomposition, findings, effective_requirements) > _quality_key(best, best_findings, effective_requirements):
            best = repaired.decomposition
            best_validation = repaired.final_report
            best_findings = findings
            emit("best_update", f"{item.value} became current best under paper lexicographic order")

        seed = repaired.decomposition

        if not queue and escalation_count < 3:
            target = _escalation_target(findings, high_stakes, already_run)
            if target is not None:
                queue = [target]
                escalation_count += 1
                emit("escalation", f"Scheduled {target.value} after {item.value}")
    if escalation_count >= 3:
        terminated_reason = "maximum three escalations reached"

    return AdaptiveResult(
        best=best, best_validation=best_validation, best_failures=best_findings,
        extraction=extraction, diagnosis=diagnosis, initial_union=initial,
        initial_validation=initial_validation, strategy_records=tuple(records),
        strategies_not_run=tuple(dict.fromkeys(not_run)), calls_made=calls,
        budget=budget, events=tuple(events), terminated_reason=terminated_reason,
    )
