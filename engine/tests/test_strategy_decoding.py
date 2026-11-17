import json
import pytest

from sociodec.catalogue import StrategyId
from sociodec.decisions import Candidate
from sociodec.extraction import ExtractionResult, aggregate_extractions
from sociodec.models.decomposition import Decomposition, Subproblem
from sociodec.models.prompt import Interpretation, Prompt
from sociodec.runtime import ProtocolOutput, StrategyRun
from sociodec.strategy_decoding import (
    DecisionAdjudication, ProtocolDecisionDecoder, StrategyDecisionError,
)


def fixture():
    prompt = Prompt("Create a service plan.", Interpretation(
        "Create service", deliverables=("Service plan",),
    ))
    extraction = aggregate_extractions((ExtractionResult(extractor_id="e1"),))
    d = Decomposition(
        (Subproblem("s1", "Create service", (), "Service plan", (), ()),),
        (), (),
    )
    candidate_json = {
        "candidate_id": "ignored-by-runtime-author",
        "subproblems": [{
            "id": "s1", "question": "Create service", "inputs": [],
            "output": "Service plan", "local_constraints": [],
            "covered_requirements": [],
        }],
        "dependencies": [], "kappa": {"Service plan": ["s1"]},
    }
    return prompt, extraction, d, candidate_json


def out(index, agent, action, payload):
    return ProtocolOutput(
        index, agent, 1, index + 1, action,
        json.dumps(payload), True, False,
    )


def candidate_out(index, agent, action="draft"):
    _, _, _, raw = fixture()
    return out(index, agent, action, {"candidate": raw})


def run(*outputs):
    return StrategyRun("test", tuple(outputs), len(outputs), len(outputs), ())


@pytest.mark.parametrize(
    "sid,outputs,expected",
    [
        (StrategyId.S1, (candidate_out(0, "coordinator", "check"),), "authority"),
        (StrategyId.S12, (candidate_out(0, "expert-1"), candidate_out(1, "expert-2")), "union"),
        (StrategyId.S2, (candidate_out(0, "participant-1"), candidate_out(1, "participant-2")), "union"),
        (StrategyId.S3, (
            candidate_out(0, "member-1"), candidate_out(1, "member-2"),
            out(2, "member-1", "rank", {"ranking": ["member-1", "member-2"]}),
            out(3, "member-2", "rank", {"ranking": ["member-2", "member-1"]}),
        ), "rank-sum"),
        (StrategyId.S4, (
            candidate_out(0, "expert-1"), candidate_out(1, "expert-2"),
            out(2, "facilitator", "summarise", {"summary": "Shared summary"}),
            candidate_out(3, "expert-1", "revise"), candidate_out(4, "expert-2", "revise"),
        ), "consensus-medoid"),
        (StrategyId.S9, (
            candidate_out(0, "voter-1"), candidate_out(1, "voter-2"),
            out(2, "voter-1", "vote", {"endorsed_subproblems": [{"candidate_id": "voter-1", "subproblem_id": "s1"}]}),
            out(3, "voter-2", "vote", {"endorsed_subproblems": [{"candidate_id": "voter-2", "subproblem_id": "s1"}]}),
        ), "majority"),
        (StrategyId.S5, (
            candidate_out(0, "author"), candidate_out(1, "author", "revise"),
            out(2, "judge", "judge", {"selected_candidate_id": "author", "rationale": "Accepted after critique"}),
        ), "authority"),
        (StrategyId.S6, (
            candidate_out(0, "decomposer-1"), candidate_out(1, "decomposer-2"),
            candidate_out(2, "synthesizer", "merge"),
        ), "synthesis"),
        (StrategyId.S7, (
            candidate_out(0, "party-1"), candidate_out(1, "party-2"),
            out(2, "judge", "judge", {"selected_candidate_id": "party-1", "rationale": "Stronger defence"}),
        ), "authority"),
        (StrategyId.S8, (
            candidate_out(0, "author"), candidate_out(1, "editor", "judge")
            if False else out(1, "editor", "judge", {"selected_candidate_id": "author", "rationale": "Reviews addressed"}),
            candidate_out(2, "author", "revise"),
        ), "authority"),
        (StrategyId.S10, (
            candidate_out(0, "participant-1", "revise"),
            candidate_out(1, "participant-2", "revise"),
            out(2, "moderator", "judge", {"selected_candidate_id": "participant-1", "rationale": "No unresolved objection"}),
        ), "consensus"),
    ],
)
def test_strategy_decision_assembly_applies_paper_operator(sid, outputs, expected):
    prompt, extraction, _, _ = fixture()
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    result = decoder(sid, run(*outputs))
    assert result.decision.rule == expected
    assert result.decision.decomposition.kappa == {"Service plan": frozenset({"s1"})}


def test_s11_compromise_requires_explicit_negotiated_result():
    prompt, extraction, d, _ = fixture()
    outputs = (
        candidate_out(0, "party-1"),
        candidate_out(1, "party-2"),
        out(2, "mediator", "summarise", {"summary": "Balance cost and access"}),
        candidate_out(3, "party-1", "revise"),
        candidate_out(4, "party-2", "revise"),
    )
    with pytest.raises(StrategyDecisionError, match="explicit external decision adjudication"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S11, run(*outputs))
    decoder = ProtocolDecisionDecoder(prompt, extraction, adjudications={
        StrategyId.S11: DecisionAdjudication(
            negotiated_decomposition=d, rationale="Both parties accepted the negotiated plan",
        ),
    })
    assert decoder(StrategyId.S11, run(*outputs)).decision.rule == "compromise"


def test_s13_authority_choice_must_be_explicit_not_inferred_from_critique():
    prompt, extraction, _, _ = fixture()
    outputs = (
        candidate_out(0, "agent-A"),
        out(1, "agent-B", "critique", {"objections": []}),
        candidate_out(2, "agent-B", "revise"),
        out(3, "agent-A", "critique", {"objections": []}),
    )
    with pytest.raises(StrategyDecisionError, match="explicit external decision adjudication"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S13, run(*outputs))
    decoder = ProtocolDecisionDecoder(prompt, extraction, adjudications={
        StrategyId.S13: DecisionAdjudication(
            selected_candidate_id="agent-B", rationale="Agent A explicitly endorses the repaired draft",
        ),
    })
    assert decoder(StrategyId.S13, run(*outputs)).decision.rule == "authority"


def test_s9_rejects_ballots_with_unknown_candidate_or_subproblem():
    prompt, extraction, _, _ = fixture()
    outputs = (
        candidate_out(0, "voter-1"),
        out(1, "voter-1", "vote", {"endorsed_subproblems": [{"candidate_id": "unknown", "subproblem_id": "s1"}]}),
    )
    with pytest.raises(StrategyDecisionError, match="unknown candidate"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S9, run(*outputs))


def test_conflicting_hypothesis_verdicts_are_rejected():
    prompt, extraction, _, _ = fixture()
    # Empty extraction has no hypotheses, so the parser rejects the unknown
    # verdict before a contradictory pair can be silently aggregated.
    payload = {"candidate": fixture()[3], "hypothesis_verdicts": [{
        "type": "target", "domain": "x", "statement": "unknown", "verdict": "confirmed",
    }]}
    with pytest.raises(ValueError, match="outside H-hat"):
        ProtocolDecisionDecoder(prompt, extraction)(
            StrategyId.S2, run(out(0, "participant-1", "draft", payload)),
        )
