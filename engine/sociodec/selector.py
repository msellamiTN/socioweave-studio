"""Paper-aligned adaptive strategy diagnosis and decision-list planner.

Implements the feature diagnosis and Table 8 decision list from Section 7.3.
It plans established strategies and paper-described combinations; it does not
execute LLM calls or claim that a selected strategy is effective.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from sociodec.catalogue import StrategyId, get_strategy
from sociodec.decisions import decomposition_distance
from sociodec.extraction import AggregatedExtraction
from sociodec.models.decomposition import Decomposition


DEFAULT_EPSILON = 0.1
DEFAULT_THETA_C = 5


class PlanItem(StrEnum):
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"
    S6 = "S6"
    S7 = "S7"
    S8 = "S8"
    S9 = "S9"
    S10 = "S10"
    S11 = "S11"
    S12 = "S12"
    S13 = "S13"
    C8_BRAINSTORM_THEN_REVIEW = "C8: S2 then S8"
    COMBO_JIGSAW_THEN_CRITIC = "Jigsaw then Devil's Advocate"
    COMBO_FULL_PIPELINE = "Nominal Group, Dialectical Inquiry, Delphi, Adversarial Procedure"


@dataclass(frozen=True, slots=True)
class PromptFeatures:
    constraint_count: int
    domain_count: int
    hypothesis_count: int
    ambiguity: bool
    conflict: bool
    open_prompt: bool
    stakeholder_values: bool
    justified_plan: bool
    content_gap: float
    structure_gap: float
    mean_coupling: float
    high_stakes: bool
    model_families: int

    def __post_init__(self) -> None:
        for name in ("constraint_count", "domain_count", "hypothesis_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if isinstance(self.model_families, bool) or not isinstance(self.model_families, int) or self.model_families < 1:
            raise ValueError("model_families must be an integer >= 1")
        for name in ("content_gap", "structure_gap", "mean_coupling"):
            value = getattr(self, name)
            upper = 1 if name in {"content_gap", "structure_gap"} else float("inf")
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= upper:
                raise ValueError(f"{name} must be in [0, 1]" if upper == 1 else f"{name} must be non-negative")
        for name in ("ambiguity", "conflict", "open_prompt", "stakeholder_values", "justified_plan", "high_stakes"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be boolean")

    @property
    def any_flag(self) -> bool:
        return any((self.ambiguity, self.conflict, self.open_prompt,
                    self.stakeholder_values, self.justified_plan))


@dataclass(frozen=True, slots=True)
class StrategyPlan:
    items: tuple[PlanItem, ...]
    rule_ids: tuple[str, ...]
    not_run: tuple[PlanItem, ...]
    calls_reserved: int
    budget: int
    reason: str


@dataclass(frozen=True, slots=True)
class Diagnosis:
    features: PromptFeatures
    initial_union: Decomposition
    initial_distance: float


def diagnose_features(
    extraction: AggregatedExtraction,
    draft_a: Decomposition,
    draft_b: Decomposition,
    *,
    high_stakes: bool,
    model_families: int,
    open_prompt: bool = False,
    stakeholder_values: bool = False,
    justified_plan: bool = False,
) -> Diagnosis:
    """Derive estimated features from extraction and two isolated drafts.

    Isolation of draft generation is a caller-side protocol requirement and
    cannot be established by inspecting the two resulting decompositions.
    """
    from sociodec.decisions import Candidate, _jaccard, subproblem_signature, union

    constraints = sum(item.type.value == "constraint" for item in extraction.requirements)
    domains = {item.domain for item in extraction.requirements}
    domains.update(item.domain for item in extraction.hypotheses)
    distance = decomposition_distance(draft_a, draft_b)
    sa = frozenset(subproblem_signature(x) for x in draft_a.subproblems)
    sb = frozenset(subproblem_signature(x) for x in draft_b.subproblems)

    def edge_signatures(d: Decomposition) -> frozenset:
        by_id = {x.identifier: x for x in d.subproblems}
        return frozenset((subproblem_signature(by_id[a]), subproblem_signature(by_id[b]))
                         for a, b in d.E)

    content_gap = 1.0 - _jaccard(sa, sb)
    structure_gap = 1.0 - _jaccard(edge_signatures(draft_a), edge_signatures(draft_b))
    coupling_a = len(draft_a.E) / max(1, len(draft_a.subproblems))
    coupling_b = len(draft_b.E) / max(1, len(draft_b.subproblems))
    features = PromptFeatures(
        constraint_count=constraints,
        domain_count=len(domains),
        hypothesis_count=len(extraction.hypotheses),
        ambiguity=bool(extraction.ambiguities),
        conflict=bool(extraction.conflicts),
        open_prompt=open_prompt,
        stakeholder_values=stakeholder_values,
        justified_plan=justified_plan,
        content_gap=content_gap,
        structure_gap=structure_gap,
        mean_coupling=(coupling_a + coupling_b) / 2,
        high_stakes=high_stakes,
        model_families=model_families,
    )
    initial_union = union((Candidate("draft-a", draft_a), Candidate("draft-b", draft_b))).decomposition
    return Diagnosis(features, initial_union, distance)


def _cost(item: PlanItem, *, n: int, k: int, T: int) -> int:
    if item is PlanItem.C8_BRAINSTORM_THEN_REVIEW:
        return get_strategy(StrategyId.S2).calls(n=n, k=k, T=T) + get_strategy(StrategyId.S8).calls(n=n, k=k, T=T)
    if item is PlanItem.COMBO_JIGSAW_THEN_CRITIC:
        return get_strategy(StrategyId.S12).calls(n=n, k=k, T=T) + get_strategy(StrategyId.S5).calls(n=n, k=k, T=T)
    if item is PlanItem.COMBO_FULL_PIPELINE:
        return sum(get_strategy(s).calls(n=n, k=k, T=T) for s in
                   (StrategyId.S3, StrategyId.S6, StrategyId.S4, StrategyId.S7))
    return get_strategy(StrategyId(item.value)).calls(n=n, k=k, T=T)


def _stage1(f: PromptFeatures) -> tuple[PlanItem | None, str | None]:
    if f.ambiguity and f.stakeholder_values:
        return PlanItem.S10, "1.1"
    if f.ambiguity:
        return PlanItem.S4, "1.2"
    return None, None


def _stage2(f: PromptFeatures, initial_distance: float, epsilon: float, theta_c: int) -> tuple[PlanItem | None, str | None]:
    if f.open_prompt:
        return PlanItem.C8_BRAINSTORM_THEN_REVIEW, "2.1"
    if f.content_gap <= epsilon < f.structure_gap and f.high_stakes:
        return PlanItem.S7, "2.2"
    if f.content_gap <= epsilon < f.structure_gap:
        return PlanItem.S6, "2.3"
    if epsilon < initial_distance <= 2 * epsilon and f.model_families >= 2:
        return PlanItem.S9, "2.4"
    if f.constraint_count >= theta_c or f.hypothesis_count > 0:
        return PlanItem.S12, "2.5"
    if f.domain_count >= 3 and f.mean_coupling <= 1:
        return PlanItem.S1, "2.6"
    if f.content_gap > 2 * epsilon and f.model_families >= 2:
        return PlanItem.S3, "2.7"
    return None, None


def _stage3(f: PromptFeatures) -> tuple[PlanItem | None, str | None]:
    if f.conflict:
        return PlanItem.S11, "3.1"
    if f.high_stakes:
        return PlanItem.S8, "3.2"
    if f.justified_plan and f.model_families >= 2:
        return PlanItem.S13, "3.3"
    return None, None


def _escalation(failures: Iterable[str], high_stakes: bool, already: set[PlanItem]) -> PlanItem | None:
    codes = set(failures)
    if codes & {"uncovered_requirements", "missing_hypothesis_verdict"}:
        target = PlanItem.COMBO_JIGSAW_THEN_CRITIC
    elif codes & {"dependency_cycle", "unowned_deliverable", "sink_without_deliverable"}:
        target = PlanItem.S8
    elif codes or high_stakes:
        target = PlanItem.COMBO_FULL_PIPELINE
    else:
        return None
    return None if target in already else target


def plan_strategy_chain(
    features: PromptFeatures,
    *,
    initial_distance: float,
    failures: Iterable[str],
    budget: int,
    extraction_calls: int,
    epsilon: float = DEFAULT_EPSILON,
    theta_c: int = DEFAULT_THETA_C,
    n: int = 3,
    k: int = 3,
    T: int = 2,
) -> StrategyPlan:
    """Apply Table 8, reserve one possible repair call, and report truncation.

    Budget includes extraction and two mandatory initial drafts. Strategy
    costs are the paper's Table 4 formulae; combinations sum their phases.
    """
    if budget < 0 or extraction_calls < 1:
        raise ValueError("budget must be >= 0 and extraction_calls must be >= 1")
    if not 0 <= epsilon <= 1 or theta_c < 1:
        raise ValueError("epsilon must be in [0,1] and theta_c >= 1")
    if not 0 <= initial_distance <= 1:
        raise ValueError("initial_distance must be in [0,1]")
    if n < 1 or k < 1 or T < 1:
        raise ValueError("n, k and T must be >= 1")

    spent = extraction_calls + 2
    if spent > budget:
        raise ValueError("Budget cannot cover extraction and the two mandatory initial drafts")

    rule0 = (initial_distance <= epsilon and features.hypothesis_count == 0
             and not features.any_flag and not features.high_stakes)
    selected: list[PlanItem] = []
    rules: list[str] = []
    if not rule0:
        for item, rule in (_stage1(features), _stage2(features, initial_distance, epsilon, theta_c), _stage3(features)):
            if item is not None and item not in selected:
                selected.append(item)
                rules.append(rule or "")
        if not selected:
            selected.append(PlanItem.S5)
            rules.append("3.4")

    queue = list(selected)
    reason = "Table 8 decision list"
    failure_set = tuple(failures)
    if not queue or (queue and (failure_set or features.high_stakes)):
        escalated = _escalation(failure_set, features.high_stakes, set(selected))
        if escalated is not None:
            queue.append(escalated)
            reason = "Algorithm 2 escalation"

    not_run: list[PlanItem] = []
    accepted: list[PlanItem] = []
    for index, item in enumerate(queue):
        required = _cost(item, n=n, k=k, T=T) + 1
        if spent + required > budget:
            not_run.extend(queue[index:])
            break
        accepted.append(item)
        spent += required
    return StrategyPlan(tuple(accepted), tuple(rules[:len(accepted)]),
                        tuple(not_run), spent, budget,
                        "checked union (rule 0)" if rule0 else reason)
