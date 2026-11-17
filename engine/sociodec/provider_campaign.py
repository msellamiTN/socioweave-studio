"""End-to-end provider-backed adaptive campaign integration.

This is the callable adapter consumed by Core 16/19 resumable campaign
runners. Prompt interpretation, extraction, initial drafting, social strategy
execution and fixed execution are explicit dependencies; no semantics are
invented from raw benchmark text.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from typing import Callable, Mapping, Protocol

from sociodec.campaign import FixedExecutor, UtilityScorer, evaluate_adaptive_trial
from sociodec.experiments import (
    BenchmarkPrompt, ExperimentConfig, TrialContext, TrialOutcome,
)
from sociodec.extraction import (
    AggregatedExtraction, RequirementExtractor, run_extractors,
)
from sociodec.models.decomposition import Decomposition
from sociodec.models.prompt import Prompt
from sociodec.orchestrator import (
    AdaptiveResult, ExtractionRunner, InitialDrafter, StrategyExecutor,
    run_adaptive,
)
from sociodec.protocol_decoding import parse_candidate
from sociodec.providers.base import ChatMessage, GenerationConfig, LLMProvider
from sociodec.resumable import run_resumable_campaign


class PromptFactory(Protocol):
    """Build the declared interpretation ι for a benchmark prompt."""
    def __call__(self, example: BenchmarkPrompt) -> Prompt: ...


@dataclass(frozen=True, slots=True)
class InitialDraftTrace:
    author_index: int
    provider: str
    model: str
    request_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float
    prompt_sha256: str
    output_sha256: str


class ProviderInitialDrafter:
    """Two independent, single-call initial drafts with no shared history."""

    def __init__(
        self,
        providers: tuple[LLMProvider, LLMProvider],
        *,
        temperature: float = 0.7,
        max_new_tokens: int = 1024,
    ) -> None:
        self.providers = providers
        self.temperature = temperature
        self.max_new_tokens = max_new_tokens
        self.traces: list[InitialDraftTrace] = []

    def __call__(
        self, prompt: Prompt, extraction: AggregatedExtraction, author_index: int,
    ) -> Decomposition:
        if author_index not in (0, 1):
            raise ValueError("Initial author_index must be 0 or 1")
        provider = self.providers[author_index]
        system = (
            "You are an independent prompt decomposer. Produce a complete "
            "typed decomposition candidate. Do not assume access to another "
            "agent's work. Return one JSON object and no markdown."
        )
        payload = {
            "prompt_text": prompt.text,
            "declared_goal": prompt.iota.goal,
            "constraints": [
                {"kind": c.kind.value, "statement": c.statement}
                for c in prompt.iota.constraints
            ],
            "inputs": list(prompt.iota.inputs),
            "deliverables": list(prompt.iota.deliverables),
            "explicit_requirements": [
                {"type": r.type.value, "domain": r.domain,
                 "statement": r.statement}
                for r in extraction.requirements
            ],
            "implicit_hypotheses": [
                {"type": h.type.value, "domain": h.domain,
                 "statement": h.statement}
                for h in extraction.hypotheses
            ],
            "output_contract": {
                "candidate_id": "string",
                "subproblems": [{
                    "id": "string", "question": "string", "inputs": [],
                    "output": "string", "local_constraints": [],
                    "covered_requirements": [{
                        "type": "target|constraint|deliverable",
                        "domain": "string", "statement": "exact extracted statement"
                    }]
                }],
                "dependencies": [{"source": "subproblem-id", "target": "subproblem-id"}],
                "kappa": {"exact declared deliverable": ["contributor-subproblem-id"]},
                "hypothesis_verdicts": [{
                    "type": "target|constraint|deliverable", "domain": "string",
                    "statement": "exact hypothesis statement",
                    "verdict": "confirmed|rejected"
                }]
            },
        }
        user_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        started = time.perf_counter()
        response = provider.generate(
            [ChatMessage("system", system), ChatMessage("user", user_text)],
            GenerationConfig(
                temperature=self.temperature,
                max_new_tokens=self.max_new_tokens,
            ),
        )
        elapsed = (time.perf_counter() - started) * 1000
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Initial draft returned invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("Initial draft JSON root must be an object")
        candidate = parse_candidate(
            data.get("candidate", data), prompt=prompt,
            extraction=extraction, candidate_id=f"initial-{author_index}",
        )
        self.traces.append(InitialDraftTrace(
            author_index, response.provider, response.model,
            response.request_id, response.input_tokens, response.output_tokens,
            round(elapsed, 3),
            hashlib.sha256(user_text.encode()).hexdigest(),
            hashlib.sha256(response.text.encode()).hexdigest(),
        ))
        return candidate.decomposition


@dataclass(frozen=True, slots=True)
class CampaignPolicy:
    call_budget: int
    high_stakes: bool = False
    open_prompt: bool = False
    stakeholder_values: bool = False
    justified_plan: bool = False
    epsilon: float = 0.1
    theta_c: int = 5
    repair_callback: object | None = None

    def __post_init__(self) -> None:
        if isinstance(self.call_budget, bool) or self.call_budget < 1:
            raise ValueError("call_budget must be >= 1")


class ProviderBackedTrialAdapter:
    """Callable TrialContext -> TrialOutcome for resumable campaigns.

    It runs Core 11 adaptive orchestration, then Core 20 fixed-executor
    evaluation. The prompt factory is mandatory because BenchmarkPrompt
    contains raw text, not the declared interpretation tuple.
    """

    def __init__(
        self,
        *,
        prompt_factory: PromptFactory,
        extract: ExtractionRunner,
        draft: InitialDrafter,
        execute_strategy: StrategyExecutor,
        executor: FixedExecutor,
        expected_executor_id: str,
        policy: CampaignPolicy,
        utility_scorer: UtilityScorer | None = None,
        trace_supplier: Callable[[], tuple[Mapping[str, object], ...]] | None = None,
    ) -> None:
        if not expected_executor_id.strip():
            raise ValueError("expected_executor_id must be non-empty")
        self.prompt_factory = prompt_factory
        self.extract = extract
        self.draft = draft
        self.execute_strategy = execute_strategy
        self.executor = executor
        self.expected_executor_id = expected_executor_id
        self.policy = policy
        self.utility_scorer = utility_scorer
        self.trace_supplier = trace_supplier

    def __call__(self, context: TrialContext) -> TrialOutcome:
        prompt = self.prompt_factory(context.example)
        if not isinstance(prompt, Prompt):
            raise TypeError("prompt_factory must return Prompt")
        if prompt.text != context.example.prompt_text:
            raise ValueError("prompt_factory must preserve the exact benchmark prompt text")
        config = context.config
        adaptive: AdaptiveResult = run_adaptive(
            prompt,
            extract=self.extract,
            draft=self.draft,
            execute_strategy=self.execute_strategy,
            budget=self.policy.call_budget,
            high_stakes=self.policy.high_stakes,
            model_families=len(config.model_families),
            open_prompt=self.policy.open_prompt,
            stakeholder_values=self.policy.stakeholder_values,
            justified_plan=self.policy.justified_plan,
            epsilon=self.policy.epsilon,
            theta_c=self.policy.theta_c,
            n=config.n_agents,
            k=config.k_experts,
            T=config.max_rounds,
            repair_callback=self.policy.repair_callback,
        )
        traces = tuple(dict(x) for x in (
            self.trace_supplier() if self.trace_supplier is not None else ()
        ))
        outcome, final = evaluate_adaptive_trial(
            adaptive, self.executor, seed=context.seed,
            expected_executor_id=self.expected_executor_id,
            utility_scorer=self.utility_scorer,
            provider_trace=traces,
        )
        metrics = dict(outcome.metrics)
        metrics["orchestration_calls"] = float(adaptive.calls_made)
        metrics["strategy_runs"] = float(len(adaptive.strategy_records))
        metrics["strategies_not_run"] = float(len(adaptive.strategies_not_run))
        metadata = dict(outcome.metadata)
        metadata.update({
            "experiment_id": config.experiment_id,
            "config_hash": config.config_hash,
            "dataset": context.example.dataset,
            "example_id": context.example.example_id,
            "prompt_hash": context.example.prompt_hash,
            "repeat_index": context.repeat_index,
            "trial_seed": context.seed,
            "termination_reason": adaptive.terminated_reason,
            "selected_strategy_run_id": adaptive.best_strategy_run_id,
            "strategies_executed": [record.item.value for record in adaptive.strategy_records],
            "strategies_not_run": [item.value for item in adaptive.strategies_not_run],
            "events": [asdict(event) for event in adaptive.events],
            "final_fully_valid": final.fully_valid,
            "trace_count": len(traces),
        })
        return TrialOutcome(metrics, traces, metadata)


def provider_extraction_runner(
    extractors: tuple[RequirementExtractor, ...],
) -> ExtractionRunner:
    """Create the paper's q-extractor union/dedup adapter."""
    if not extractors:
        raise ValueError("At least one requirement extractor is required")
    def extract(prompt: Prompt) -> AggregatedExtraction:
        return run_extractors(prompt.text, extractors)
    return extract


def run_provider_backed_campaign(
    config: ExperimentConfig,
    examples: tuple[BenchmarkPrompt, ...],
    adapter: ProviderBackedTrialAdapter,
    checkpoint_path: str,
):
    """Execute/resume a provider-backed campaign with per-trial fsync."""
    return run_resumable_campaign(config, examples, adapter, checkpoint_path)
