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
            expected_members = (
                {agent_id for agent_id in run.expected_agent_ids
                 if agent_id.startswith("member-")}
                if run.expected_agent_ids is not None else None
            )
            member_ids = tuple(sorted(
                expected_members if expected_members is not None
                else (agent_id for agent_id in pool if agent_id.startswith("member-"))
            ))
            if not member_ids:
                raise StrategyDecisionError("S3 requires at least one configured member")

            draft_messages = [
                (agent, message) for agent, message in messages
                if message.action == "draft" and message.candidate is not None
            ]
            draft_ids = [agent for agent, _ in draft_messages]
            if len(draft_ids) != len(set(draft_ids)):
                raise StrategyDecisionError("S3 requires exactly one candidate draft per member; duplicate draft")
            observed_drafters = set(draft_ids)
            if observed_drafters != set(member_ids):
                missing = sorted(set(member_ids) - observed_drafters)
                unexpected = sorted(observed_drafters - set(member_ids))
                details = []
                if missing:
                    details.append("missing drafts: " + ", ".join(missing))
                if unexpected:
                    details.append("unexpected drafts: " + ", ".join(unexpected))
                raise StrategyDecisionError(
                    "S3 candidate drafts do not match expected member roster ("
                    + "; ".join(details) + ")"
                )

            selected = _required_candidates(pool, member_ids)
            ranking_messages = [
                (agent, message) for agent, message in messages
                if message.action == "rank"
            ]
            ranking_ids = [agent for agent, _ in ranking_messages]
            if any(agent not in member_ids for agent in ranking_ids):
                unexpected = sorted(set(ranking_ids) - set(member_ids))
                raise StrategyDecisionError(
                    "S3 received rankings from non-member(s): " + ", ".join(unexpected)
                )
            if len(ranking_ids) != len(set(ranking_ids)):
                raise StrategyDecisionError("S3 requires exactly one ranking per member; duplicate ranking")
            missing_rankings = sorted(set(member_ids) - set(ranking_ids))
            if missing_rankings:
                raise StrategyDecisionError(
                    "S3 requires exactly one ranking per member; missing: "
                    + ", ".join(missing_rankings)
                )
            rankings = {agent: message.ranking for agent, message in ranking_messages}
            try:
                decision = rank_sum(selected, rankings)
            except ValueError as exc:
                raise StrategyDecisionError(f"S3 invalid ranking evidence: {exc}") from exc
        elif strategy_id is StrategyId.S4:
            expected_experts = (
                {agent_id for agent_id in run.expected_agent_ids
                 if agent_id.startswith("expert-")}
                if run.expected_agent_ids is not None else None
            )
            observed_experts = {
                agent for agent, message in messages
                if message.action in {"draft", "revise"} and message.candidate is not None
                and agent.startswith("expert-")
            }
            experts_set = expected_experts if expected_experts is not None else observed_experts
            experts = tuple(sorted(experts_set))
            if not experts:
                raise StrategyDecisionError("S4 requires at least one configured expert")

            # Validate the complete Delphi trace round by round. Each round has
            # one draft/revision from every expert and one anonymous facilitator
            # summary; only the final round's drafts enter the medoid operator.
            round_numbers = sorted({output.round for output in run.outputs})
            if not round_numbers or round_numbers != list(range(1, max(round_numbers) + 1)):
                raise StrategyDecisionError("S4 rounds must be contiguous from round 1")
            final_round = max(round_numbers)
            final_candidates: dict[str, Candidate] = {}
            for round_number in round_numbers:
                round_outputs = [
                    (output, message)
                    for output, (_, message) in zip(run.outputs, messages)
                    if output.round == round_number
                ]
                expected_action = "draft" if round_number == 1 else "revise"
                expert_messages = [
                    (output, message) for output, message in round_outputs
                    if output.agent_id.startswith("expert-")
                    and output.action in {"draft", "revise"}
                ]
                observed_ids = [output.agent_id for output, _ in expert_messages]
                if len(observed_ids) != len(set(observed_ids)):
                    raise StrategyDecisionError(
                        f"S4 round {round_number} contains duplicate expert drafts"
                    )
                if set(observed_ids) != set(experts):
                    missing = sorted(set(experts) - set(observed_ids))
                    unexpected = sorted(set(observed_ids) - set(experts))
                    raise StrategyDecisionError(
                        f"S4 round {round_number} expert roster mismatch; "
                        f"missing={missing}, unexpected={unexpected}"
                    )
                wrong_actions = [
                    output.agent_id for output, _ in expert_messages
                    if output.action != expected_action
                ]
                if wrong_actions:
                    raise StrategyDecisionError(
                        f"S4 round {round_number} requires {expected_action} from every expert"
                    )
                facilitator_summaries = [
                    message for output, message in round_outputs
                    if output.agent_id == "facilitator" and output.action == "summarise"
                ]
                if len(facilitator_summaries) != 1:
                    raise StrategyDecisionError(
                        f"S4 round {round_number} requires exactly one facilitator summary"
                    )
                if round_number == final_round:
                    final_candidates = {
                        output.agent_id: message.candidate
                        for output, message in expert_messages
                        if message.candidate is not None
                    }
            if len(final_candidates) != len(experts):
                raise StrategyDecisionError("S4 final round is missing an expert candidate")
            decision = consensus_medoid(
                tuple(final_candidates[expert] for expert in experts)
            )
        elif strategy_id is StrategyId.S9:
            expected_voters = (
                {agent_id for agent_id in run.expected_agent_ids
                 if agent_id.startswith("voter-")}
                if run.expected_agent_ids is not None else None
            )
            voter_ids = tuple(sorted(
                expected_voters if expected_voters is not None
                else (x for x in pool if x.startswith("voter-"))
            ))
            if not voter_ids:
                raise StrategyDecisionError("S9 requires at least one configured voter")
            if expected_voters is not None:
                observed_drafters = {
                    agent for agent, message in messages
                    if message.action == "draft" and message.candidate is not None
                }
                if observed_drafters != expected_voters:
                    missing = sorted(expected_voters - observed_drafters)
                    unexpected = sorted(observed_drafters - expected_voters)
                    details = []
                    if missing:
                        details.append("missing drafts: " + ", ".join(missing))
                    if unexpected:
                        details.append("unexpected drafts: " + ", ".join(unexpected))
                    raise StrategyDecisionError(
                        "S9 candidate drafts do not match expected voter roster ("
                        + "; ".join(details) + ")"
                    )
            selected = _required_candidates(pool, voter_ids)
            vote_messages = [
                (agent, message) for agent, message in messages
                if message.action == "vote"
            ]
            vote_ids = [agent for agent, _ in vote_messages]
            if any(agent not in voter_ids for agent in vote_ids):
                unexpected = sorted(set(vote_ids) - set(voter_ids))
                raise StrategyDecisionError(
                    "S9 received ballots from non-voter(s): " + ", ".join(unexpected)
                )
            if len(vote_ids) != len(set(vote_ids)):
                raise StrategyDecisionError("S9 requires exactly one ballot per voter; duplicate ballot")
            missing_votes = sorted(set(voter_ids) - set(vote_ids))
            if missing_votes:
                raise StrategyDecisionError(
                    "S9 requires exactly one ballot per voter; missing: "
                    + ", ".join(missing_votes)
                )
            by_candidate = {candidate.identifier: candidate for candidate in selected}
            ballots = {}
            for agent, message in vote_messages:
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
            # The paper's four-call sequence is author draft, critic objections,
            # author revision, then judge authority. Do not silently accept a
            # draft-only trace or let the pre-critique draft become the result.
            expected_trace = (
                ("author", "draft"),
                ("critic", "critique"),
                ("author", "revise"),
                ("judge", "judge"),
            )
            observed_trace = tuple(
                (output.agent_id, output.action) for output in run.outputs
            )
            if observed_trace != expected_trace:
                raise StrategyDecisionError(
                    "S5 requires the ordered four-step trace: author draft, critic critique, "
                    "author revision, judge decision"
                )
            revisions = [
                message.candidate for agent, message in messages
                if agent == "author" and message.action == "revise"
                and message.candidate is not None
            ]
            if len(revisions) != 1:
                raise StrategyDecisionError("S5 requires exactly one typed author revision")
            judge = _judge_message(messages, "judge")
            try:
                decision = authority(
                    (Candidate("author", revisions[0].decomposition),),
                    judge_id="judge",
                    selected_candidate_id=judge.selected_candidate_id,
                    rationale=judge.rationale,
                )
            except ValueError as exc:
                raise StrategyDecisionError(f"S5 judge decision is invalid: {exc}") from exc
        elif strategy_id is StrategyId.S6:
            # S6 is a sequential dialectic: the second decomposer sees D1,
            # inverts its main assumption, and returns a counter-plan D2.
            # The synthesizer then compares both and emits D*.
            expected_trace = (
                ("decomposer-1", "draft"),
                ("decomposer-2", "counter_plan"),
                ("synthesizer", "merge"),
            )
            observed_trace = tuple((output.agent_id, output.action) for output in run.outputs)
            if observed_trace != expected_trace:
                raise StrategyDecisionError(
                    "S6 requires the ordered three-step trace: first draft, counter-plan, synthesis"
                )
            selected = _required_candidates(pool, ("decomposer-1", "decomposer-2"))
            synthesized = [message.candidate for agent, message in messages
                           if agent == "synthesizer" and message.action == "merge"
                           and message.candidate is not None]
            if len(synthesized) != 1:
                raise StrategyDecisionError("S6 requires exactly one typed synthesizer decomposition")
            try:
                decision = synthesis(selected, synthesized[0].decomposition,
                                     synthesizer_id="synthesizer",
                                     rationale="Typed synthesis output.")
            except ValueError as exc:
                raise StrategyDecisionError(f"S6 synthesis decision is invalid: {exc}") from exc
        elif strategy_id is StrategyId.S7:
            # Table 4: two parallel drafts, two parallel defences, then one
            # neutral judge decision (five calls, three sequential stages).
            expected_trace = (
                ("party-1", "draft"),
                ("party-2", "draft"),
                ("party-1", "defend"),
                ("party-2", "defend"),
                ("judge", "judge"),
            )
            observed_trace = tuple((output.agent_id, output.action) for output in run.outputs)
            if observed_trace != expected_trace:
                raise StrategyDecisionError(
                    "S7 requires two independent drafts, two defences, and one judge decision"
                )
            stages = tuple(output.stage for output in run.outputs)
            if stages != (stages[0], stages[0], stages[0] + 1, stages[0] + 1, stages[0] + 2):
                raise StrategyDecisionError("S7 requires parallel draft/defence stages followed by the judge")
            if any(output.round != 1 for output in run.outputs):
                raise StrategyDecisionError("S7 is a single-round procedure")
            if run.expected_agent_ids is not None:
                expected = set(run.expected_agent_ids)
                if expected != {"party-1", "party-2", "judge"}:
                    raise StrategyDecisionError("S7 configured roster must contain two parties and one neutral judge")
            defences = [
                message for agent, message in messages
                if agent in {"party-1", "party-2"} and message.action == "defend"
            ]
            if len(defences) != 2 or any(not message.rationale.strip() for message in defences):
                raise StrategyDecisionError("S7 requires one non-empty defence from each party")
            selected = _required_candidates(pool, ("party-1", "party-2"))
            judge = _judge_message(messages, "judge")
            try:
                decision = authority(
                    selected, judge_id="judge",
                    selected_candidate_id=judge.selected_candidate_id,
                    rationale=judge.rationale,
                )
            except ValueError as exc:
                raise StrategyDecisionError(f"S7 judge decision is invalid: {exc}") from exc
        elif strategy_id is StrategyId.S8:
            # One author draft, isolated parallel reviewer reports, editor
            # verdict, and a conditional final author revision.
            trace = tuple((output.agent_id, output.action) for output in run.outputs)
            editor_positions = [
                index for index, item in enumerate(trace)
                if item == ("editor", "judge")
            ]
            editor_index = editor_positions[0] if len(editor_positions) == 1 else -1
            reviewer_trace = trace[1:editor_index] if editor_index > 1 else ()
            revision_trace = trace[editor_index + 1:] if editor_index >= 0 else ()
            if (not trace or trace[0] != ("author", "draft")
                    or editor_index < 0
                    or (not reviewer_trace and run.expected_agent_ids is None)
                    or any(action != "critique" for _, action in reviewer_trace)
                    or any(item != ("author", "revise") for item in revision_trace)):
                raise StrategyDecisionError(
                    "S8 requires author draft, parallel reviewer critiques, editor verdict, "
                    "and a conditional author revision"
                )
            expected_stages = ((1,) + (2,) * len(reviewer_trace) + (3,)
                               + (4,) * len(revision_trace))
            if tuple(output.stage for output in run.outputs) != expected_stages:
                raise StrategyDecisionError("S8 requires draft/review/editor/revision stages 1/2/3/4")
            if any(output.round != 1 for output in run.outputs):
                raise StrategyDecisionError("S8 peer review is a single-round procedure")
            if run.expected_agent_ids is not None:
                expected_roster = set(run.expected_agent_ids)
                if not {"author", "editor"}.issubset(expected_roster):
                    raise StrategyDecisionError("S8 configured roster must include author and editor")
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
            reviewer_messages = [
                (agent, message) for agent, message in messages
                if message.action == "critique"
            ]
            reviewer_ids = [agent for agent, _ in reviewer_messages]
            if (not reviewer_ids and run.expected_agent_ids is None) or any(not agent.startswith("reviewer-") for agent in reviewer_ids):
                raise StrategyDecisionError("S8 requires at least one named reviewer critique")
            if len(reviewer_ids) != len(set(reviewer_ids)):
                raise StrategyDecisionError("S8 must contain exactly one critique per reviewer")
            if run.expected_agent_ids is not None:
                expected_reviewers = {
                    agent_id for agent_id in run.expected_agent_ids
                    if agent_id.startswith("reviewer-")
                }
                observed_reviewers = set(reviewer_ids)
                if not expected_reviewers:
                    raise StrategyDecisionError("S8 expected roster must include at least one reviewer")
                if observed_reviewers != expected_reviewers:
                    missing = sorted(expected_reviewers - observed_reviewers)
                    unexpected = sorted(observed_reviewers - expected_reviewers)
                    details = []
                    if missing:
                        details.append("missing: " + ", ".join(missing))
                    if unexpected:
                        details.append("unexpected: " + ", ".join(unexpected))
                    raise StrategyDecisionError(
                        "S8 reviewer critiques do not match expected roster (" + "; ".join(details) + ")"
                    )
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
            # Consensus deliberation is shared, sequential revision: every
            # participant receives the preceding turns, then the moderator
            # closes the exchange once the deliberation rounds are complete.
            participant_ids = tuple(
                agent_id for agent_id in (
                    run.expected_agent_ids or tuple(dict.fromkeys(
                        output.agent_id for output in run.outputs
                        if output.agent_id.startswith("participant-")
                    ))
                ) if agent_id.startswith("participant-")
            )
            if not participant_ids:
                raise StrategyDecisionError("S10 requires at least one configured participant")
            if len(participant_ids) != len(set(participant_ids)):
                raise StrategyDecisionError("S10 configured participant roster contains duplicates")
            if run.expected_agent_ids is not None and "moderator" not in run.expected_agent_ids:
                raise StrategyDecisionError("S10 configured roster must include the moderator")
            participant_turns = [
                output for output in run.outputs
                if output.agent_id.startswith("participant-")
            ]
            moderator_turns = [
                output for output in run.outputs
                if output.agent_id == "moderator" and output.action == "judge"
            ]
            if not participant_turns or len(moderator_turns) != 1:
                raise StrategyDecisionError(
                    "S10 requires sequential participant revisions and exactly one final moderator closure"
                )
            if any(output.action != "revise" for output in participant_turns):
                raise StrategyDecisionError("S10 participant turns must all revise the shared draft")
            observed_rounds = sorted({output.round for output in participant_turns})
            if observed_rounds != list(range(1, max(observed_rounds) + 1)):
                raise StrategyDecisionError("S10 deliberation rounds must be contiguous from round 1")
            expected_turn_order = tuple(
                (round_number, participant_id)
                for round_number in observed_rounds
                for participant_id in participant_ids
            )
            observed_turn_order = tuple(
                (output.round, output.agent_id) for output in participant_turns
            )
            if observed_turn_order != expected_turn_order:
                raise StrategyDecisionError(
                    "S10 requires exactly one sequential revision from every participant in each round"
                )
            final_judge = moderator_turns[0]
            if run.outputs[-1] != final_judge:
                raise StrategyDecisionError("S10 moderator must close after all participant turns")
            if final_judge.round != observed_rounds[-1]:
                raise StrategyDecisionError("S10 moderator closure must follow the final deliberation round")
            expected_stages = tuple(range(1, len(run.outputs) + 1))
            if tuple(output.stage for output in run.outputs) != expected_stages:
                raise StrategyDecisionError("S10 all turns must occupy strictly sequential stages")
            final_message = next(
                message for output, (_, message) in reversed(tuple(zip(run.outputs, messages)))
                if output.agent_id.startswith("participant-") and message.candidate is not None
            )
            final_candidate_id = next(
                output.agent_id for output in reversed(run.outputs)
                if output.agent_id.startswith("participant-")
            )
            moderator = moderator_turns[0]
            moderator_message = next(
                message for output, (_, message) in zip(run.outputs, messages)
                if output is moderator
            )
            if moderator_message.consensus_no_objection is not True:
                raise StrategyDecisionError(
                    "S10 moderator must explicitly report no_objection=true to close consensus"
                )
            decision = DecisionResult(
                final_message.candidate.decomposition,
                "consensus", final_candidate_id,
                f"Moderator closed the shared draft: {moderator_message.rationale}",
            )
        elif strategy_id is StrategyId.S11:
            # Initial independent drafts are made once. Each subsequent
            # mediation round is a neutral summary followed by parallel revisions.
            if len(run.outputs) < 5 or (len(run.outputs) - 2) % 3:
                raise StrategyDecisionError("S11 requires two initial drafts and complete three-call mediation rounds")
            observed_rounds = sorted({output.round for output in run.outputs})
            if observed_rounds != list(range(1, max(observed_rounds) + 1)):
                raise StrategyDecisionError("S11 mediation rounds must be contiguous from round 1")
            initial = run.outputs[:2]
            if tuple((output.agent_id, output.action, output.round, output.stage) for output in initial) != (
                ("party-1", "draft", 1, 1), ("party-2", "draft", 1, 1)
            ):
                raise StrategyDecisionError("S11 requires exactly two parallel initial party drafts")
            for round_number in observed_rounds:
                offset = 2 + (round_number - 1) * 3
                round_outputs = run.outputs[offset:offset + 3]
                if tuple((output.agent_id, output.action, output.round) for output in round_outputs) != (
                    ("mediator", "summarise", round_number),
                    ("party-1", "revise", round_number),
                    ("party-2", "revise", round_number),
                ):
                    raise StrategyDecisionError(
                        f"S11 round {round_number} requires one mediator summary and two parallel party revisions"
                    )
                if tuple(output.stage for output in round_outputs) != (
                    2 * round_number, 2 * round_number + 1, 2 * round_number + 1
                ):
                    raise StrategyDecisionError("S11 requires one summary stage followed by parallel revision stage in every round")
            if run.expected_agent_ids is not None and set(run.expected_agent_ids) != {
                "party-1", "party-2", "mediator"
            }:
                raise StrategyDecisionError(
                    "S11 configured roster must contain exactly party-1, party-2, and mediator"
                )
            for round_number in observed_rounds:
                summary_index = 2 + (round_number - 1) * 3
                summary = messages[summary_index][1]
                if not summary.summary.strip():
                    raise StrategyDecisionError(f"S11 mediator summary in round {round_number} must be non-empty")
                if not summary.agreements and not summary.disagreements:
                    raise StrategyDecisionError(
                        f"S11 mediator summary in round {round_number} must identify agreements or disagreements"
                    )
            if run.mediation_converged is True:
                # Section 5.4.2's explicit return rule: once the two latest
                # party drafts agree or are within epsilon, return D1. The
                # mediator facilitates convergence; it does not select.
                party_one = _required_candidates(pool, ("party-1",))[0]
                decision = DecisionResult(
                    party_one.decomposition, "compromise", "party-1",
                    "The mediation stop condition was met; Section 5.4.2 returns D1 (party-1's latest draft).",
                )
            else:
                if adjudication is None or adjudication.negotiated_decomposition is None:
                    raise StrategyDecisionError(
                        "S11 exhausted its configured rounds without convergence and requires an explicit negotiated joint decomposition"
                    )
                if not adjudication.rationale.strip():
                    raise StrategyDecisionError("S11 negotiated joint decomposition requires acceptance rationale")
                selected = _required_candidates(pool, ("party-1", "party-2"))
                decision = compromise(
                    selected, adjudication.negotiated_decomposition,
                    mediator_id="mediator", rationale=adjudication.rationale,
                )
        elif strategy_id is StrategyId.S13:
            trace = tuple((agent, message.action) for agent, message in messages)
            expected_trace = (
                ("agent-A", "draft"),
                ("agent-B", "critique"),
                ("agent-B", "revise"),
                ("agent-A", "critique"),
            )
            if trace != expected_trace:
                raise StrategyDecisionError(
                    "S13 requires the ordered role-reversal trace A draft, B critique, "
                    "B revision, A critique"
                )
            if tuple(output.stage for output in run.outputs) != (1, 2, 3, 4):
                raise StrategyDecisionError("S13 requires four sequential stages")
            if any(output.round != 1 for output in run.outputs):
                raise StrategyDecisionError("S13 role reversal is a single-round procedure")
            if run.expected_agent_ids is not None and set(run.expected_agent_ids) != {"agent-A", "agent-B"}:
                raise StrategyDecisionError("S13 configured roster must contain exactly agent-A and agent-B")
            first_critique, final_critique = messages[1][1], messages[3][1]
            if not first_critique.objections:
                raise StrategyDecisionError("S13 agent-B must provide typed objections before repairing D1")
            if not final_critique.objections:
                raise StrategyDecisionError("S13 agent-A must critique the repaired D2")
            repaired = _required_candidates(pool, ("agent-B",))[0]
            decision = DecisionResult(
                repaired.decomposition, "authority", "agent-B",
                "Role reversal returns agent-B's repaired D2 after agent-A's final critique.",
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
