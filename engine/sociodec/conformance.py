"""Executable catalogue-to-blueprint conformance oracle.

The oracle is intentionally separate from strategy_protocols.py: expected
protocol signatures are derived from the paper's Table 4 and strategy
sections, then compared with the concrete factory output. Passing this module
is implementation-conformance evidence, not a proof of strategy correctness.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from sociodec.catalogue import STRATEGIES, StrategyId, get_strategy
from sociodec.models.strategy import Action, DecisionRule, Role, SocialStrategy
from sociodec.strategy_protocols import StrategyBlueprint, build_strategy_blueprint


@dataclass(frozen=True, slots=True)
class StrategySemanticProfile:
    strategy_id: StrategyId
    name: str
    agent_count_formula: str
    roles: tuple[Role, ...]
    rounds_formula: str
    action_sequence: str
    input_references: tuple[str, ...]
    visibility_contract: str
    decision_rule: DecisionRule
    table4_calls_formula: str
    table4_depth_formula: str
    runtime_calls_formula: str
    runtime_depth_formula: str
    anonymous: bool


@dataclass(frozen=True, slots=True)
class ConformanceFinding:
    invariant: str
    message: str


@dataclass(frozen=True, slots=True)
class ConformanceReport:
    strategy_id: StrategyId
    parameters: tuple[int, int, int]
    expected_calls: int
    actual_calls: int
    expected_depth: int
    actual_depth: int
    findings: tuple[ConformanceFinding, ...]

    @property
    def passed(self) -> bool:
        return not self.findings


# The profile table is the machine-readable contract. Candidate C1-C5 are
# deliberately absent: they are not among the paper's thirteen strategies.
_PROFILE_DATA = {
    StrategyId.S1: ("n+1", (Role.COORDINATOR, Role.DECOMPOSER), "3",
        "SPLIT | DRAFT[n] | CHECK", ("prompt", "all_previous_outputs"),
        "domain-partitioned specialists; coordinator integrates", "n+2", "3", "n+2", "3", False),
    StrategyId.S12: ("n+1", (Role.DECOMPOSER, Role.AGGREGATOR), "2",
        "DRAFT[n] | MERGE", ("prompt", "all_previous_outputs"),
        "isolated facet experts; integrator sees all expert outputs", "n+1", "2", "n+1", "2", False),
    StrategyId.S2: ("n+1", (Role.DECOMPOSER, Role.AGGREGATOR), "2",
        "DRAFT[n] | MERGE", ("prompt", "all_previous_outputs"),
        "independent generation; aggregator sees pooled outputs", "n+1", "2", "n+1", "2", False),
    StrategyId.S3: ("n", (Role.DECOMPOSER,), "2",
        "DRAFT[n] | RANK[n]", ("prompt", "all_previous_outputs"),
        "drafts isolated; all pooled drafts visible for ranking", "2n", "2", "2n", "2", True),
    StrategyId.S4: ("n+1", (Role.DECOMPOSER, Role.FACILITATOR), "T",
        "(DRAFT[n] | SUMMARISE) then (REVISE[n] | SUMMARISE) repeated",
        ("prompt", "all_previous_outputs"),
        "anonymous expert exchange; facilitator sees expert outputs", "T(n+1)", "2T", "T(n+1)", "2T", True),
    StrategyId.S9: ("n", (Role.DECOMPOSER,), "2",
        "DRAFT[n] | VOTE[n]", ("prompt", "all_previous_outputs"),
        "drafts isolated; pooled candidates visible for voting", "2n", "2", "2n", "2", False),
    StrategyId.S5: ("3", (Role.DECOMPOSER, Role.CRITIC, Role.JUDGE), "1",
        "DRAFT | CRITIQUE | REVISE | JUDGE", ("prompt", "step:0", "step:1", "all_previous_outputs"),
        "author draft visible to critic; judge sees trace", "4", "4", "4", "4", False),
    StrategyId.S6: ("3", (Role.DECOMPOSER, Role.AGGREGATOR), "1",
        "DRAFT | COUNTER_PLAN | MERGE", ("prompt", "step:0", "all_previous_outputs"),
        "second decomposer sees first; synthesizer sees both", "3", "3", "3", "3", False),
    StrategyId.S8: ("k+2", (Role.DECOMPOSER, Role.CRITIC, Role.JUDGE), "4",
        "DRAFT | CRITIQUE[k] | JUDGE | REVISE", ("prompt", "step:0", "all_previous_outputs"),
        "reviewers independently see author; editor sees all reviews", "k+3", "4", "k+3", "4", False),
    StrategyId.S13: ("2", (Role.DECOMPOSER, Role.CRITIC), "2",
        "DRAFT | CRITIQUE | REVISE | CRITIQUE", ("prompt", "step:0", "step:2"),
        "full visibility; decomposer and critic roles swap", "4", "4", "4", "4", False),
    StrategyId.S7: ("3", (Role.DECOMPOSER, Role.JUDGE), "3",
        "DRAFT[2] | DEFEND[2] | JUDGE", ("prompt", "step:0", "step:1", "all_previous_outputs"),
        "parties isolated; judge sees both defended cases", "5", "3", "5", "3", False),
    StrategyId.S11: ("3", (Role.DECOMPOSER, Role.MEDIATOR), "T",
        "DRAFT[2] | (SUMMARISE | REVISE[2]) repeated T times",
        ("prompt", "all_previous_outputs"),
        "mediator and both parties see both drafts and revisions", "5", "3",
        "2+3T", "1+2T", False),
    StrategyId.S10: ("n+1", (Role.DECOMPOSER, Role.MODERATOR), "T",
        "REVISE[n] repeated T turns | JUDGE", ("all_previous_outputs",),
        "every participant sees every preceding turn", "nT+1", "nT+1", "nT+1", "nT+1", False),
}


PROFILES: tuple[StrategySemanticProfile, ...] = tuple(
    StrategySemanticProfile(
        definition.identifier, definition.name,
        _PROFILE_DATA[definition.identifier][0],
        _PROFILE_DATA[definition.identifier][1],
        _PROFILE_DATA[definition.identifier][2],
        _PROFILE_DATA[definition.identifier][3],
        _PROFILE_DATA[definition.identifier][4],
        _PROFILE_DATA[definition.identifier][5],
        DecisionRule(definition.decision_rule),
        _PROFILE_DATA[definition.identifier][6],
        _PROFILE_DATA[definition.identifier][7],
        _PROFILE_DATA[definition.identifier][8],
        _PROFILE_DATA[definition.identifier][9],
        _PROFILE_DATA[definition.identifier][10],
    )
    for definition in STRATEGIES
)
PROFILE_BY_ID = {profile.strategy_id: profile for profile in PROFILES}


def _formula_value(expression: str, n: int, k: int, T: int) -> int:
    """Evaluate only the finite, reviewed formula vocabulary used by profiles."""
    formulas = {
        "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
        "n": n, "k": k, "T": T,
        "n+1": n + 1, "n+2": n + 2, "k+2": k + 2, "k+3": k + 3,
        "2n": 2 * n, "2T": 2 * T, "T(n+1)": T * (n + 1), "nT+1": n * T + 1,
        "2+3T": 2 + 3 * T, "1+2T": 1 + 2 * T,
    }
    try:
        return formulas[expression]
    except KeyError as exc:
        raise ValueError(f"Unsupported strategy profile formula: {expression}") from exc


def _expected_agent_ids(sid: StrategyId, n: int, k: int) -> tuple[str, ...]:
    if sid is StrategyId.S1:
        return ("coordinator", *(f"specialist-{i}" for i in range(1, n + 1)))
    if sid is StrategyId.S12:
        return (*(f"expert-{i}" for i in range(1, n + 1)), "integrator")
    if sid is StrategyId.S2:
        return (*(f"participant-{i}" for i in range(1, n + 1)), "aggregator")
    if sid is StrategyId.S3:
        return tuple(f"member-{i}" for i in range(1, n + 1))
    if sid is StrategyId.S4:
        return (*(f"expert-{i}" for i in range(1, n + 1)), "facilitator")
    if sid is StrategyId.S9:
        return tuple(f"voter-{i}" for i in range(1, n + 1))
    if sid is StrategyId.S5:
        return ("author", "critic", "judge")
    if sid is StrategyId.S6:
        return ("decomposer-1", "decomposer-2", "synthesizer")
    if sid is StrategyId.S8:
        return ("author", *(f"reviewer-{i}" for i in range(1, k + 1)), "editor")
    if sid is StrategyId.S13:
        return ("agent-A", "agent-B")
    if sid is StrategyId.S7:
        return ("party-1", "party-2", "judge")
    if sid is StrategyId.S11:
        return ("party-1", "party-2", "mediator")
    if sid is StrategyId.S10:
        return (*(f"participant-{i}" for i in range(1, n + 1)), "moderator")
    raise ValueError(f"Unknown paper strategy: {sid}")


def _expected_rounds(sid: StrategyId, T: int) -> int:
    if sid in {StrategyId.S4, StrategyId.S10, StrategyId.S11}:
        return T
    if sid is StrategyId.S1 or sid is StrategyId.S7:
        return 3
    if sid is StrategyId.S8:
        return 4
    if sid is StrategyId.S13 or sid in {StrategyId.S2, StrategyId.S3, StrategyId.S9, StrategyId.S12}:
        return 2
    return 1


def _expected_role(sid: StrategyId, agent: str, round_number: int) -> Role:
    if sid is StrategyId.S1:
        return Role.COORDINATOR if agent == "coordinator" else Role.DECOMPOSER
    if sid in {StrategyId.S12, StrategyId.S2}:
        return Role.AGGREGATOR if agent in {"integrator", "aggregator"} else Role.DECOMPOSER
    if sid in {StrategyId.S3, StrategyId.S9}:
        return Role.DECOMPOSER
    if sid is StrategyId.S4:
        return Role.FACILITATOR if agent == "facilitator" else Role.DECOMPOSER
    if sid is StrategyId.S5:
        return {"author": Role.DECOMPOSER, "critic": Role.CRITIC, "judge": Role.JUDGE}[agent]
    if sid is StrategyId.S6:
        return Role.AGGREGATOR if agent == "synthesizer" else Role.DECOMPOSER
    if sid is StrategyId.S8:
        return Role.JUDGE if agent == "editor" else Role.CRITIC if agent.startswith("reviewer-") else Role.DECOMPOSER
    if sid is StrategyId.S13:
        if round_number == 1:
            return Role.DECOMPOSER if agent == "agent-A" else Role.CRITIC
        return Role.CRITIC if agent == "agent-A" else Role.DECOMPOSER
    if sid is StrategyId.S7:
        return Role.JUDGE if agent == "judge" else Role.DECOMPOSER
    if sid is StrategyId.S11:
        return Role.MEDIATOR if agent == "mediator" else Role.DECOMPOSER
    if sid is StrategyId.S10:
        return Role.MODERATOR if agent == "moderator" else Role.DECOMPOSER
    raise ValueError(f"No role oracle for {sid}")


def _expected_steps(sid: StrategyId, n: int, k: int, T: int):
    steps: list[tuple[str, Action, str, int, int]] = []
    add = steps.append
    if sid is StrategyId.S1:
        add(("coordinator", Action.SPLIT, "prompt", 1, 1))
        steps.extend((f"specialist-{i}", Action.DRAFT, "prompt", 2, 2) for i in range(1, n + 1))
        add(("coordinator", Action.CHECK, "all_previous_outputs", 3, 3))
    elif sid in {StrategyId.S12, StrategyId.S2}:
        prefix, merger = ("expert-", "integrator") if sid is StrategyId.S12 else ("participant-", "aggregator")
        steps.extend((f"{prefix}{i}", Action.DRAFT, "prompt", 1, 1) for i in range(1, n + 1))
        add((merger, Action.MERGE, "all_previous_outputs", 2, 2))
    elif sid is StrategyId.S3:
        steps.extend((f"member-{i}", Action.DRAFT, "prompt", 1, 1) for i in range(1, n + 1))
        steps.extend((f"member-{i}", Action.RANK, "all_previous_outputs", 2, 2) for i in range(1, n + 1))
    elif sid is StrategyId.S4:
        for t in range(1, T + 1):
            action, ref, stage = (Action.DRAFT, "prompt", 2*t-1) if t == 1 else (Action.REVISE, "all_previous_outputs", 2*t-1)
            steps.extend((f"expert-{i}", action, ref, t, stage) for i in range(1, n + 1))
            add(("facilitator", Action.SUMMARISE, "all_previous_outputs", t, 2*t))
    elif sid is StrategyId.S9:
        steps.extend((f"voter-{i}", Action.DRAFT, "prompt", 1, 1) for i in range(1, n + 1))
        steps.extend((f"voter-{i}", Action.VOTE, "all_previous_outputs", 2, 2) for i in range(1, n + 1))
    elif sid is StrategyId.S5:
        steps.extend((("author", Action.DRAFT, "prompt", 1, 1),
                      ("critic", Action.CRITIQUE, "step:0", 1, 2),
                      ("author", Action.REVISE, "step:1", 1, 3),
                      ("judge", Action.JUDGE, "all_previous_outputs", 1, 4)))
    elif sid is StrategyId.S6:
        steps.extend((("decomposer-1", Action.DRAFT, "prompt", 1, 1),
                      ("decomposer-2", Action.COUNTER_PLAN, "step:0", 1, 2),
                      ("synthesizer", Action.MERGE, "all_previous_outputs", 1, 3)))
    elif sid is StrategyId.S8:
        steps.append(("author", Action.DRAFT, "prompt", 1, 1))
        steps.extend((f"reviewer-{i}", Action.CRITIQUE, "step:0", 2, 2) for i in range(1, k + 1))
        steps.extend((("editor", Action.JUDGE, "all_previous_outputs", 3, 3),
                      ("author", Action.REVISE, "all_previous_outputs", 4, 4)))
    elif sid is StrategyId.S13:
        steps.extend((("agent-A", Action.DRAFT, "prompt", 1, 1),
                      ("agent-B", Action.CRITIQUE, "step:0", 1, 2),
                      ("agent-B", Action.REVISE, "all_previous_outputs", 2, 3),
                      ("agent-A", Action.CRITIQUE, "step:2", 2, 4)))
    elif sid is StrategyId.S7:
        steps.extend((("party-1", Action.DRAFT, "prompt", 1, 1),
                      ("party-2", Action.DRAFT, "prompt", 1, 1),
                      ("party-1", Action.DEFEND, "step:0", 2, 2),
                      ("party-2", Action.DEFEND, "step:1", 2, 2),
                      ("judge", Action.JUDGE, "all_previous_outputs", 3, 3)))
    elif sid is StrategyId.S11:
        steps.extend((("party-1", Action.DRAFT, "prompt", 1, 1),
                      ("party-2", Action.DRAFT, "prompt", 1, 1)))
        for t in range(1, T + 1):
            steps.append(("mediator", Action.SUMMARISE, "all_previous_outputs", t, 2*t))
            steps.extend((("party-1", Action.REVISE, "all_previous_outputs", t, 2*t+1),
                          ("party-2", Action.REVISE, "all_previous_outputs", t, 2*t+1)))
    elif sid is StrategyId.S10:
        stage = 1
        for t in range(1, T + 1):
            for i in range(1, n + 1):
                steps.append((f"participant-{i}", Action.REVISE, "all_previous_outputs", t, stage))
                stage += 1
        steps.append(("moderator", Action.JUDGE, "all_previous_outputs", T, stage))
    return tuple(steps)


def _expected_visibility(sid: StrategyId, agent_ids: tuple[str, ...], T: int):
    pairs_by_round: dict[int, tuple[tuple[str, str], ...]] = {}
    own = tuple((agent, agent) for agent in agent_ids)
    full = tuple((observer, author) for observer in agent_ids for author in agent_ids)
    if sid is StrategyId.S1:
        for r in range(1, 4):
            pairs_by_round[r] = full if r == 3 else own
    elif sid is StrategyId.S2:
        participants = tuple(a for a in agent_ids if a != "aggregator")
        pairs_by_round[1] = own
        pairs_by_round[2] = own + tuple(("aggregator", a) for a in participants)
    elif sid in {StrategyId.S3, StrategyId.S9}:
        pairs_by_round[1] = own
        pairs_by_round[2] = full
    elif sid is StrategyId.S12:
        experts = tuple(a for a in agent_ids if a != "integrator")
        pairs_by_round[1] = own
        pairs_by_round[2] = own + tuple(("integrator", a) for a in experts)
    elif sid is StrategyId.S4:
        experts = tuple(a for a in agent_ids if a != "facilitator")
        for t in range(1, T + 1):
            pairs_by_round[t] = (
                tuple((a, a) for a in experts)
                + tuple((a, "facilitator") for a in experts)
                + tuple(("facilitator", a) for a in experts)
                + (("facilitator", "facilitator"),)
            )
    elif sid is StrategyId.S5:
        pairs_by_round[1] = full
    elif sid is StrategyId.S6:
        pairs_by_round[1] = (
            ("decomposer-1", "decomposer-1"),
            ("decomposer-2", "decomposer-2"), ("decomposer-2", "decomposer-1"),
            ("synthesizer", "synthesizer"), ("synthesizer", "decomposer-1"),
            ("synthesizer", "decomposer-2"),
        )
    elif sid is StrategyId.S8:
        reviewers = tuple(a for a in agent_ids if a.startswith("reviewer-"))
        pairs_by_round[1] = own
        pairs_by_round[2] = (("author", "author"), ("editor", "editor")) + tuple(
            pair for reviewer in reviewers for pair in ((reviewer, "author"), (reviewer, reviewer))
        )
        pairs_by_round[3] = tuple(("editor", a) for a in agent_ids) + own
        pairs_by_round[4] = tuple(("author", a) for a in agent_ids) + own
    elif sid is StrategyId.S13:
        pairs_by_round[1] = full
        pairs_by_round[2] = full
    elif sid is StrategyId.S7:
        pairs_by_round[1] = own
        pairs_by_round[2] = (("party-1", "party-1"), ("party-2", "party-2"),
                             ("judge", "party-1"), ("judge", "party-2"), ("judge", "judge"))
        pairs_by_round[3] = full
    elif sid is StrategyId.S11:
        for t in range(1, T + 1):
            pairs_by_round[t] = full
    elif sid is StrategyId.S10:
        for t in range(1, T + 1):
            pairs_by_round[t] = full
    return tuple((r, frozenset(pairs)) for r, pairs in sorted(pairs_by_round.items()))


def _expected_call_depth(sid: StrategyId, n: int, k: int, T: int) -> tuple[int, int]:
    calls = {
        StrategyId.S1: n + 2, StrategyId.S12: n + 1, StrategyId.S2: n + 1,
        StrategyId.S3: 2*n, StrategyId.S4: T*(n+1), StrategyId.S9: 2*n,
        StrategyId.S5: 4, StrategyId.S6: 3, StrategyId.S8: k+3,
        StrategyId.S13: 4, StrategyId.S7: 5, StrategyId.S11: 2+3*T,
        StrategyId.S10: n*T+1,
    }[sid]
    depth = {
        StrategyId.S1: 3, StrategyId.S12: 2, StrategyId.S2: 2, StrategyId.S3: 2,
        StrategyId.S4: 2*T, StrategyId.S9: 2, StrategyId.S5: 4, StrategyId.S6: 3,
        StrategyId.S8: 4, StrategyId.S13: 4, StrategyId.S7: 3,
        StrategyId.S11: 1+2*T, StrategyId.S10: n*T+1,
    }[sid]
    return calls, depth


def _role_map(strategy: SocialStrategy) -> dict[tuple[str, int], Role]:
    return {(item.agent_id, item.round): item.role for item in strategy.assignments}


def validate_blueprint(blueprint: StrategyBlueprint, *, n: int = 3, k: int = 3, T: int = 2) -> ConformanceReport:
    """Compare one generated blueprint against the independent paper oracle."""
    if min(n, k, T) < 1:
        raise ValueError("n, k and T must be >= 1")
    sid = blueprint.strategy_id
    profile = PROFILE_BY_ID[sid]
    definition = get_strategy(sid)
    strategy = blueprint.strategy
    findings: list[ConformanceFinding] = []

    def check(name: str, ok: bool, message: str) -> None:
        if not ok:
            findings.append(ConformanceFinding(name, message))

    check("catalogue-name", profile.name == definition.name,
          "semantic profile name differs from canonical strategy catalogue")
    check("catalogue-decision-rule", profile.decision_rule.value == definition.decision_rule,
          "semantic profile decision rule differs from canonical strategy catalogue")
    check("catalogue-table4-calls", profile.table4_calls_formula == definition.call_formula,
          "semantic profile Table 4 call formula differs from canonical strategy catalogue")
    check("catalogue-table4-depth", profile.table4_depth_formula == definition.depth_formula,
          "semantic profile Table 4 depth formula differs from canonical strategy catalogue")

    expected_agents = _expected_agent_ids(sid, n, k)
    check("agent-count-formula", len(expected_agents) == _formula_value(profile.agent_count_formula, n, k, T),
          "profile agent-count formula does not match the expected roster")
    actual_agents = tuple(agent.identifier for agent in strategy.agents)
    check("agent-roster", actual_agents == expected_agents,
          f"expected ordered agents {expected_agents}, got {actual_agents}")
    check("prompt-view-roster", set(blueprint.prompt_views) == set(expected_agents),
          "prompt views must cover exactly the declared strategy agents")
    check("prompt-view-content", all(isinstance(v, str) and v.strip() for v in blueprint.prompt_views.values()),
          "every prompt view must be a non-empty string")

    expected_rounds = _expected_rounds(sid, T)
    check("rounds-formula", expected_rounds == _formula_value(profile.rounds_formula, n, k, T),
          "profile rounds formula does not match the expected protocol rounds")
    check("round-bound", strategy.rounds == expected_rounds,
          f"expected {expected_rounds} rounds, got {strategy.rounds}")
    expected_role_map = {
        (agent, r): _expected_role(sid, agent, r)
        for r in range(1, expected_rounds + 1) for agent in expected_agents
    }
    check("role-set", set(strategy.roles) == set(profile.roles),
          "declared role set differs from the paper strategy profile")
    check("role-assignment", _role_map(strategy) == expected_role_map,
          "role assignments differ from the paper strategy profile")
    check("decision-rule", strategy.decision_rule is profile.decision_rule,
          f"expected decision rule {profile.decision_rule.value}, got {strategy.decision_rule.value}")
    check("anonymity", strategy.anonymous is profile.anonymous,
          f"expected anonymous={profile.anonymous}, got {strategy.anonymous}")

    expected_steps = _expected_steps(sid, n, k, T)
    actual_steps = tuple((s.agent_id, s.action, s.input_ref, s.round, s.stage) for s in strategy.protocol)
    check("protocol-sequence", actual_steps == expected_steps,
          "ordered (agent, action, input_ref, round, stage) protocol signature differs from oracle")

    expected_visibility = dict(_expected_visibility(sid, expected_agents, T))
    actual_visibility = {v.round: frozenset(v.visible_pairs) for v in strategy.visibility}
    check("visibility", actual_visibility == expected_visibility,
          "visibility relation differs from the strategy's paper profile")

    expected_calls, expected_depth = _expected_call_depth(sid, n, k, T)
    check("runtime-calls-formula", expected_calls == _formula_value(profile.runtime_calls_formula, n, k, T),
          "profile runtime call formula does not match the independent protocol oracle")
    check("runtime-depth-formula", expected_depth == _formula_value(profile.runtime_depth_formula, n, k, T),
          "profile runtime depth formula does not match the independent protocol oracle")
    check("call-formula", strategy.calls == expected_calls,
          f"expected {expected_calls} model calls, got {strategy.calls}")
    check("depth-formula", strategy.depth == expected_depth,
          f"expected {expected_depth} stages, got {strategy.depth}")

    # Input references are checked as executable references, not just strings.
    for index, step in enumerate(strategy.protocol):
        if step.input_ref not in {"prompt", "all_previous_outputs"} and not step.input_ref.startswith("step:"):
            findings.append(ConformanceFinding(
                "input-reference", f"step {index} uses unsupported input reference {step.input_ref!r}"
            ))
        if step.input_ref.startswith("step:"):
            try:
                target_index = int(step.input_ref.split(":", 1)[1])
            except ValueError:
                target_index = -1
            valid_target = 0 <= target_index < index
            check("input-reference", valid_target,
                  f"step {index} references non-prior protocol output {step.input_ref!r}")
            if valid_target:
                target = strategy.protocol[target_index]
                visible = actual_visibility.get(step.round, frozenset())
                check("input-visibility", (step.agent_id, target.agent_id) in visible,
                      f"{step.agent_id} cannot see referenced output by {target.agent_id} in round {step.round}")
                check("input-stage", target.stage < step.stage,
                      f"{step.agent_id} references same/future stage output {step.input_ref}")

    return ConformanceReport(
        sid, (n, k, T), expected_calls, strategy.calls,
        expected_depth, strategy.depth, tuple(findings),
    )


def build_and_validate_all(*, n: int = 3, k: int = 3, T: int = 2) -> tuple[ConformanceReport, ...]:
    reports = []
    for definition in STRATEGIES:
        sid = definition.identifier
        views = None
        if sid is StrategyId.S1:
            views = {"coordinator": "FULL_PROMPT", **{f"specialist-{i}": f"DOMAIN:{i}" for i in range(1, n+1)}}
        elif sid is StrategyId.S12:
            views = {**{f"expert-{i}": f"FACET:{i}" for i in range(1, n+1)}, "integrator": "FULL_PROMPT"}
        blueprint = build_strategy_blueprint(sid, n=n, k=k, T=T, prompt_views=views)
        reports.append(validate_blueprint(blueprint, n=n, k=k, T=T))
    return tuple(reports)


def profile_as_dict(
    identifier: StrategyId | str, *, n: int = 3, k: int = 3, T: int = 2,
) -> dict[str, object]:
    """Return a concrete JSON-serializable strategy profile for given parameters."""
    if min(n, k, T) < 1:
        raise ValueError("n, k and T must be >= 1")
    sid = StrategyId(identifier)
    profile = PROFILE_BY_ID[sid]
    agents = _expected_agent_ids(sid, n, k)
    rounds = _expected_rounds(sid, T)
    protocol = _expected_steps(sid, n, k, T)
    visibility = _expected_visibility(sid, agents, T)
    calls, depth = _expected_call_depth(sid, n, k, T)
    payload = asdict(profile)
    payload["strategy_id"] = profile.strategy_id.value
    payload["roles"] = [role.value for role in profile.roles]
    payload["decision_rule"] = profile.decision_rule.value
    payload["parameters"] = {"n": n, "k": k, "T": T}
    payload["agents"] = list(agents)
    payload["rounds"] = rounds
    payload["role_assignments"] = [
        {"agent_id": agent, "round": round_number,
         "role": _expected_role(sid, agent, round_number).value}
        for round_number in range(1, rounds + 1) for agent in agents
    ]
    payload["protocol"] = [
        {"index": index, "agent_id": agent, "action": action.value,
         "input_ref": input_ref, "round": round_number, "stage": stage}
        for index, (agent, action, input_ref, round_number, stage) in enumerate(protocol)
    ]
    payload["visibility_relation"] = {
        str(round_number): [list(pair) for pair in sorted(pairs)]
        for round_number, pairs in visibility
    }
    payload["expected_model_calls"] = calls
    payload["expected_depth"] = depth
    return payload
