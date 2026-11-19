"""Direct non-adaptive E1 execution of one paper strategy."""
from __future__ import annotations
import json
from typing import Callable, Mapping
from sociodec.catalogue import StrategyId
from sociodec.decisions import decomposition_distance
from sociodec.direct_e1 import DirectMethodAdapter, MethodRun
from sociodec.e1_protocol import E1Condition, BASELINES
from sociodec.extraction import AggregatedExtraction
from sociodec.models.prompt import Prompt
from sociodec.models.strategy import Agent, ProtocolStep
from sociodec.runtime import ProtocolContext, ProtocolInvoker, run_strategy
from sociodec.protocol_decoding import parse_candidate
from sociodec.strategy_decoding import DecisionAdjudication, ProtocolDecisionDecoder
from sociodec.strategy_protocols import build_strategy_blueprint

ModelResolver = Callable[[E1Condition, tuple[str, ...]], Mapping[str, str]]
PromptViewFactory = Callable[[StrategyId, Prompt, AggregatedExtraction, tuple[str, ...]], Mapping[str, str]]
InvokerFactory = Callable[[Agent, int], ProtocolInvoker]

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
                 agent_contexts: Mapping[str, str] | None = None,
                 adjudications: Mapping[StrategyId | str, DecisionAdjudication] | None = None,
                 n: int = 3, k: int = 3, T: int = 2,
                 delphi_epsilon: float = 0.1,
                 mediation_epsilon: float = 0.1,
                 consensus_epsilon: float = 0.1):
        if min(n, k, T) < 1: raise ValueError("n, k and T must be >= 1")
        self.extraction, self.model_resolver, self.invoker_factory = extraction, model_resolver, invoker_factory
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
            raise ValueError("homogeneous condition requires one shared model identity")
        if condition.model_mode == "heterogeneous" and len(distinct) < 2:
            raise ValueError("heterogeneous condition requires at least two model identities")
        views = None
        if self.prompt_view_factory:
            views = dict(self.prompt_view_factory(sid, prompt, self.extraction, agent_ids))
            if set(views) != set(agent_ids) or any(not isinstance(v, str) or not v.strip() for v in views.values()):
                raise ValueError("prompt_view_factory must return one non-empty view per agent")
        elif sid is StrategyId.S12:
            raise ValueError("S12 requires explicit facet prompt views; S1 partitions are generated by its coordinator")
        blueprint = build_strategy_blueprint(sid, model_ids=models, prompt_views=views,
            agent_contexts=self.agent_contexts, n=self.n, k=self.k, T=self.T)
        routes = {a.identifier: self.invoker_factory(a, seed) for a in blueprint.strategy.agents}
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
        run = run_strategy(sid.value, prompt, blueprint.strategy, invoker,
            prompt_views=blueprint.prompt_views, hypotheses=self.extraction.hypotheses,
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
                "strategy_calls_executed": run.calls_made,
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
                "agent_model_ids": models, "seeded_agents": list(run.seeded_agents),
                "output_count": len(run.outputs), "decision_rule": decoded.decision.rule,
                "decision_selected_candidate": decoded.decision.selected_candidate_id,
                "decision_rationale": decoded.decision.rationale, "trace_complete": len(traces) == run.calls_made,
            })
