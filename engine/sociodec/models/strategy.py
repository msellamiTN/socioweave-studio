"""Formal social strategy model from Definitions 9 and 10.

The model records agents, role assignments, visibility, protocol steps and
decision rule. It does not execute a strategy or choose one for a prompt.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    DECOMPOSER = "decomposer"
    CRITIC = "critic"
    DEFENDER = "defender"
    JUDGE = "judge"
    COORDINATOR = "coordinator"
    AGGREGATOR = "aggregator"
    FACILITATOR = "facilitator"
    MEDIATOR = "mediator"
    MODERATOR = "moderator"
    VOTER = "voter"


class Action(StrEnum):
    SPLIT = "split"
    DRAFT = "draft"
    COUNTER_PLAN = "counter-plan"
    CRITIQUE = "critique"
    DEFEND = "defend"
    REVISE = "revise"
    RANK = "rank"
    VOTE = "vote"
    SUMMARISE = "summarise"
    COMPARE = "compare"
    MERGE = "merge"
    JUDGE = "judge"
    CHECK = "check"


class DecisionRule(StrEnum):
    AUTHORITY = "authority"
    RANK_SUM = "rank-sum"
    MAJORITY = "majority"
    UNION = "union"
    SYNTHESIS = "synthesis"
    COMPROMISE = "compromise"
    CONSENSUS = "consensus"


@dataclass(frozen=True, slots=True)
class Agent:
    """a=(m_a,c_a,mu_a): model, context description and optional memory."""
    identifier: str
    model_id: str
    context: str
    memory: str | None = None

    def __post_init__(self) -> None:
        if not self.identifier.strip():
            raise ValueError("Agent.identifier must not be empty")
        if not self.model_id.strip():
            raise ValueError("Agent.model_id must not be empty")
        if not self.context.strip():
            raise ValueError("Agent.context must not be empty")


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    agent_id: str
    round: int
    role: Role

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            raise ValueError("RoleAssignment.agent_id must not be empty")
        if self.round < 1:
            raise ValueError("RoleAssignment.round must be >= 1")
        if not isinstance(self.role, Role):
            raise ValueError("RoleAssignment.role must be a defined Role")


@dataclass(frozen=True, slots=True)
class VisibilityRound:
    """V_t contains (observer, author) pairs visible to the observer."""
    round: int
    visible_pairs: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if self.round < 1:
            raise ValueError("VisibilityRound.round must be >= 1")
        if len(set(self.visible_pairs)) != len(self.visible_pairs):
            raise ValueError("VisibilityRound.visible_pairs must be unique")
        for pair in self.visible_pairs:
            if len(pair) != 2 or not all(item.strip() for item in pair):
                raise ValueError("Visibility pairs must contain two non-empty agent identifiers")


@dataclass(frozen=True, slots=True)
class ProtocolStep:
    """pi_l=(agent, action, input), with round/stage and call accounting."""
    agent_id: str
    action: Action
    input_ref: str
    round: int
    stage: int
    invokes_model: bool = True

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            raise ValueError("ProtocolStep.agent_id must not be empty")
        if not isinstance(self.action, Action):
            raise ValueError("ProtocolStep.action must be a defined Action")
        if not self.input_ref.strip():
            raise ValueError("ProtocolStep.input_ref must not be empty")
        if self.round < 1:
            raise ValueError("ProtocolStep.round must be >= 1")
        if self.stage < 1:
            raise ValueError("ProtocolStep.stage must be >= 1")
        if not isinstance(self.invokes_model, bool):
            raise ValueError("ProtocolStep.invokes_model must be a boolean")


@dataclass(frozen=True, slots=True)
class SocialStrategy:
    """sigma=(A,R,alpha,V,pi,omega) with explicit anonymity flag eta."""
    agents: tuple[Agent, ...]
    roles: tuple[Role, ...]
    assignments: tuple[RoleAssignment, ...]
    visibility: tuple[VisibilityRound, ...]
    protocol: tuple[ProtocolStep, ...]
    decision_rule: DecisionRule
    rounds: int
    anonymous: bool = False

    def __post_init__(self) -> None:
        if self.rounds < 1:
            raise ValueError("SocialStrategy.rounds must be >= 1")
        if not isinstance(self.decision_rule, DecisionRule):
            raise ValueError("decision_rule must be a defined DecisionRule")
        if not isinstance(self.anonymous, bool):
            raise ValueError("anonymous must be a boolean")

        agent_ids = [agent.identifier for agent in self.agents]
        if not agent_ids or len(agent_ids) != len(set(agent_ids)):
            raise ValueError("SocialStrategy requires unique, non-empty agent set")
        if (
            not self.roles
            or any(not isinstance(role, Role) for role in self.roles)
            or len(set(self.roles)) != len(self.roles)
        ):
            raise ValueError("SocialStrategy.roles must be defined, non-empty and unique")

        known_agents = set(agent_ids)
        assignment_keys = [(item.agent_id, item.round) for item in self.assignments]
        if len(assignment_keys) != len(set(assignment_keys)):
            raise ValueError("Role assignments must be unique per agent and round")
        expected_keys = {
            (agent_id, round_number)
            for agent_id in known_agents
            for round_number in range(1, self.rounds + 1)
        }
        if set(assignment_keys) != expected_keys:
            raise ValueError("Role assignment alpha must cover every agent in every round")
        for assignment in self.assignments:
            if assignment.agent_id not in known_agents:
                raise ValueError(f"Role assignment references unknown agent: {assignment.agent_id}")
            if assignment.round > self.rounds:
                raise ValueError("Role assignment round exceeds strategy rounds")
            if assignment.role not in self.roles:
                raise ValueError("Role assignment uses a role outside R")

        visibility_rounds = [item.round for item in self.visibility]
        if sorted(visibility_rounds) != list(range(1, self.rounds + 1)):
            raise ValueError("Visibility V must define exactly one relation for each round")
        for item in self.visibility:
            for observer, author in item.visible_pairs:
                if observer not in known_agents or author not in known_agents:
                    raise ValueError("Visibility relation references an unknown agent")
            visible = set(item.visible_pairs)
            for agent_id in known_agents:
                if (agent_id, agent_id) not in visible:
                    raise ValueError("Every agent must see its own outputs in every round")

        if not self.protocol:
            raise ValueError("SocialStrategy.protocol must not be empty")
        stages = {step.stage for step in self.protocol}
        if stages != set(range(1, max(stages) + 1)):
            raise ValueError("Protocol stages must be contiguous from 1")
        ordered_pairs = [(step.round, step.stage) for step in self.protocol]
        if ordered_pairs != sorted(ordered_pairs):
            raise ValueError("Protocol steps must be ordered by round and stage")
        stage_rounds: dict[int, int] = {}
        for step in self.protocol:
            previous_round = stage_rounds.setdefault(step.stage, step.round)
            if previous_round != step.round:
                raise ValueError("A protocol stage cannot span multiple rounds")
        for step in self.protocol:
            if step.agent_id not in known_agents:
                raise ValueError(f"Protocol step references unknown agent: {step.agent_id}")
            if step.round > self.rounds:
                raise ValueError("Protocol step round exceeds strategy rounds")
            if (step.agent_id, step.round) not in set(assignment_keys):
                raise ValueError("Protocol step agent has no role assignment in its round")

    @property
    def calls(self) -> int:
        """calls(sigma): number of protocol steps that invoke a model."""
        return sum(step.invokes_model for step in self.protocol)

    @property
    def depth(self) -> int:
        """depth(sigma): number of sequential protocol stages."""
        return len({step.stage for step in self.protocol})

    @property
    def homogeneous(self) -> bool:
        """True iff all agents share the same underlying model identity."""
        return len({agent.model_id for agent in self.agents}) == 1

    @property
    def independent_first_round(self) -> bool:
        """No agent sees another agent's output in round 1."""
        first = next(item for item in self.visibility if item.round == 1)
        return all(
            observer == author
            for observer, author in first.visible_pairs
        )

    @property
    def role_stable(self) -> bool:
        """True iff each agent retains one role across all rounds."""
        by_agent: dict[str, set[Role]] = {}
        for assignment in self.assignments:
            by_agent.setdefault(assignment.agent_id, set()).add(assignment.role)
        return all(len(roles) == 1 for roles in by_agent.values())
