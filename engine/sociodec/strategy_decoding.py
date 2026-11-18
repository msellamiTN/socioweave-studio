"""Resolve typed protocol messages into strategy-specific decision operators.

This layer consumes only decoded, typed outputs. It does not infer a judge's
choice, mediator's compromise, or synthesizer's content from free text.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from sociodec.catalogue import StrategyId
from sociodec.decisions import (
    Candidate, DecisionResult, authority, compromise, consensus_medoid,
    majority, rank_sum, subproblem_signature, synthesis, union,
)
from sociodec.extraction import AggregatedExtraction
from sociodec.models.decomposition import Decomposition
from sociodec.models.prompt import Prompt
from sociodec.protocol_decoding import (
    ProtocolDecodeError, ProtocolMessage, parse_protocol_output,
)
from sociodec.runtime import StrategyRun
from sociodec.validation import HypothesisVerdict


class StrategyDecisionError(ValueError):
    """Protocol evidence is insufficient or inconsistent for its decision rule."""


@dataclass(frozen=True, slots=True)
class DecisionAdjudication:
    """Explicit evidence for decisions not fully represented by protocol outputs.

    S11 needs the mediator's negotiated decomposition; S13's final authority
    choice is not encoded in its last critique step. These must be supplied,
    never guessed from a critique or summary.
    """
    selected_candidate_id: str | None = None
    negotiated_decomposition: Decomposition | None = None
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class StrategyDecision:
    decision: DecisionResult
    hypothesis_verdicts: tuple[HypothesisVerdict, ...]
    candidate_support_counts: tuple[tuple[tuple[str, str], int], ...]
    messages: tuple[ProtocolMessage, ...]


def _latest_candidates(messages: tuple[tuple[str, ProtocolMessage], ...]) -> dict[str, Candidate]:
    latest: dict[str, Candidate] = {}
    for agent_id, message in messages:
        if message.candidate is not None:
            latest[agent_id] = Candidate(agent_id, message.candidate.decomposition)
    return latest


def _required_candidates(pool: Mapping[str, Candidate], agent_ids: tuple[str, ...]) -> tuple[Candidate, ...]:
    missing = [agent for agent in agent_ids if agent not in pool]
    if missing:
        raise StrategyDecisionError("Missing candidate output(s) from: " + ", ".join(missing))
    return tuple(pool[agent] for agent in agent_ids)


def _judge_message(messages: tuple[tuple[str, ProtocolMessage], ...], judge_id: str) -> ProtocolMessage:
    matches = [message for agent, message in messages if agent == judge_id and message.action == "judge"]
    if len(matches) != 1 or matches[0].selected_candidate_id is None:
        raise StrategyDecisionError(f"Expected exactly one explicit judge selection from {judge_id}")
    return matches[0]


def _support_counts(candidates: tuple[Candidate, ...]) -> tuple[tuple[tuple[str, str], int], ...]:
    counts: dict[tuple[str, str], int] = {}
    for candidate in candidates:
        d = candidate.decomposition
        for source, target in d.E:
            edge = (source, target)
            counts[edge] = counts.get(edge, 0) + 1
    return tuple(sorted(counts.items()))


class ProtocolDecisionDecoder:
    """Callable StrategyDecoder implementation for all thirteen strategies."""

    def __init__(
        self,
        prompt: Prompt,
        extraction: AggregatedExtraction,
        *,
        adjudications: Mapping[StrategyId | str, DecisionAdjudication] | None = None,
    ) -> None:
        self.prompt = prompt
        self.extraction = extraction
        self.adjudications = {
            StrategyId(key): value for key, value in (adjudications or {}).items()
        }

    def __call__(self, strategy_id: StrategyId, run: StrategyRun):
        from sociodec.strategy_adapter import DecodedStrategyResult

        decoded: list[tuple[str, ProtocolMessage]] = []
        verdicts_by_hypothesis = {}
        for output in run.outputs:
            message = parse_protocol_output(
                output, prompt=self.prompt, extraction=self.extraction,
                candidate_id=output.agent_id,
            )
            decoded.append((output.agent_id, message))
            for verdict in message.hypothesis_verdicts:
                prior = verdicts_by_hypothesis.get(verdict.hypothesis)
                if prior is not None and prior != verdict.verdict:
                    raise StrategyDecisionError(
                        f"Conflicting hypothesis verdicts for {verdict.hypothesis.statement!r}"
                    )
                verdicts_by_hypothesis[verdict.hypothesis] = verdict.verdict

        messages = tuple(decoded)
        pool = _latest_candidates(messages)
        candidates = tuple(pool[key] for key in sorted(pool))
        adjudication = self.adjudications.get(strategy_id)
        if strategy_id is StrategyId.S1:
            candidate = _required_candidates(pool, ("coordinator",))
            decision = authority(candidate, judge_id="coordinator",
                                 selected_candidate_id="coordinator",
                                 rationale="Coordinator checked the specialist decomposition.")
        elif strategy_id is StrategyId.S12:
            expert_ids = tuple(sorted(x for x in pool if x.startswith("expert-")))
            decision = union(_required_candidates(pool, expert_ids))
        elif strategy_id is StrategyId.S2:
            participant_ids = tuple(sorted(x for x in pool if x.startswith("participant-")))
            decision = union(_required_candidates(pool, participant_ids))
        elif strategy_id is StrategyId.S3:
            member_ids = tuple(sorted(x for x in pool if x.startswith("member-")))
            selected = _required_candidates(pool, member_ids)
            rankings = {
                agent: message.ranking for agent, message in messages
                if agent in member_ids and message.action == "rank"
            }
            decision = rank_sum(selected, rankings)
        elif strategy_id is StrategyId.S4:
            experts = tuple(sorted(x for x in pool if x.startswith("expert-")))
            decision = consensus_medoid(_required_candidates(pool, experts))
        elif strategy_id is StrategyId.S9:
            voter_ids = tuple(sorted(x for x in pool if x.startswith("voter-")))
            selected = _required_candidates(pool, voter_ids)
            by_candidate = {candidate.identifier: candidate for candidate in selected}
            ballots = {}
            for agent, message in messages:
                if agent not in voter_ids or message.action != "vote":
                    continue
                signatures = set()
                for candidate_id, subproblem_id in message.endorsed_subproblems:
                    candidate = by_candidate.get(candidate_id)
                    if candidate is None:
                        raise StrategyDecisionError(f"Ballot references unknown candidate {candidate_id!r}")
                    item = next((x for x in candidate.decomposition.subproblems
                                 if x.identifier == subproblem_id), None)
                    if item is None:
                        raise StrategyDecisionError(
                            f"Ballot references unknown subproblem {subproblem_id!r} in {candidate_id!r}"
                        )
                    signatures.add(subproblem_signature(item))
                ballots[agent] = frozenset(signatures)
            decision = majority(selected, ballots)
        elif strategy_id is StrategyId.S5:
            selected = _required_candidates(pool, ("author",))
            judge = _judge_message(messages, "judge")
            decision = authority(selected, judge_id="judge",
                                 selected_candidate_id=judge.selected_candidate_id,
                                 rationale=judge.rationale)
        elif strategy_id is StrategyId.S6:
            selected = _required_candidates(pool, ("decomposer-1", "decomposer-2"))
            synthesized = [message.candidate for agent, message in messages
                           if agent == "synthesizer" and message.candidate is not None]
            if len(synthesized) != 1:
                raise StrategyDecisionError("S6 requires exactly one typed synthesizer decomposition")
            decision = synthesis(selected, synthesized[0].decomposition,
                                 synthesizer_id="synthesizer",
                                 rationale="Typed synthesis output.")
        elif strategy_id is StrategyId.S7:
            selected = _required_candidates(pool, ("party-1", "party-2"))
            judge = _judge_message(messages, "judge")
            decision = authority(selected, judge_id="judge",
                                 selected_candidate_id=judge.selected_candidate_id,
                                 rationale=judge.rationale)
        elif strategy_id is StrategyId.S8:
            author_drafts = [
                message.candidate for agent, message in messages
                if agent == "author" and message.action == "draft" and message.candidate is not None
            ]
            author_revisions = [
                message.candidate for agent, message in messages
                if agent == "author" and message.action == "revise" and message.candidate is not None
            ]
            editor_messages = [
                message for agent, message in messages
                if agent == "editor" and message.action == "judge"
            ]
            if len(author_drafts) != 1 or len(editor_messages) != 1:
                raise StrategyDecisionError("S8 requires exactly one original author draft and editor verdict")
            editor = editor_messages[0]
            if editor.peer_review_verdict is None:
                raise StrategyDecisionError("S8 editor verdict must be typed accept/revise")
            if editor.peer_review_verdict.value == "accept":
                if author_revisions:
                    raise StrategyDecisionError("S8 ACCEPT branch must not contain an author revision")
                chosen = Candidate("author", author_drafts[0].decomposition)
                rationale = f"Editor ACCEPT: {editor.rationale}"
            else:
                if len(author_revisions) != 1:
                    raise StrategyDecisionError("S8 REVISE verdict requires exactly one author D1 revision")
                chosen = Candidate("author", author_revisions[0].decomposition)
                rationale = f"Editor REVISE: {editor.rationale}"
            decision = authority((chosen,), judge_id="editor",
                                selected_candidate_id="author", rationale=rationale)
        elif strategy_id is StrategyId.S10:
            participant_ids = tuple(sorted(x for x in pool if x.startswith("participant-")))
            selected = _required_candidates(pool, participant_ids)
            moderator = _judge_message(messages, "moderator")
            candidate_id = moderator.selected_candidate_id
            if candidate_id not in {item.identifier for item in selected}:
                raise StrategyDecisionError("Moderator selected a candidate outside the deliberation pool")
            decision = DecisionResult(
                next(item.decomposition for item in selected if item.identifier == candidate_id),
                "consensus", candidate_id, f"Moderator: {moderator.rationale}",
            )
        elif strategy_id in {StrategyId.S11, StrategyId.S13}:
            if adjudication is None or not adjudication.rationale.strip():
                raise StrategyDecisionError(
                    f"{strategy_id.value} requires explicit external decision adjudication; "
                    "the protocol outputs do not contain a negotiated/final selection"
                )
            if strategy_id is StrategyId.S11:
                selected = _required_candidates(pool, ("party-1", "party-2"))
                if adjudication.negotiated_decomposition is None:
                    raise StrategyDecisionError("S11 adjudication must supply negotiated_decomposition")
                decision = compromise(
                    selected, adjudication.negotiated_decomposition,
                    mediator_id="mediator", rationale=adjudication.rationale,
                )
            else:
                selected = tuple(pool.values())
                if adjudication.selected_candidate_id is None:
                    raise StrategyDecisionError("S13 adjudication must select a candidate explicitly")
                decision = authority(
                    selected, judge_id="agent-A",
                    selected_candidate_id=adjudication.selected_candidate_id,
                    rationale=adjudication.rationale,
                )
        else:
            raise StrategyDecisionError(f"No decision assembly for {strategy_id.value}")

        return DecodedStrategyResult(
            decision=decision,
            hypothesis_verdicts=tuple(
                HypothesisVerdict(hypothesis, verdict)
                for hypothesis, verdict in verdicts_by_hypothesis.items()
            ),
            candidate_support_counts=_support_counts(candidates),
        )
