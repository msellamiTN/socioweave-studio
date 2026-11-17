"""Visibility-aware protocol runtime for a SocialStrategy.

This is the orchestration realisation of Definition 10 and Algorithm 1's
protocol loop. Calls are delegated to an injected invoker; this module never
selects a provider or changes the strategy's declared decision rule.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

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

    @property
    def output_refs(self) -> dict[str, str]:
        return {f"step:{item.step_index}": item.text for item in self.outputs}


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

    for stage in stages:
        stage_snapshot = tuple(outputs)
        stage_outputs: list[ProtocolOutput] = []
        for index, step in enumerate(strategy.protocol):
            if step.stage != stage:
                continue
            agent = known_agents[step.agent_id]
            prompt_view = views.get(step.agent_id, prompt.text)
            if step.input_ref == "prompt":
                input_content = prompt_view
            elif step.input_ref == "all_previous_outputs":
                visibility_round = next(item for item in strategy.visibility if item.round == step.round)
                visible_authors = {author for observer, author in visibility_round.visible_pairs if observer == step.agent_id}
                input_content = "\\n\\n".join(
                    f"[{item.agent_id}:{item.action}]\\n{item.text}"
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

    return StrategyRun(
        strategy_id=strategy_id,
        outputs=tuple(sorted(outputs, key=lambda item: item.step_index)),
        calls_made=calls_made,
        depth_executed=len(stages),
        seeded_agents=tuple(sorted(seeded_agents)),
    )
