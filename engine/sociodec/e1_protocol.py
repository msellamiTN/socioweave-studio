"""Pre-registered E1 overall-comparison design from Sections 8.1 and Tables 12–14.

Validates experiment manifests only; it does not run models or claim results.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Mapping
from sociodec.catalogue import STRATEGIES, get_strategy
from sociodec.dataset_metrics import get_metric_profile

PUBLIC_DATASETS = ("BREAK", "StrategyQA", "TaskBench", "TravelPlanner")
ALL_DATASETS = PUBLIC_DATASETS + ("smart-administration",)
BASELINES = ("single_plan_and_solve", "single_self_refinement", "single_self_consistency", "decomposer_plus_evaluator", "multi_agent_debate", "nominal_multi_agent")
MODEL_MODES = ("heterogeneous", "homogeneous")
EXPECTED_PROMPTS = {"BREAK":100,"StrategyQA":100,"TaskBench":100,"TravelPlanner":100,"smart-administration":60}
EXPECTED_SEEDS = 5

@dataclass(frozen=True, slots=True)
class E1Condition:
    dataset: str
    method_id: str
    model_mode: str
    seed: int
    prompt_ids: tuple[str, ...]
    call_budget: int
    matched_strategy_id: str | None = None
    def __post_init__(self):
        if self.dataset not in ALL_DATASETS: raise ValueError(f"Unknown E1 dataset: {self.dataset}")
        allowed = {x.identifier.value for x in STRATEGIES} | set(BASELINES)
        if self.method_id not in allowed: raise ValueError(f"Unknown E1 method: {self.method_id}")
        if self.model_mode not in MODEL_MODES: raise ValueError(f"model_mode must be one of {MODEL_MODES}")
        if isinstance(self.seed,bool) or not isinstance(self.seed,int) or self.seed < 0: raise ValueError("seed must be a non-negative integer")
        if not self.prompt_ids or len(self.prompt_ids) != len(set(self.prompt_ids)): raise ValueError("prompt_ids must be non-empty and unique")
        if isinstance(self.call_budget,bool) or not isinstance(self.call_budget,int) or self.call_budget < 1: raise ValueError("call_budget must be a positive integer")
        baseline = self.method_id in BASELINES
        if baseline != (self.matched_strategy_id is not None): raise ValueError("Only baseline rows must name matched_strategy_id")
        if self.matched_strategy_id is not None and self.matched_strategy_id not in {x.identifier.value for x in STRATEGIES}: raise ValueError("matched_strategy_id must identify a paper strategy")

def validate_e1_manifest(conditions: Iterable[E1Condition], *, expected_prompt_ids: Mapping[str, tuple[str,...]], require_complete_grid: bool = True) -> tuple[str,...]:
    rows = tuple(conditions)
    if set(expected_prompt_ids) != set(ALL_DATASETS): raise ValueError("expected_prompt_ids must declare all five paper datasets")
    for dataset, ids in expected_prompt_ids.items():
        if len(ids) != EXPECTED_PROMPTS[dataset] or len(set(ids)) != len(ids): raise ValueError(f"{dataset} requires {EXPECTED_PROMPTS[dataset]} unique frozen prompt IDs")
    expected_ids = {d:set(ids) for d,ids in expected_prompt_ids.items()}
    keys=set(); strategies={}; baselines={}
    for row in rows:
        if row.seed not in range(EXPECTED_SEEDS): raise ValueError("E1 requires five seed indices: 0 through 4")
        if set(row.prompt_ids) != expected_ids[row.dataset]: raise ValueError(f"{row.dataset} condition does not use the frozen E1 prompt set")
        key=(row.dataset,row.method_id,row.model_mode,row.seed,row.matched_strategy_id)
        if key in keys: raise ValueError(f"duplicate E1 condition: {key}")
        keys.add(key)
        if row.method_id in BASELINES: baselines[(row.dataset,row.matched_strategy_id,row.model_mode,row.seed,row.method_id)] = row
        else: strategies[(row.dataset,row.method_id,row.model_mode,row.seed)] = row
    errors=[]; strategy_ids=tuple(x.identifier.value for x in STRATEGIES)
    for dataset in ALL_DATASETS:
        for mode in MODEL_MODES:
            for seed in range(EXPECTED_SEEDS):
                for sid in strategy_ids:
                    strategy=strategies.get((dataset,sid,mode,seed))
                    if strategy is None:
                        errors.append(f"missing strategy condition {(dataset,sid,mode,seed)}")
                    for bid in BASELINES:
                        baseline=baselines.get((dataset,sid,mode,seed,bid))
                        if baseline is None: errors.append(f"missing budget-matched baseline {(dataset,sid,mode,seed,bid)}")
                        elif strategy is not None and baseline.call_budget != strategy.call_budget: errors.append(f"baseline {bid} budget {baseline.call_budget} does not match {sid} budget {strategy.call_budget}")
    if errors and require_complete_grid: raise ValueError("Incomplete or invalid E1 grid: " + "; ".join(errors[:12]))
    return tuple(errors)


def build_e1_conditions(
    *,
    expected_prompt_ids: Mapping[str, tuple[str, ...]],
    n: int = 3,
    k: int = 3,
    T: int = 2,
) -> tuple[E1Condition, ...]:
    """Build the complete paper E1 grid from caller-supplied frozen prompt IDs.

    This creates condition metadata only. It does not fabricate benchmark
    examples, download datasets, choose providers, or execute model calls.
    Every baseline inherits the exact method-call budget of its matched
    strategy for the same dataset, model mode, seed, and prompt set.
    """
    if min(n, k, T) < 1:
        raise ValueError("n, k and T must be >= 1")
    if set(expected_prompt_ids) != set(ALL_DATASETS):
        raise ValueError("expected_prompt_ids must declare all five paper datasets")

    conditions: list[E1Condition] = []
    for dataset in ALL_DATASETS:
        prompt_ids = tuple(expected_prompt_ids[dataset])
        for model_mode in MODEL_MODES:
            for seed in range(EXPECTED_SEEDS):
                for strategy in STRATEGIES:
                    strategy_id = strategy.identifier.value
                    budget = strategy.calls(n=n, k=k, T=T)
                    conditions.append(E1Condition(
                        dataset, strategy_id, model_mode, seed, prompt_ids, budget,
                    ))
                    for baseline_id in BASELINES:
                        conditions.append(E1Condition(
                            dataset, baseline_id, model_mode, seed, prompt_ids,
                            budget, matched_strategy_id=strategy_id,
                        ))

    validate_e1_manifest(
        conditions,
        expected_prompt_ids=expected_prompt_ids,
        require_complete_grid=True,
    )
    return tuple(conditions)

def e1_metric_obligations(dataset: str) -> frozenset[str]:
    profile=get_metric_profile(dataset)
    return profile.applicable_metrics | profile.additional_metrics
