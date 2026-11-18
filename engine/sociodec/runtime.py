"""Visibility-aware protocol runtime for a SocialStrategy.

This is the orchestration realisation of Definition 10 and Algorithm 1's
protocol loop. Calls are delegated to an injected invoker; this module never
selects a provider or changes the strategy's declared decision rule.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable, Mapping, Protocol

from sociodec.extraction import Hypothesis
from sociodec.models.prompt import Prompt
from sociodec.models.strategy import (
    Agent, ProtocolStep, Role, SocialStrategy,
)


@dataclass(frozen=True, slots=True)
class VisibleOutput:
    step_index: int
    author: str
    action: str
    text: str
    from_seed: bool


@dataclass(frozen=True, slots=True)
class ProtocolContext:
    prompt_view: str
    agent_context: str
    agent_id: str
    role: Role
    action: str
    input_ref: str
    input_content: str
    hypotheses: tuple[Hypothesis, ...]
    visible_history: tuple[VisibleOutput, ...]


@dataclass(frozen=True, slots=True)
class ProtocolOutput:
    step_index: int
    agent_id: str
    round: int
    stage: int
    action: str
    text: str
    model_invoked: bool
    from_seed: bool


@dataclass(frozen=True, slots=True)
class StrategyRun:
    strategy_id: str
    outputs: tuple[ProtocolOutput, ...]
    calls_made: int
    depth_executed: int
    seeded_agents: tuple[str, ...]
    expected_agent_ids: tuple[str, ...] | None = None
    scheduled_steps: int | None = None
    scheduled_depth: int | None = None

    @property
    def output_refs(self) -> dict[str, str]:
        return {f"step:{item.step_index}": item.text for item in self.outputs}

    @property
    def protocol_steps(self) -> int:
        """Number of protocol outputs actually produced, including skipped calls."""
        return len(self.outputs)

    @property
    def model_invocations(self) -> int:
        return sum(item.model_invoked for item in self.outputs)

    @property
    def seeded_steps(self) -> int:
        return sum(item.from_seed for item in self.outputs)

    @property
    def precomputed_steps(self) -> int:
        return sum(not item.model_invoked and not item.from_seed for item in self.outputs)

    @property
    def skipped_steps(self) -> int | None:
        if self.scheduled_steps is None:
            return None
        return self.scheduled_steps - self.protocol_steps

    @property
    def skipped_stages(self) -> int | None:
        if self.scheduled_depth is None:
            return None
        return self.scheduled_depth - self.depth_executed

    @property
    def accounting_reconciles(self) -> bool:
        if self.scheduled_steps is None or self.scheduled_depth is None:
            return False
        skipped = self.skipped_steps
        skipped_stages = self.skipped_stages
        return (
            skipped is not None and skipped >= 0
            and skipped_stages is not None and skipped_stages >= 0
            and self.protocol_steps + skipped == self.scheduled_steps
            and self.depth_executed + skipped_stages == self.scheduled_depth
            and self.protocol_steps
            == self.model_invocations + self.seeded_steps + self.precomputed_steps
            and self.calls_made == self.model_invocations
        )


class ProtocolInvoker(Protocol):
    def invoke(
        self,
        agent: Agent,
        step: ProtocolStep,
        context: ProtocolContext,
    ) -> str: ...


def _role_for(strategy: SocialStrategy, agent_id: str, round_number: int) -> Role:
    for assignment in strategy.assignments:
        if assignment.agent_id == agent_id and assignment.round == round_number:
            return assignment.role
    raise ValueError(f"No role assignment for {agent_id} in round {round_number}")


def _visible_history(
    strategy: SocialStrategy,
    observer_id: str,
    round_number: int,
    stage_history: tuple[ProtocolOutput, ...],
    same_stage_own_outputs: tuple[ProtocolOutput, ...],
) -> tuple[VisibleOutput, ...]:
    visibility = next(item for item in strategy.visibility if item.round == round_number)
    visible_authors = {
        author for observer, author in visibility.visible_pairs
        if observer == observer_id
    }
    selected = [
        item for item in stage_history
        if item.agent_id in visible_authors
    ]
    selected.extend(
        item for item in same_stage_own_outputs
        if item.agent_id == observer_id and item not in selected
    )
    selected.sort(key=lambda item: item.step_index)
    return tuple(
        VisibleOutput(
            step_index=item.step_index,
            author="anonymous" if strategy.anonymous else item.agent_id,
            action=item.action,
            text=item.text,
            from_seed=item.from_seed,
        )
        for item in selected
    )


def _s8_revision_required(outputs: list[ProtocolOutput]) -> bool:
    judges = [item for item in outputs if item.action == "judge"]
    if not judges:
        raise ValueError("S8 revision step requires a preceding editor verdict")
    try:
        payload = json.loads(judges[-1].text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid S8 editor verdict JSON") from exc
    if not isinstance(payload, dict) or payload.get("verdict") not in {"accept", "revise"}:
        raise ValueError("Invalid S8 editor verdict; expected accept or revise")
    return payload["verdict"] == "revise"

def run_strategy(
    strategy_id: str,
    prompt: Prompt,
    strategy: SocialStrategy,
    invoker: ProtocolInvoker,
    *,
    initial_inputs: Mapping[str, str] | None = None,
    prompt_views: Mapping[str, str] | None = None,
    hypotheses: tuple[Hypothesis, ...] = (),
    seeds: Mapping[str, str] | None = None,
    precomputed_outputs: Mapping[str, str] | None = None,
    delphi_epsilon: float | None = None,
    delphi_candidate_distance: Callable[[str, str], float] | None = None,
    consensus_epsilon: float | None = None,
    consensus_candidate_distance: Callable[[str, str], float] | None = None,
    mediation_epsilon: float | None = None,
    mediation_candidate_distance: Callable[[str, str], float] | None = None,
) -> StrategyRun:
    """Execute protocol steps with stage snapshots and per-agent visibility.

    Steps in the same stage share a history snapshot: an agent cannot observe
    another agent's output from a peer step in that same stage. Its own earlier
    output remains visible. The runtime dispatches steps serially for
    reproducibility; stage metadata preserves the paper's parallel-stage
    semantics and depth accounting.
    """
    if not strategy_id.strip():
        raise ValueError("strategy_id must not be empty")
    if strategy_id == "S4":
        if delphi_epsilon is not None and not 0.0 <= delphi_epsilon <= 1.0:
            raise ValueError("delphi_epsilon must be in [0, 1]")
        if delphi_epsilon is not None and delphi_candidate_distance is None:
            raise ValueError("delphi_candidate_distance is required when delphi_epsilon is set")
    elif delphi_epsilon is not None or delphi_candidate_distance is not None:
        raise ValueError("Delphi stopping options are valid only for S4")
    if strategy_id == "S10":
        if consensus_epsilon is not None and not 0.0 <= consensus_epsilon <= 1.0:
            raise ValueError("consensus_epsilon must be in [0, 1]")
        if consensus_epsilon is not None and consensus_candidate_distance is None:
            raise ValueError("consensus_candidate_distance is required when consensus_epsilon is set")
    elif consensus_epsilon is not None or consensus_candidate_distance is not None:
        raise ValueError("Consensus stopping options are valid only for S10")
    if strategy_id == "S11":
        if mediation_epsilon is not None and not 0.0 <= mediation_epsilon <= 1.0:
            raise ValueError("mediation_epsilon must be in [0, 1]")
        if mediation_epsilon is not None and mediation_candidate_distance is None:
            raise ValueError("mediation_candidate_distance is required when mediation_epsilon is set")
    elif mediation_epsilon is not None or mediation_candidate_distance is not None:
        raise ValueError("Mediation stopping options are valid only for S11")
    inputs = dict(initial_inputs or {})
    views = dict(prompt_views or {})
    seed_map = dict(seeds or {})
    fixed_outputs = dict(precomputed_outputs or {})
    known_agents = {agent.identifier: agent for agent in strategy.agents}

    unknown_seeds = set(seed_map) - set(known_agents)
    if unknown_seeds:
        raise ValueError("Seed supplied for unknown agent(s): " + ", ".join(sorted(unknown_seeds)))
    if any(not value.strip() for value in seed_map.values()):
        raise ValueError("Seeds must be non-empty")
    unknown_views = set(views) - set(known_agents)
    if unknown_views:
        raise ValueError("Prompt view supplied for unknown agent(s): " + ", ".join(sorted(unknown_views)))

    outputs: list[ProtocolOutput] = []
    seeded_agents: set[str] = set()
    calls_made = 0
    stages = sorted({step.stage for step in strategy.protocol})
    consensus_stopped_after: int | None = None
    mediation_stopped_after: int | None = None

    def canonical_candidate(record: ProtocolOutput) -> str:
        try:
            payload = json.loads(record.text)
        except (TypeError, json.JSONDecodeError):
            return record.text.strip()
        if isinstance(payload, dict):
            payload = payload.get("candidate", payload)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    for stage in stages:
        stage_snapshot = tuple(outputs)
        stage_outputs: list[ProtocolOutput] = []
        for index, step in enumerate(strategy.protocol):
            if step.stage != stage:
                continue
            # S10 stops participant turns after a completed stable round, but
            # retains the single final moderator closure step in the blueprint.
            if (strategy_id == "S10" and consensus_stopped_after is not None
                    and step.action.value != "judge" and step.round > consensus_stopped_after):
                continue
            if strategy_id == "S11" and mediation_stopped_after is not None and step.round > mediation_stopped_after:
                continue
            if strategy_id == "S8" and step.action.value == "revise":
                if not _s8_revision_required(outputs):
                    continue
            agent = known_agents[step.agent_id]
            prompt_view = views.get(step.agent_id, prompt.text)
            if step.input_ref == "prompt":
                input_content = prompt_view
            elif step.input_ref == "all_previous_outputs":
                visibility_round = next(item for item in strategy.visibility if item.round == step.round)
                visible_authors = {author for observer, author in visibility_round.visible_pairs if observer == step.agent_id}
                input_content = "\\n\\n".join(
                    f"[{('anonymous' if strategy.anonymous else item.agent_id)}:{item.action}]\\n{item.text}"
                    for item in stage_snapshot if item.agent_id in visible_authors
                )
                if not input_content:
                    input_content = inputs.get("all_previous_outputs", "")
            elif step.input_ref in inputs:
                input_content = inputs[step.input_ref]
            elif step.input_ref.startswith("step:"):
                prior = {
                    f"step:{item.step_index}": item.text
                    for item in stage_snapshot
                }
                if step.input_ref not in prior:
                    raise ValueError(
                        f"Protocol input {step.input_ref!r} is not available before stage {stage}"
                    )
                referenced = next(item for item in stage_snapshot if f"step:{item.step_index}" == step.input_ref)
                visibility_round = next(item for item in strategy.visibility if item.round == step.round)
                if (step.agent_id, referenced.agent_id) not in visibility_round.visible_pairs:
                    raise ValueError("Protocol input is not visible to the acting agent")
                input_content = prior[step.input_ref]
            else:
                raise ValueError(f"Unknown protocol input reference: {step.input_ref}")

            role = _role_for(strategy, step.agent_id, step.round)
            same_stage_own = tuple(
                item for item in stage_outputs if item.agent_id == step.agent_id
            )
            history = _visible_history(
                strategy, step.agent_id, step.round,
                stage_snapshot, same_stage_own,
            )
            context = ProtocolContext(
                prompt_view=prompt_view,
                agent_context=agent.context,
                agent_id=agent.identifier,
                role=role,
                action=step.action.value,
                input_ref=step.input_ref,
                input_content=input_content,
                hypotheses=hypotheses,
                visible_history=history,
            )

            from_seed = (
                step.action.value == "draft"
                and step.round == 1
                and step.agent_id in seed_map
                and step.agent_id not in seeded_agents
            )
            if from_seed:
                text = seed_map[step.agent_id]
                seeded_agents.add(step.agent_id)
                model_invoked = False
            elif step.invokes_model:
                text = invoker.invoke(agent, step, context)
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("Protocol invoker must return non-empty text")
                calls_made += 1
                model_invoked = True
            else:
                output_ref = f"step:{index}"
                if output_ref not in fixed_outputs:
                    raise ValueError(
                        f"Non-model protocol step requires precomputed output {output_ref}"
                    )
                text = fixed_outputs[output_ref]
                if not text.strip():
                    raise ValueError("Precomputed protocol output must not be empty")
                model_invoked = False

            record = ProtocolOutput(
                step_index=index,
                agent_id=step.agent_id,
                round=step.round,
                stage=step.stage,
                action=step.action.value,
                text=text,
                model_invoked=model_invoked,
                from_seed=from_seed,
            )
            stage_outputs.append(record)
        outputs.extend(stage_outputs)

        # Consensus stopping is evaluated only after the final sequential
        # participant turn in a complete round. Compare the shared state left
        # by the last participant with the preceding round's final state.
        if strategy_id == "S10" and stage_outputs:
            executed_round = stage_outputs[-1].round
            round_steps = [step for step in strategy.protocol
                           if step.round == executed_round and step.action.value != "judge"]
            if stage == max(step.stage for step in round_steps) and executed_round > 1:
                participants = tuple(agent.identifier for agent in strategy.agents
                                     if agent.identifier.startswith("participant-"))
                prior_round = [item for item in outputs
                               if item.round == executed_round - 1 and item.agent_id in participants]
                current_round = [item for item in outputs
                                 if item.round == executed_round and item.agent_id in participants]
                if len(prior_round) != len(participants) or len(current_round) != len(participants):
                    raise ValueError(
                        "S10 convergence requires one completed shared-draft turn per participant "
                        f"in adjacent rounds (participants={participants}, "
                        f"prior={[item.agent_id for item in prior_round]}, "
                        f"current={[item.agent_id for item in current_round]}, "
                        f"round={executed_round}, stage={stage})"
                    )
                previous = canonical_candidate(max(prior_round, key=lambda item: item.step_index))
                current = canonical_candidate(max(current_round, key=lambda item: item.step_index))
                unchanged = previous == current
                within_epsilon = False
                if consensus_epsilon is not None:
                    distance = consensus_candidate_distance(previous, current)
                    if not isinstance(distance, (int, float)) or not 0.0 <= distance <= 1.0:
                        raise ValueError("Consensus candidate distance must return a value in [0, 1]")
                    within_epsilon = distance <= consensus_epsilon
                if unchanged or within_epsilon:
                    consensus_stopped_after = executed_round

        # Mediation compares the two parties' revised drafts at the end of
        # each complete round. The mediator facilitates; it never selects a
        # winner or manufactures the negotiated joint decomposition.
        if strategy_id == "S11" and stage_outputs:
            round_number = next(step.round for step in strategy.protocol if step.stage == stage)
            round_stages = [step.stage for step in strategy.protocol if step.round == round_number]
            if stage == max(round_stages):
                revisions = {
                    agent_id: [item for item in outputs
                               if item.round == round_number and item.agent_id == agent_id
                               and item.action == "revise"]
                    for agent_id in ("party-1", "party-2")
                }
                if any(len(items) != 1 for items in revisions.values()):
                    raise ValueError("S11 convergence requires exactly one revision from each party per completed round")
                left = canonical_candidate(revisions["party-1"][0])
                right = canonical_candidate(revisions["party-2"][0])
                agreed = left == right
                within_epsilon = False
                if mediation_epsilon is not None:
                    distance = mediation_candidate_distance(left, right)
                    if not isinstance(distance, (int, float)) or not 0.0 <= distance <= 1.0:
                        raise ValueError("Mediation candidate distance must return a value in [0, 1]")
                    within_epsilon = distance <= mediation_epsilon
                if agreed or within_epsilon:
                    mediation_stopped_after = round_number

        # Delphi stopping is evaluated only after the facilitator has completed
        # the round. Each expert is compared with their own previous draft.
        if strategy_id == "S4":
            round_number = next(step.round for step in strategy.protocol if step.stage == stage)
            round_stages = [step.stage for step in strategy.protocol if step.round == round_number]
            if stage == max(round_stages) and round_number > 1:
                def candidate_payload(record: ProtocolOutput) -> str:
                    try:
                        payload = json.loads(record.text)
                    except json.JSONDecodeError:
                        # The orchestration layer also supports non-JSON invokers.
                        # Exact textual stability remains observable; epsilon-based
                        # structural distance requires the caller-supplied evaluator.
                        return record.text.strip()
                    if not isinstance(payload, dict):
                        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
                    candidate = payload.get("candidate", payload)
                    return json.dumps(candidate, sort_keys=True, separators=(",", ":"))

                experts = tuple(agent.identifier for agent in strategy.agents
                                if agent.identifier.startswith("expert-"))
                previous = {}
                current = {}
                for expert in experts:
                    history = [item for item in outputs if item.agent_id == expert
                               and item.action in {"draft", "revise"}
                               and item.round in {round_number - 1, round_number}]
                    prior = [item for item in history if item.round == round_number - 1]
                    latest = [item for item in history if item.round == round_number]
                    if len(prior) != 1 or len(latest) != 1:
                        raise ValueError(f"S4 convergence requires one draft per expert in rounds {round_number - 1} and {round_number}")
                    previous[expert] = candidate_payload(prior[0])
                    current[expert] = candidate_payload(latest[0])

                unchanged = all(previous[expert] == current[expert] for expert in experts)
                within_epsilon = False
                if delphi_epsilon is not None:
                    distances = [delphi_candidate_distance(previous[expert], current[expert])
                                 for expert in experts]
                    if any(not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0
                           for value in distances):
                        raise ValueError("Delphi candidate distance must return values in [0, 1]")
                    within_epsilon = max(distances) <= delphi_epsilon
                if unchanged or within_epsilon:
                    break

    return StrategyRun(
        strategy_id=strategy_id,
        outputs=tuple(sorted(outputs, key=lambda item: item.step_index)),
        calls_made=calls_made,
        depth_executed=len({item.stage for item in outputs}),
        seeded_agents=tuple(sorted(seeded_agents)),
        expected_agent_ids=tuple(agent.identifier for agent in strategy.agents),
        scheduled_steps=len(strategy.protocol),
        scheduled_depth=len(stages),
    )
