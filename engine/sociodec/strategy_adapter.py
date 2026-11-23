"""Bridge concrete strategy blueprints to the visibility-aware runtime.

The adapter owns protocol construction, seed placement, runtime dispatch and
decision-contract checks. Structured model-output decoding remains an explicit
injected boundary; untrusted free text is never silently treated as a
Decomposition.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable, Mapping, Protocol

from sociodec.catalogue import StrategyId
from sociodec.decisions import DecisionResult
from sociodec.extraction import AggregatedExtraction
from sociodec.models.decomposition import Decomposition
from sociodec.models.prompt import Prompt
from sociodec.orchestrator import StrategyOutcome
from sociodec.runtime import ProtocolInvoker, StrategyRun, run_strategy
from sociodec.selector import PlanItem
from sociodec.strategy_protocols import build_strategy_blueprint
from sociodec.strategy_decoding import DecisionAdjudication, ProtocolDecisionDecoder
from sociodec.validation import ValidationFinding, HypothesisVerdict


@dataclass(frozen=True, slots=True)
class DecodedStrategyResult:
    decision: DecisionResult
    hypothesis_verdicts: tuple[HypothesisVerdict, ...] = ()
    candidate_support_counts: tuple[tuple[tuple[str, str], int], ...] = ()
    findings: tuple[ValidationFinding, ...] = ()


class StrategyDecoder(Protocol):
    def __call__(
        self, strategy_id: StrategyId, run: StrategyRun,
    ) -> DecodedStrategyResult: ...


class CompositeExecutor(Protocol):
    def __call__(
        self, item: PlanItem, prompt: Prompt, extraction: AggregatedExtraction,
        initial_drafts: tuple[Decomposition, Decomposition],
        chain_seed: Decomposition | None, available_calls: int,
    ) -> StrategyOutcome: ...


PromptViewFactory = Callable[
    [StrategyId, Prompt, AggregatedExtraction, tuple[str, ...]],
    Mapping[str, str],
]


_EXPECTED_DECISION = {
    StrategyId.S1: "authority",
    StrategyId.S12: "union",
    StrategyId.S2: "union",
    StrategyId.S3: "rank-sum",
    StrategyId.S4: "consensus-medoid",
    StrategyId.S9: "majority",
    StrategyId.S5: "authority",
    StrategyId.S6: "synthesis",
    StrategyId.S8: "authority",
    StrategyId.S13: "authority",
    StrategyId.S7: "authority",
    StrategyId.S11: "compromise",
    StrategyId.S10: "consensus",
}


class ConcreteStrategyAdapter:
    """Callable adapter compatible with Core 11's StrategyExecutor contract.

    The decoder parses protocol outputs into typed candidates and invokes the
    matching pure decision operator. It returns the DecisionResult plus
    hypothesis verdict and support evidence.
    """

    def __init__(
        self,
        invoker: ProtocolInvoker,
        decoder: StrategyDecoder | None = None,
        *,
        prompt_view_factory: PromptViewFactory | None = None,
        model_ids: Mapping[str, str] | None = None,
        agent_contexts: Mapping[str, str] | None = None,
        n: int = 3,
        k: int = 3,
        T: int = 2,
        seed_selector: Callable[
            [tuple[Decomposition, Decomposition]], Decomposition
        ] | None = None,
        composite_executor: CompositeExecutor | None = None,
        decision_adjudications: Mapping[StrategyId | str, DecisionAdjudication] | None = None,
    ) -> None:
        if n < 1 or k < 1 or T < 1:
            raise ValueError("n, k and T must be >= 1")
        self.invoker = invoker
        self.decoder = decoder
        self.decision_adjudications = dict(decision_adjudications or {})
        self.prompt_view_factory = prompt_view_factory
        self.model_ids = dict(model_ids or {})
        self.agent_contexts = dict(agent_contexts or {})
        self.n, self.k, self.T = n, k, T
        self.seed_selector = seed_selector
        self.composite_executor = composite_executor

    def _strategy_id(self, item: PlanItem) -> StrategyId:
        try:
            return StrategyId(item.value)
        except ValueError:
            raise ValueError(
                f"{item.value} is a composition, not one atomic strategy; "
                "provide a composite_executor"
            ) from None

    def __call__(
        self,
        item: PlanItem,
        prompt: Prompt,
        extraction: AggregatedExtraction,
        initial_drafts: tuple[Decomposition, Decomposition],
        chain_seed: Decomposition | None,
        available_calls: int,
    ) -> StrategyOutcome:
        if item in {
            PlanItem.C8_BRAINSTORM_THEN_REVIEW,
            PlanItem.COMBO_JIGSAW_THEN_CRITIC,
            PlanItem.COMBO_FULL_PIPELINE,
        }:
            if self.composite_executor is None:
                raise ValueError(f"{item.value} requires an explicit composition executor")
            result = self.composite_executor(
                item, prompt, extraction, initial_drafts, chain_seed, available_calls,
            )
            if result.calls_made > available_calls:
                raise RuntimeError("Composite executor exceeded available call budget")
            return result

        sid = self._strategy_id(item)
        partitioned = sid in {StrategyId.S1, StrategyId.S12}
        if partitioned and self.prompt_view_factory is None:
            raise ValueError(
                f"{sid.value} requires an explicit prompt_view_factory; "
                "full-prompt fallback is forbidden for partitioned strategies"
            )
        # Build only the role/agent manifest here. These sentinels are never
        # passed to the runtime; the final blueprint uses caller-derived views.
        preliminary_views = None
        if sid is StrategyId.S1:
            preliminary_views = {"coordinator": "FULL_PROMPT", **{
                f"specialist-{i}": f"PARTITION_REQUIRED:{i}" for i in range(1, self.n + 1)
            }}
        elif sid is StrategyId.S12:
            preliminary_views = {**{
                f"expert-{i}": f"FACET_REQUIRED:{i}" for i in range(1, self.n + 1)
            }, "integrator": "FULL_PROMPT"}
        preliminary = build_strategy_blueprint(
            sid, model_ids=self.model_ids, prompt_views=preliminary_views,
            agent_contexts=self.agent_contexts, n=self.n, k=self.k, T=self.T,
        )
        agent_ids = tuple(agent.identifier for agent in preliminary.strategy.agents)
        views = (
            self.prompt_view_factory(sid, prompt, extraction, agent_ids)
            if self.prompt_view_factory is not None else
            {agent_id: prompt.text for agent_id in agent_ids}
        )
        if partitioned:
            if set(views) != set(agent_ids):
                raise ValueError(f"{sid.value} prompt_view_factory must return exactly the declared agent views")
            restricted_ids = (
                tuple(f"specialist-{i}" for i in range(1, self.n + 1))
                if sid is StrategyId.S1 else
                tuple(f"expert-{i}" for i in range(1, self.n + 1))
            )
            if any(views.get(agent_id) == prompt.text for agent_id in restricted_ids):
                raise ValueError(
                    f"{sid.value} specialist/expert views must not equal the full prompt"
                )
        blueprint = build_strategy_blueprint(
            sid, model_ids=self.model_ids, prompt_views=views,
            agent_contexts=self.agent_contexts,
            n=self.n, k=self.k, T=self.T,
        )

        draft_agents = [
            step.agent_id for step in blueprint.strategy.protocol
            if step.action.value == "draft" and step.round == 1
        ]
        seeds: dict[str, str] = {}
        if not partitioned and draft_agents:
            if chain_seed is not None:
                seeds[draft_agents[0]] = _decomposition_seed_text(chain_seed)
            elif sid in {StrategyId.S5, StrategyId.S8}:
                if self.seed_selector is not None:
                    chosen = self.seed_selector(initial_drafts)
                    seeds[draft_agents[0]] = _decomposition_seed_text(chosen)
            elif sid in {StrategyId.S6, StrategyId.S13}:
                seeds[draft_agents[0]] = _decomposition_seed_text(initial_drafts[0])
            else:
                for agent_id, decomposition in zip(draft_agents, initial_drafts):
                    seeds[agent_id] = _decomposition_seed_text(decomposition)

        initial_inputs = {"all_previous_outputs": ""} if sid is StrategyId.S10 else {}
        run = run_strategy(
            sid.value, prompt, blueprint.strategy, self.invoker,
            prompt_views=blueprint.prompt_views,
            hypotheses=extraction.hypotheses,
            seeds=seeds,
            initial_inputs=initial_inputs,
        )
        if run.calls_made > available_calls:
            raise RuntimeError(
                f"{sid.value} used {run.calls_made} calls; allowance is {available_calls}"
            )
        decoder = self.decoder or ProtocolDecisionDecoder(
            prompt, extraction, adjudications=self.decision_adjudications,
        )
        decoded = decoder(sid, run)
        if not isinstance(decoded, DecodedStrategyResult):
            raise TypeError("decoder must return DecodedStrategyResult")
        expected = _EXPECTED_DECISION[sid]
        if decoded.decision.rule != expected:
            raise ValueError(
                f"{sid.value} requires decision operator {expected!r}, "
                f"got {decoded.decision.rule!r}"
            )
        return StrategyOutcome(
            decomposition=decoded.decision.decomposition,
            calls_made=run.calls_made,
            hypothesis_verdicts=decoded.hypothesis_verdicts,
            candidate_support_counts=decoded.candidate_support_counts,
            findings=decoded.findings,
            strategy_run_id=f"{sid.value}:{len(run.outputs)}-steps",
        )


def _decomposition_seed_text(decomposition: Decomposition) -> str:
    """Serialize a seed using the same strict candidate JSON contract as model outputs."""
    payload = {
        "candidate_id": "adopted-seed",
        "subproblems": [
            {
                "id": item.identifier,
                "question": item.question,
                "inputs": list(item.inputs),
                "output": item.output,
                "local_constraints": [
                    {"kind": constraint.kind.value, "statement": constraint.statement}
                    for constraint in item.local_constraints
                ],
                "covered_requirements": [
                    {
                        "type": requirement.type.value,
                        "domain": requirement.domain,
                        "statement": requirement.statement,
                    }
                    for requirement in item.covered_requirements
                ],
            }
            for item in decomposition.subproblems
        ],
        "dependencies": [
            {"source": source, "target": target}
            for source, target in sorted(decomposition.E)
        ],
        "kappa": {
            deliverable: sorted(contributors)
            for deliverable, contributors in decomposition.kappa.items()
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
