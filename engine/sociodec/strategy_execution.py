"""Visibility-enforcing execution kernel for formal social strategies.

The kernel executes an already specified SocialStrategy. It does not invent
strategy protocols, roles, visibility relations, or decision outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from sociodec.models.strategy import ProtocolStep, SocialStrategy


class StrategyExecutionError(RuntimeError):
    """Raised when a protocol cannot be executed without violating its contract."""


@dataclass(frozen=True, slots=True)
class StepContext:
    step: ProtocolStep
    input_text: str
    visible_outputs: Mapping[str, str]
    visible_author_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class StepRecord:
    output_id: str
    agent_id: str
    action: str
    round: int
    stage: int
    input_ref: str
    invokes_model: bool
    visible_output_ids: tuple[str, ...]
    output_text: str


@dataclass(frozen=True, slots=True)
class StrategyExecutionResult:
    strategy: SocialStrategy
    records: tuple[StepRecord, ...]

    @property
    def model_calls(self) -> int:
        return sum(record.invokes_model for record in self.records)

    @property
    def depth(self) -> int:
        return len({record.stage for record in self.records})

    @property
    def outputs(self) -> Mapping[str, str]:
        return {record.output_id: record.output_text for record in self.records}


StepExecutor = Callable[[StepContext], str]


def _output_id(step: ProtocolStep) -> str:
    return f"r{step.round}:s{step.stage}:{step.agent_id}:{step.action.value}"


def _resolve_input(
    input_ref: str,
    prompt_text: str,
    prior_outputs: Mapping[str, StepRecord],
    visible_author_ids: frozenset[str],
) -> str:
    if input_ref == "prompt":
        return prompt_text
    if not input_ref.startswith("output:"):
        raise StrategyExecutionError(
            "input_ref must be 'prompt' or 'output:<output_id>'"
        )
    output_id = input_ref.removeprefix("output:")
    record = prior_outputs.get(output_id)
    if record is None:
        raise StrategyExecutionError(f"input_ref points to unavailable output: {output_id}")
    if record.agent_id not in visible_author_ids:
        raise StrategyExecutionError(
            f"visibility violation: agent cannot read output authored by {record.agent_id}"
        )
    return record.output_text


def execute_strategy(
    strategy: SocialStrategy,
    prompt_text: str,
    *,
    model_executor: StepExecutor,
    local_executor: StepExecutor | None = None,
) -> StrategyExecutionResult:
    """Execute a formal protocol in deterministic stage barriers.

    All steps in a stage observe only outputs committed by earlier stages.
    Thus one step cannot observe a peer's output from the same parallel stage.
    Visibility is checked against the observer's relation for that round.
    Non-model steps require an explicit local executor and do not increment
    the model-call count.
    """
    if not prompt_text.strip():
        raise ValueError("prompt_text must not be empty")
    if not callable(model_executor):
        raise TypeError("model_executor must be callable")
    if local_executor is not None and not callable(local_executor):
        raise TypeError("local_executor must be callable")

    visibility_by_round = {
        item.round: frozenset(item.visible_pairs) for item in strategy.visibility
    }
    assignments = {(item.agent_id, item.round): item.role for item in strategy.assignments}
    records: list[StepRecord] = []
    committed: dict[str, StepRecord] = {}

    stages = sorted({(step.round, step.stage) for step in strategy.protocol})
    for round_number, stage_number in stages:
        stage_steps = [
            step for step in strategy.protocol
            if step.round == round_number and step.stage == stage_number
        ]
        # Snapshot before executing this stage: same-stage outputs are hidden.
        stage_snapshot = dict(committed)
        pending: list[StepRecord] = []

        for step in stage_steps:
            observer_role = assignments.get((step.agent_id, step.round))
            if observer_role is None:
                raise StrategyExecutionError("protocol step has no role assignment")
            visible_authors = frozenset(
                author for observer, author in visibility_by_round[round_number]
                if observer == step.agent_id
            )
            visible_records = {
                output_id: record.output_text
                for output_id, record in stage_snapshot.items()
                if record.agent_id in visible_authors
            }
            input_text = _resolve_input(
                step.input_ref, prompt_text, stage_snapshot, visible_authors,
            )
            context = StepContext(
                step=step,
                input_text=input_text,
                visible_outputs=visible_records,
                visible_author_ids=visible_authors,
            )
            if step.invokes_model:
                output_text = model_executor(context)
            else:
                if local_executor is None:
                    raise StrategyExecutionError(
                        "non-model protocol step requires local_executor"
                    )
                output_text = local_executor(context)
            if not isinstance(output_text, str) or not output_text.strip():
                raise StrategyExecutionError("step executor must return non-empty text")
            output_id = _output_id(step)
            if output_id in stage_snapshot or any(x.output_id == output_id for x in pending):
                raise StrategyExecutionError(f"duplicate protocol output identity: {output_id}")
            pending.append(StepRecord(
                output_id=output_id,
                agent_id=step.agent_id,
                action=step.action.value,
                round=step.round,
                stage=step.stage,
                input_ref=step.input_ref,
                invokes_model=step.invokes_model,
                visible_output_ids=tuple(sorted(visible_records)),
                output_text=output_text,
            ))

        for record in pending:
            committed[record.output_id] = record
            records.append(record)

    result = StrategyExecutionResult(strategy=strategy, records=tuple(records))
    if result.model_calls != strategy.calls:
        raise StrategyExecutionError(
            f"model call accounting mismatch: trace={result.model_calls}, "
            f"strategy={strategy.calls}"
        )
    if result.depth != strategy.depth:
        raise StrategyExecutionError(
            f"depth accounting mismatch: trace={result.depth}, strategy={strategy.depth}"
        )
    return result
