"""Direct non-adaptive E1 execution of one paper strategy."""
from __future__ import annotations
import json
from dataclasses import replace
from typing import Callable, Mapping
from sociodec.catalogue import StrategyId
from sociodec.decisions import decomposition_distance
from sociodec.direct_e1 import DirectMethodAdapter, MethodRun
from sociodec.e1_protocol import E1Condition, BASELINES
from sociodec.extraction import AggregatedExtraction
from sociodec.models.prompt import Prompt
from sociodec.models.strategy import Agent, ProtocolStep, Role, SocialStrategy
from sociodec.runtime import ProtocolContext, ProtocolInvoker, run_strategy
from sociodec.protocol_decoding import parse_candidate
from sociodec.strategy_decoding import DecisionAdjudication, ProtocolDecisionDecoder
from sociodec.jigsaw import JigsawPromptViewBundle, PaperJigsawPromptViewFactory
from sociodec.strategy_protocols import build_strategy_blueprint

ModelResolver = Callable[[E1Condition, tuple[str, ...]], Mapping[str, str]]
ModelFamilyResolver = Callable[[E1Condition, tuple[str, ...]], Mapping[str, str]]
PromptViewFactory = Callable[[StrategyId, Prompt, AggregatedExtraction, tuple[str, ...]], Mapping[str, str] | JigsawPromptViewBundle]
InvokerFactory = Callable[[Agent, int], ProtocolInvoker]


def _drop_empty_jigsaw_facets(strategy: SocialStrategy, dropped_facets: tuple[str, ...]) -> SocialStrategy:
    """Remove empty S12 experts from the prompt-specific protocol and visibility graph."""
    dropped = set(dropped_facets)
    if not dropped:
        return strategy
    if "integrator" in dropped or not dropped.issubset(
        {f"expert-{index}" for index in range(1, 4)}
    ):
        raise ValueError("S12 may drop only empty expert facets; integrator must remain")
    active = {agent.identifier for agent in strategy.agents} - dropped
    if not any(agent_id.startswith("expert-") for agent_id in active):
        raise ValueError("S12 cannot run when every extracted facet is empty")
    return replace(
        strategy,
        agents=tuple(agent for agent in strategy.agents if agent.identifier in active),
        assignments=tuple(item for item in strategy.assignments if item.agent_id in active),
        visibility=tuple(
            replace(
                item,
                visible_pairs=tuple(
                    (observer, author) for observer, author in item.visible_pairs
                    if observer in active and author in active
                ),
            )
            for item in strategy.visibility
        ),
        protocol=tuple(step for step in strategy.protocol if step.agent_id in active),
    )


class _RoutedInvoker:
    def __init__(self, routes: Mapping[str, ProtocolInvoker]):
        self.routes = dict(routes)
        self.traces: list[Mapping[str, object]] = []
    def invoke(self, agent: Agent, step: ProtocolStep, context: ProtocolContext) -> str:
        provider = self.routes[agent.identifier]
        trace_fn = getattr(provider, "trace_dicts", None)
        if not callable(trace_fn):
            raise RuntimeError(f"Provider for {agent.identifier} must expose trace_dicts()")
        before = len(trace_fn())
        result = provider.invoke(agent, step, context)
        after = trace_fn()
        if len(after) != before + 1:
            raise RuntimeError(f"Provider trace must record exactly one call for {agent.identifier}")
        self.traces.append(dict(after[-1]))
        return result
    def trace_dicts(self):
        return tuple(dict(x) for x in self.traces)

class DirectProtocolStrategyAdapter(DirectMethodAdapter):
    """One strategy -> typed decision decoder; no adaptive drafts or selector."""
    def __init__(self, *, extraction: AggregatedExtraction, model_resolver: ModelResolver,
                 invoker_factory: InvokerFactory, prompt_view_factory: PromptViewFactory | None = None,
                 model_family_resolver: ModelFamilyResolver | None = None,
                 agent_contexts: Mapping[str, str] | None = None,
                 adjudications: Mapping[StrategyId | str, DecisionAdjudication] | None = None,
                 n: int = 3, k: int = 3, T: int = 2,
                 delphi_epsilon: float = 0.1,
                 mediation_epsilon: float = 0.1,
                 consensus_epsilon: float = 0.1):
        if min(n, k, T) < 1: raise ValueError("n, k and T must be >= 1")
        self.extraction, self.model_resolver, self.invoker_factory = extraction, model_resolver, invoker_factory
        self.model_family_resolver = model_family_resolver
        if prompt_view_factory is None and n == 3:
            prompt_view_factory = PaperJigsawPromptViewFactory()
        self.prompt_view_factory, self.agent_contexts = prompt_view_factory, dict(agent_contexts or {})
        if not 0.0 <= delphi_epsilon <= 1.0:
            raise ValueError("delphi_epsilon must be in [0, 1]")
        if not 0.0 <= mediation_epsilon <= 1.0:
            raise ValueError("mediation_epsilon must be in [0, 1]")
        if not 0.0 <= consensus_epsilon <= 1.0:
            raise ValueError("consensus_epsilon must be in [0, 1]")
        self.adjudications, self.n, self.k, self.T = dict(adjudications or {}), n, k, T
        self.delphi_epsilon = delphi_epsilon
        self.mediation_epsilon = mediation_epsilon
        self.consensus_epsilon = consensus_epsilon

    def run(self, *, condition: E1Condition, prompt: Prompt, seed: int) -> MethodRun:
        if condition.method_id in BASELINES: raise ValueError("Strategy adapter cannot execute a baseline")
        sid = StrategyId(condition.method_id)
        # Establish roster without introducing any model call or draft.
        ids = (("coordinator", *(f"specialist-{i+1}" for i in range(self.n))) if sid is StrategyId.S1 else
               (*(f"expert-{i+1}" for i in range(self.n)), "integrator") if sid is StrategyId.S12 else None)
        initial_views = ({agent: "ROSTER_ONLY" for agent in ids} if ids else None)
        roster = build_strategy_blueprint(sid, n=self.n, k=self.k, T=self.T, prompt_views=initial_views)
        agent_ids = tuple(a.identifier for a in roster.strategy.agents)
        models = dict(self.model_resolver(condition, agent_ids))
        if set(models) != set(agent_ids) or any(not isinstance(v, str) or not v.strip() for v in models.values()):
            raise ValueError("model_resolver must return a non-empty model ID for every agent")
        distinct = set(models.values())
        if condition.model_mode == "homogeneous" and len(distinct) != 1:
            raise ValueError("homogeneous condition requires exactly one model identity")
        if condition.model_mode == "heterogeneous" and len(distinct) < 2:
            raise ValueError("heterogeneous condition requires at least two distinct model identities")
        model_families: dict[str, str] = {}
        if self.model_family_resolver is not None:
            model_families = dict(self.model_family_resolver(condition, agent_ids))
            if set(model_families) != set(agent_ids) or any(
                not isinstance(value, str) or not value.strip()
                for value in model_families.values()
            ):
                raise ValueError("model_family_resolver must return one non-empty family ID per agent")
            distinct_families = set(model_families.values())
            if condition.model_mode == "homogeneous" and len(distinct_families) != 1:
                raise ValueError("homogeneous condition requires exactly one model family")
            if condition.model_mode == "heterogeneous" and len(distinct_families) < min(2, len(agent_ids)):
                raise ValueError(
                    f"heterogeneous condition requires at least {min(2, len(agent_ids))} distinct model families"
                )
            for assignment in roster.strategy.assignments:
                if condition.model_mode != "heterogeneous" or assignment.role is not Role.JUDGE:
                    continue
                authors = {
                    item.agent_id for item in roster.strategy.assignments
                    if item.round == assignment.round and item.role is Role.DECOMPOSER
                }
                if model_families[assignment.agent_id] in {
                    model_families[author] for author in authors
                }:
                    raise ValueError(
                        f"judge {assignment.agent_id} must use a model family distinct from the authors it judges"
                    )
        views = None
        jigsaw_bundle: JigsawPromptViewBundle | None = None
        dropped_facets: tuple[str, ...] = ()
        if sid is StrategyId.S12 and self.prompt_view_factory:
            factory_result = self.prompt_view_factory(sid, prompt, self.extraction, agent_ids)
            if isinstance(factory_result, JigsawPromptViewBundle):
                jigsaw_bundle = factory_result
                views = dict(factory_result.views)
                dropped_facets = factory_result.dropped_facets
            else:
                views = dict(factory_result)
            if set(views) != set(agent_ids) or any(not isinstance(v, str) or not v.strip() for v in views.values()):
                raise ValueError("prompt_view_factory must return one non-empty view per agent")
        elif sid is StrategyId.S12:
            raise ValueError("S12 requires a registered facet prompt-view factory")
        blueprint = build_strategy_blueprint(sid, model_ids=models, prompt_views=views,
            agent_contexts=self.agent_contexts, n=self.n, k=self.k, T=self.T)
        strategy = blueprint.strategy
        if dropped_facets:
            if sid is not StrategyId.S12:
                raise ValueError("Only S12 may drop empty facets")
            strategy = _drop_empty_jigsaw_facets(strategy, dropped_facets)
        active_agent_ids = tuple(
            agent_id for agent_id in agent_ids if agent_id not in set(dropped_facets)
        )
        if sid is StrategyId.S12 and condition.model_mode == "heterogeneous":
            if len({models[agent_id] for agent_id in active_agent_ids}) < 2:
                raise ValueError(
                    "heterogeneous S12 must retain at least two distinct model identities among active facets and integrator"
                )
            if model_families and len({
                model_families[agent_id] for agent_id in active_agent_ids
            }) < 2:
                raise ValueError(
                    "heterogeneous S12 must retain at least two distinct model families among active facets and integrator"
                )
        active_views = {
            agent_id: value for agent_id, value in (blueprint.prompt_views or {}).items()
            if agent_id not in set(dropped_facets)
        }
        routes = {a.identifier: self.invoker_factory(a, seed) for a in strategy.agents}
        invoker = _RoutedInvoker(routes)
        run_options = {}
        if sid in {StrategyId.S4, StrategyId.S10, StrategyId.S11}:
            def candidate_distance(left_json: str, right_json: str) -> float:
                # runtime passes canonical candidate JSON (without the outer
                # protocol envelope); reconstruct typed decompositions and
                # apply Definition 7's matcher-based distance.
                left_data, right_data = json.loads(left_json), json.loads(right_json)
                left_d = parse_candidate(
                    left_data, prompt=prompt, extraction=self.extraction,
                    candidate_id="left-candidate",
                ).decomposition
                right_d = parse_candidate(
                    right_data, prompt=prompt, extraction=self.extraction,
                    candidate_id="right-candidate",
                ).decomposition
                return decomposition_distance(left_d, right_d)

            if sid is StrategyId.S4:
                run_options = {
                    "delphi_epsilon": self.delphi_epsilon,
                    "delphi_candidate_distance": candidate_distance,
                }
            elif sid is StrategyId.S10:
                run_options = {
                    "consensus_epsilon": self.consensus_epsilon,
                    "consensus_candidate_distance": candidate_distance,
                }
            else:
                run_options = {
                    "mediation_epsilon": self.mediation_epsilon,
                    "mediation_candidate_distance": candidate_distance,
                }
        run = run_strategy(sid.value, prompt, strategy, invoker,
            prompt_views=active_views, hypotheses=self.extraction.hypotheses,
            **run_options)
        if run.seeded_agents: raise RuntimeError("Direct E1 must not contain seeded agents")
        traces = invoker.trace_dicts()
        if run.calls_made != len(traces):
            raise RuntimeError(f"Runtime counted {run.calls_made} calls but {len(traces)} traces were recorded")
        decoded = ProtocolDecisionDecoder(prompt, self.extraction, adjudications=self.adjudications)(sid, run)
        return MethodRun(decoded.decision.decomposition, run.calls_made, traces,
            decoded.hypothesis_verdicts, {
                "execution_path": "direct_protocol", "strategy_id": sid.value,
                "strategy_calls_declared": blueprint.strategy.calls,
                "strategy_calls_scheduled_after_empty_facet_drop": strategy.calls,
                "strategy_calls_executed": run.calls_made,
                "jigsaw_policy_id": jigsaw_bundle.policy_id if jigsaw_bundle else None,
                "jigsaw_policy_sha256": jigsaw_bundle.policy_sha256 if jigsaw_bundle else None,
                "jigsaw_active_facets": list(jigsaw_bundle.active_facets) if jigsaw_bundle else [],
                "jigsaw_dropped_facets": list(jigsaw_bundle.dropped_facets) if jigsaw_bundle else [],
                "jigsaw_facet_manifest": [dict(item) for item in jigsaw_bundle.facet_manifest] if jigsaw_bundle else [],
                "strategy_depth_declared": blueprint.strategy.depth,
                "strategy_depth_executed": run.depth_executed,
                "strategy_base_calls": 5 if sid is StrategyId.S11 else blueprint.strategy.calls,
                "strategy_base_depth": 3 if sid is StrategyId.S11 else blueprint.strategy.depth,
                "strategy_max_calls": 2 + 3 * self.T if sid is StrategyId.S11 else blueprint.strategy.calls,
                "strategy_max_depth": 1 + 2 * self.T if sid is StrategyId.S11 else blueprint.strategy.depth,
                "delphi_epsilon": self.delphi_epsilon if sid is StrategyId.S4 else None,
                "delphi_distance_matcher": "exact-output-local-constraints-v1" if sid is StrategyId.S4 else None,
                "mediation_epsilon": self.mediation_epsilon if sid is StrategyId.S11 else None,
                "mediation_distance_matcher": "exact-output-local-constraints-v1" if sid is StrategyId.S11 else None,
                "consensus_epsilon": self.consensus_epsilon if sid is StrategyId.S10 else None,
                "consensus_distance_matcher": "exact-output-local-constraints-v1" if sid is StrategyId.S10 else None,
                "mediation_converged": run.mediation_converged if sid is StrategyId.S11 else None,
                "mediation_stop_round": run.mediation_stop_round if sid is StrategyId.S11 else None,
                "mediation_distance": run.mediation_distance if sid is StrategyId.S11 else None,
                "configured_agent_model_ids": models,
                "configured_agent_model_families": model_families or None,
                "agent_model_ids": {agent_id: models[agent_id] for agent_id in active_agent_ids},
                "agent_model_families": ({agent_id: model_families[agent_id] for agent_id in active_agent_ids} if model_families else None),
                "seeded_agents": list(run.seeded_agents),
                "output_count": len(run.outputs), "decision_rule": decoded.decision.rule,
                "decision_selected_candidate": decoded.decision.selected_candidate_id,
                "decision_rationale": decoded.decision.rationale, "trace_complete": len(traces) == run.calls_made,
            })
