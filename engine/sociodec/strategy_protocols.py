"""Concrete, paper-table protocol blueprints for all thirteen strategies.

These builders define SocialStrategy roles, visibility and protocol steps.
Prompt partitioning and semantic output decoding are explicit caller inputs;
they are never guessed by the adapter layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from sociodec.catalogue import StrategyId, get_strategy
from sociodec.models.strategy import (
    Action, Agent, DecisionRule, ProtocolStep, Role, RoleAssignment,
    SocialStrategy, VisibilityRound,
)


@dataclass(frozen=True, slots=True)
class StrategyBlueprint:
    strategy_id: StrategyId
    strategy: SocialStrategy
    prompt_views: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.prompt_views or any(not value.strip() for value in self.prompt_views.values()):
            raise ValueError("Every strategy agent must receive a non-empty prompt view")


def _pairs(agent_ids: tuple[str, ...], *, full: bool) -> tuple[tuple[str, str], ...]:
    if full:
        return tuple((observer, author) for observer in agent_ids for author in agent_ids)
    return tuple((agent, agent) for agent in agent_ids)


def _make(
    sid: StrategyId,
    agent_ids: tuple[str, ...],
    model_ids: Mapping[str, str],
    roles_by_round: Mapping[tuple[str, int], Role],
    protocol: tuple[ProtocolStep, ...],
    decision: DecisionRule,
    rounds: int,
    visibility_by_round: Mapping[int, tuple[tuple[str, str], ...]],
    prompt_views: Mapping[str, str] | None,
    agent_contexts: Mapping[str, str] | None,
) -> StrategyBlueprint:
    contexts = dict(agent_contexts or {})
    agents = tuple(
        Agent(identifier, model_ids.get(identifier, "default-model"),
              contexts.get(identifier, f"Social strategy agent {identifier}"))
        for identifier in agent_ids
    )
    roles = tuple(dict.fromkeys(roles_by_round.values()))
    assignments = tuple(
        RoleAssignment(agent, round_number, roles_by_round[(agent, round_number)])
        for round_number in range(1, rounds + 1)
        for agent in agent_ids
    )
    visibility = tuple(
        VisibilityRound(round_number, tuple(dict.fromkeys(visibility_by_round[round_number])))
        for round_number in range(1, rounds + 1)
    )
    strategy = SocialStrategy(
        agents, roles, assignments, visibility, protocol, decision, rounds,
        anonymous=(sid is StrategyId.S4 or sid is StrategyId.S3),
    )
    views = dict(prompt_views or {})
    if not views:
        views = {agent: "FULL_PROMPT" for agent in agent_ids}
    if set(views) != set(agent_ids):
        raise ValueError("prompt_views must provide exactly one view for every strategy agent")
    if any(not isinstance(value, str) or not value.strip() for value in views.values()):
        raise ValueError("prompt_views must contain non-empty strings")
    return StrategyBlueprint(sid, strategy, views)


def build_strategy_blueprint(
    identifier: StrategyId | str,
    *,
    model_ids: Mapping[str, str] | None = None,
    prompt_views: Mapping[str, str] | None = None,
    agent_contexts: Mapping[str, str] | None = None,
    n: int = 3,
    k: int = 3,
    T: int = 2,
) -> StrategyBlueprint:
    """Build a concrete SocialStrategy protocol from Table 4.

    For S1, n means specialist count; for S8, k means reviewer count;
    for other strategies, n is participant/author count where applicable.
    """
    sid = StrategyId(identifier)
    if n < 1 or k < 1 or T < 1:
        raise ValueError("n, k and T must be >= 1")
    models = dict(model_ids or {})
    p: list[ProtocolStep] = []
    roles: dict[tuple[str, int], Role] = {}
    visibility: dict[int, tuple[tuple[str, str], ...]] = {}

    def add_roles(ids: tuple[str, ...], rounds: int, role_map: Mapping[str, Role] | None = None) -> None:
        for r in range(1, rounds + 1):
            for agent in ids:
                roles[(agent, r)] = (role_map or {}).get(agent, Role.DECOMPOSER)

    if sid is StrategyId.S1:
        specialists = tuple(f"specialist-{i+1}" for i in range(n))
        ids = ("coordinator", *specialists)
        add_roles(ids, 1, {"coordinator": Role.COORDINATOR})
        roles[("coordinator", 2)] = Role.COORDINATOR
        roles.update({(a, 2): Role.DECOMPOSER for a in specialists})
        roles[("coordinator", 3)] = Role.COORDINATOR
        roles.update({(a, 3): Role.DECOMPOSER for a in specialists})
        p.extend([
            ProtocolStep("coordinator", Action.SPLIT, "prompt", 1, 1),
            *(ProtocolStep(a, Action.DRAFT, "prompt", 2, 2) for a in specialists),
            ProtocolStep("coordinator", Action.CHECK, "all_previous_outputs", 3, 3),
        ])
        for r in (1, 2, 3):
            visibility[r] = _pairs(ids, full=(r == 3))
        views = prompt_views
        if views is None:
            raise ValueError("S1 requires explicit prompt_views: coordinator prompt and one domain part per specialist")

    elif sid is StrategyId.S12:
        experts = tuple(f"expert-{i+1}" for i in range(n))
        ids = (*experts, "integrator")
        add_roles(ids, 2, {"integrator": Role.AGGREGATOR})
        roles.update({(a, 2): Role.AGGREGATOR if a == "integrator" else Role.DECOMPOSER for a in ids})
        p.extend(ProtocolStep(a, Action.DRAFT, "prompt", 1, 1) for a in experts)
        p.append(ProtocolStep("integrator", Action.MERGE, "all_previous_outputs", 2, 2))
        visibility[1] = _pairs(ids, full=False)
        visibility[2] = tuple((a, a) for a in experts) + tuple(("integrator", a) for a in experts) + (("integrator", "integrator"),)
        views = prompt_views
        if views is None:
            raise ValueError("S12 requires explicit prompt_views: one facet per expert and full view for integrator")

    elif sid is StrategyId.S2:
        participants = tuple(f"participant-{i+1}" for i in range(n))
        ids = (*participants, "aggregator")
        add_roles(ids, 2, {"aggregator": Role.AGGREGATOR})
        p.extend(ProtocolStep(a, Action.DRAFT, "prompt", 1, 1) for a in participants)
        p.append(ProtocolStep("aggregator", Action.MERGE, "all_previous_outputs", 2, 2))
        visibility[1] = _pairs(ids, full=False)
        visibility[2] = tuple((a, a) for a in participants) + tuple(("aggregator", a) for a in participants) + (("aggregator", "aggregator"),)
        views = prompt_views or {a: "FULL_PROMPT" for a in ids}

    elif sid is StrategyId.S3:
        members = tuple(f"member-{i+1}" for i in range(n))
        ids = members
        add_roles(ids, 2)
        p.extend(ProtocolStep(a, Action.DRAFT, "prompt", 1, 1) for a in members)
        p.extend(ProtocolStep(a, Action.RANK, "all_previous_outputs", 2, 2) for a in members)
        visibility[1] = _pairs(ids, full=False)
        visibility[2] = _pairs(ids, full=True)
        views = prompt_views or {a: "FULL_PROMPT" for a in ids}

    elif sid is StrategyId.S4:
        experts = tuple(f"expert-{i+1}" for i in range(n))
        ids = (*experts, "facilitator")
        add_roles(ids, T, {"facilitator": Role.FACILITATOR})
        for t in range(1, T + 1):
            draft_stage, summary_stage = 2*t - 1, 2*t
            action = Action.DRAFT if t == 1 else Action.REVISE
            input_ref = "prompt" if t == 1 else "all_previous_outputs"
            p.extend(ProtocolStep(a, action, input_ref, t, draft_stage) for a in experts)
            p.append(ProtocolStep("facilitator", Action.SUMMARISE, "all_previous_outputs", t, summary_stage))
            expert_pairs = tuple((a, a) for a in experts) + tuple((a, "facilitator") for a in experts)
            facilitator_pairs = tuple(("facilitator", a) for a in experts) + (("facilitator", "facilitator"),)
            visibility[t] = expert_pairs + facilitator_pairs
        views = prompt_views or {a: "FULL_PROMPT" for a in ids}

    elif sid is StrategyId.S9:
        voters = tuple(f"voter-{i+1}" for i in range(n))
        ids = voters
        add_roles(ids, 2)
        p.extend(ProtocolStep(a, Action.DRAFT, "prompt", 1, 1) for a in voters)
        p.extend(ProtocolStep(a, Action.VOTE, "all_previous_outputs", 2, 2) for a in voters)
        visibility[1] = _pairs(ids, full=False)
        visibility[2] = _pairs(ids, full=True)
        views = prompt_views or {a: "FULL_PROMPT" for a in ids}

    elif sid is StrategyId.S5:
        ids = ("author", "critic", "judge")
        add_roles(ids, 1, {"author": Role.DECOMPOSER, "critic": Role.CRITIC, "judge": Role.JUDGE})
        p.extend((
            ProtocolStep("author", Action.DRAFT, "prompt", 1, 1),
            ProtocolStep("critic", Action.CRITIQUE, "step:0", 1, 2),
            ProtocolStep("author", Action.REVISE, "step:1", 1, 3),
            ProtocolStep("judge", Action.JUDGE, "all_previous_outputs", 1, 4),
        ))
        visibility[1] = _pairs(ids, full=True)
        views = prompt_views or {a: "FULL_PROMPT" for a in ids}

    elif sid is StrategyId.S6:
        ids = ("decomposer-1", "decomposer-2", "synthesizer")
        add_roles(ids, 1, {"decomposer-1": Role.DECOMPOSER, "decomposer-2": Role.DECOMPOSER, "synthesizer": Role.AGGREGATOR})
        p.extend((
            ProtocolStep("decomposer-1", Action.DRAFT, "prompt", 1, 1),
            ProtocolStep("decomposer-2", Action.COUNTER_PLAN, "step:0", 1, 2),
            ProtocolStep("synthesizer", Action.MERGE, "all_previous_outputs", 1, 3),
        ))
        # Directional visibility: the counter-plan author sees D1, but D1
        # cannot see D2; the synthesizer sees both drafts.
        visibility[1] = (
            ("decomposer-1", "decomposer-1"),
            ("decomposer-2", "decomposer-2"),
            ("decomposer-2", "decomposer-1"),
            ("synthesizer", "synthesizer"),
            ("synthesizer", "decomposer-1"),
            ("synthesizer", "decomposer-2"),
        )
        views = prompt_views or {a: "FULL_PROMPT" for a in ids}

    elif sid is StrategyId.S8:
        reviewers = tuple(f"reviewer-{i+1}" for i in range(k))
        ids = ("author", *reviewers, "editor")
        add_roles(ids, 4, {"author": Role.DECOMPOSER, "editor": Role.JUDGE, **{a: Role.CRITIC for a in reviewers}})
        p.append(ProtocolStep("author", Action.DRAFT, "prompt", 1, 1))
        p.extend(ProtocolStep(a, Action.CRITIQUE, "step:0", 2, 2) for a in reviewers)
        p.append(ProtocolStep("editor", Action.JUDGE, "all_previous_outputs", 3, 3))
        p.append(ProtocolStep("author", Action.REVISE, "all_previous_outputs", 4, 4))
        visibility[1] = _pairs(ids, full=False)
        review_pairs = [("author", "author"), ("editor", "editor")]
        for reviewer in reviewers:
            review_pairs.extend(((reviewer, "author"), (reviewer, reviewer)))
        visibility[2] = tuple(review_pairs)
        visibility[3] = tuple([("editor", a) for a in ids] + [(a, a) for a in ids])
        visibility[4] = tuple([("author", a) for a in ids] + [(a, a) for a in ids])
        views = prompt_views or {a: "FULL_PROMPT" for a in ids}

    elif sid is StrategyId.S13:
        ids = ("agent-A", "agent-B")
        for r, mapping in (
            (1, {"agent-A": Role.DECOMPOSER, "agent-B": Role.CRITIC}),
            (2, {"agent-A": Role.CRITIC, "agent-B": Role.DECOMPOSER}),
        ):
            roles.update({(a, r): mapping[a] for a in ids})
        p.extend((
            ProtocolStep("agent-A", Action.DRAFT, "prompt", 1, 1),
            ProtocolStep("agent-B", Action.CRITIQUE, "step:0", 1, 2),
            ProtocolStep("agent-B", Action.REVISE, "all_previous_outputs", 2, 3),
            ProtocolStep("agent-A", Action.CRITIQUE, "step:2", 2, 4),
        ))
        visibility[1] = _pairs(ids, full=True)
        visibility[2] = _pairs(ids, full=True)
        views = prompt_views or {a: "FULL_PROMPT" for a in ids}

    elif sid is StrategyId.S7:
        ids = ("party-1", "party-2", "judge")
        add_roles(ids, 3, {"party-1": Role.DECOMPOSER, "party-2": Role.DECOMPOSER, "judge": Role.JUDGE})
        p.extend((
            ProtocolStep("party-1", Action.DRAFT, "prompt", 1, 1),
            ProtocolStep("party-2", Action.DRAFT, "prompt", 1, 1),
            ProtocolStep("party-1", Action.DEFEND, "step:0", 2, 2),
            ProtocolStep("party-2", Action.DEFEND, "step:1", 2, 2),
            ProtocolStep("judge", Action.JUDGE, "all_previous_outputs", 3, 3),
        ))
        visibility[1] = _pairs(ids, full=False)
        visibility[2] = (("party-1", "party-1"), ("party-2", "party-2"), ("judge", "party-1"), ("judge", "party-2"), ("judge", "judge"))
        visibility[3] = _pairs(ids, full=True)
        views = prompt_views or {a: "FULL_PROMPT" for a in ids}

    elif sid is StrategyId.S11:
        ids = ("party-1", "party-2", "mediator")
        add_roles(ids, T, {"party-1": Role.DECOMPOSER, "party-2": Role.DECOMPOSER, "mediator": Role.MEDIATOR})
        # The initial round drafts independently once. Every mediation round
        # thereafter is one mediator summary followed by parallel revisions.
        p.extend((
            ProtocolStep("party-1", Action.DRAFT, "prompt", 1, 1),
            ProtocolStep("party-2", Action.DRAFT, "prompt", 1, 1),
        ))
        for round_number in range(1, T + 1):
            summary_stage = 2 * round_number
            revision_stage = summary_stage + 1
            p.extend((
                ProtocolStep("mediator", Action.SUMMARISE, "all_previous_outputs", round_number, summary_stage),
                ProtocolStep("party-1", Action.REVISE, "all_previous_outputs", round_number, revision_stage),
                ProtocolStep("party-2", Action.REVISE, "all_previous_outputs", round_number, revision_stage),
            ))
            visibility[round_number] = _pairs(ids, full=True)
        views = prompt_views or {a: "FULL_PROMPT" for a in ids}

    elif sid is StrategyId.S10:
        participants = tuple(f"participant-{i+1}" for i in range(n))
        ids = (*participants, "moderator")
        add_roles(ids, T, {"moderator": Role.MODERATOR})
        stage = 1
        for t in range(1, T + 1):
            for participant in participants:
                p.append(ProtocolStep(participant, Action.REVISE, "all_previous_outputs", t, stage))
                stage += 1
        p.append(ProtocolStep("moderator", Action.JUDGE, "all_previous_outputs", T, stage))
        visibility = {t: _pairs(ids, full=True) for t in range(1, T + 1)}
        views = prompt_views or {a: "FULL_PROMPT" for a in ids}

    else:
        raise ValueError(f"Unsupported established strategy: {sid}")

    blueprint = _make(
        sid, tuple(ids), models, roles, tuple(p),
        DecisionRule(get_strategy(sid).decision_rule),
        (3 if sid in {StrategyId.S1, StrategyId.S7} else T if sid in {StrategyId.S4, StrategyId.S10, StrategyId.S11} else 4 if sid is StrategyId.S8 else 2 if sid in {StrategyId.S2, StrategyId.S3, StrategyId.S9, StrategyId.S12, StrategyId.S13} else 1),
        visibility, views, agent_contexts,
    )
    expected_calls = get_strategy(sid).calls(n=n, k=k, T=T)
    if sid not in {StrategyId.S11} and blueprint.strategy.calls != expected_calls:
        raise AssertionError(
            f"{sid.value} protocol has {blueprint.strategy.calls} calls; Table 4 requires {expected_calls}"
        )
    return blueprint
