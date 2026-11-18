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
            candidate_out(0, "author"),
            out(1, "reviewer-1", "critique", {"objections": []}),
            out(2, "editor", "judge", {"verdict": "accept", "rationale": "Reviews addressed"}),
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
    assert len(result.decision.decomposition.kappa["Service plan"]) == 1
    assert result.decision.decomposition.subproblems[0].question == "Create service"


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


def test_edge_support_counts_use_decomposition_edge_ids_for_algorithm1_repair():
    prompt, extraction, _, raw = fixture()
    raw["subproblems"].append({
        "id": "s2", "question": "Publish service", "inputs": ["Service plan"],
        "output": "Published service", "local_constraints": [],
        "covered_requirements": [],
    })
    raw["dependencies"] = [{"source": "s1", "target": "s2"}]
    raw["kappa"] = {"Service plan": ["s2"]}
    payload = {"candidate": raw}
    result = ProtocolDecisionDecoder(prompt, extraction)(
        StrategyId.S2,
        run(out(0, "participant-1", "draft", payload),
            out(1, "participant-2", "draft", payload)),
    )
    assert result.candidate_support_counts == ((("s1", "s2"), 2),)



def distinct_candidate_out(index, agent, action, question, output_text):
    _, _, _, raw = fixture()
    raw["subproblems"][0]["question"] = question
    raw["subproblems"][0]["output"] = output_text
    return out(index, agent, action, {"candidate": raw})


@pytest.mark.parametrize("verdict,expected_question,expected_output,revise_present", [
    ("accept", "Original D0 question", "D0 output", False),
    ("revise", "Revised D1 question", "D1 output", True),
])
def test_s8_typed_verdict_assembles_original_d0_or_revised_d1(
    verdict, expected_question, expected_output, revise_present,
):
    prompt, extraction, _, _ = fixture()
    outputs = [
        distinct_candidate_out(0, "author", "draft", "Original D0 question", "D0 output"),
        out(1, "reviewer-1", "critique", {"objections": []}),
        out(2, "editor", "judge", {"verdict": verdict, "rationale": "Typed editor decision"}),
    ]
    if revise_present:
        outputs.append(distinct_candidate_out(3, "author", "revise", "Revised D1 question", "D1 output"))
    result = ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S8, run(*outputs))
    assert result.decision.rule == "authority"
    assert result.decision.selected_candidate_id == "author"
    assert result.decision.decomposition.subproblems[0].question == expected_question
    assert result.decision.decomposition.subproblems[0].output == expected_output
    assert verdict.upper() in result.decision.rationale


@pytest.mark.parametrize("verdict,outputs,match", [
    ("accept", (distinct_candidate_out(0, "author", "draft", "D0", "D0"), out(1, "reviewer-1", "critique", {"objections": []}), out(2, "editor", "judge", {"verdict":"accept","rationale":"ok"}), distinct_candidate_out(3, "author", "revise", "D1","D1")), "ACCEPT branch"),
    ("revise", (distinct_candidate_out(0, "author", "draft", "D0", "D0"), out(1, "reviewer-1", "critique", {"objections": []}), out(2, "editor", "judge", {"verdict":"revise","rationale":"fix"})), "REVISE verdict"),
])
def test_s8_rejects_inconsistent_branch_evidence(verdict, outputs, match):
    prompt, extraction, _, _ = fixture()
    with pytest.raises(StrategyDecisionError, match=match):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S8, run(*outputs))


def test_s8_rejects_duplicate_reviewer_critiques():
    prompt, extraction, _, _ = fixture()
    outputs = (
        candidate_out(0, "author"),
        out(1, "reviewer-1", "critique", {"objections": []}),
        out(2, "reviewer-1", "critique", {"objections": []}),
        out(3, "editor", "judge", {"verdict": "accept", "rationale": "Reviewed"}),
    )
    with pytest.raises(StrategyDecisionError, match="exactly one critique per reviewer"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S8, run(*outputs))


def test_s8_rejects_critique_from_unregistered_role_name():
    prompt, extraction, _, _ = fixture()
    outputs = (
        candidate_out(0, "author"),
        out(1, "critic", "critique", {"objections": []}),
        out(2, "editor", "judge", {"verdict": "accept", "rationale": "Reviewed"}),
    )
    with pytest.raises(StrategyDecisionError, match="named reviewer critique"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S8, run(*outputs))


def test_s8_revise_requires_exactly_one_author_revision():
    prompt, extraction, _, _ = fixture()
    outputs = (
        candidate_out(0, "author"),
        out(1, "reviewer-1", "critique", {"objections": []}),
        out(2, "editor", "judge", {"verdict": "revise", "rationale": "Please revise"}),
        candidate_out(3, "author", "revise"),
        candidate_out(4, "author", "revise"),
    )
    with pytest.raises(StrategyDecisionError, match="exactly one author D1 revision"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S8, run(*outputs))

@pytest.mark.parametrize("reviewer_count", [1, 3, 5])
def test_s8_requires_complete_configured_reviewer_roster(reviewer_count):
    prompt, extraction, _, _ = fixture()
    expected = ("author", *(f"reviewer-{i}" for i in range(1, reviewer_count + 1)), "editor")
    complete = [candidate_out(0, "author")]
    complete.extend(out(i, f"reviewer-{i}", "critique", {"objections": []})
                    for i in range(1, reviewer_count + 1))
    complete.append(out(reviewer_count + 1, "editor", "judge",
                        {"verdict": "accept", "rationale": "Reviewed"}))
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    assert decoder(StrategyId.S8, StrategyRun(
        "S8", tuple(complete), len(complete), 3, (), expected,
    )).decision.rule == "authority"
    for missing_id in (f"reviewer-{i}" for i in range(1, reviewer_count + 1)):
        incomplete = tuple(item for item in complete if item.agent_id != missing_id)
        with pytest.raises(StrategyDecisionError, match="do not match expected roster"):
            decoder(StrategyId.S8, StrategyRun(
                "S8", incomplete, len(incomplete), 3, (), expected,
            ))


def test_s8_rejects_unexpected_reviewer_when_roster_is_known():
    prompt, extraction, _, _ = fixture()
    outputs = (
        candidate_out(0, "author"),
        out(1, "reviewer-1", "critique", {"objections": []}),
        out(2, "reviewer-2", "critique", {"objections": []}),
        out(3, "editor", "judge", {"verdict": "accept", "rationale": "Reviewed"}),
    )
    known_roster = StrategyRun(
        "S8", outputs, len(outputs), 3, (),
        ("author", "reviewer-1", "editor"),
    )
    with pytest.raises(StrategyDecisionError, match="unexpected: reviewer-2"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S8, known_roster)


def test_s8_legacy_run_without_roster_retains_minimum_reviewer_validation():
    prompt, extraction, _, _ = fixture()
    outputs = (
        candidate_out(0, "author"),
        out(1, "reviewer-1", "critique", {"objections": []}),
        out(2, "editor", "judge", {"verdict": "accept", "rationale": "Reviewed"}),
    )
    assert ProtocolDecisionDecoder(prompt, extraction)(
        StrategyId.S8, run(*outputs),
    ).decision.rule == "authority"


@pytest.mark.parametrize("voter_count", [1, 3, 5])
def test_s9_requires_exactly_one_ballot_from_every_configured_voter(voter_count):
    prompt, extraction, _, _ = fixture()
    expected = tuple(f"voter-{i}" for i in range(1, voter_count + 1))
    outputs = [candidate_out(i, voter) for i, voter in enumerate(expected)]
    outputs.extend(
        out(voter_count + i, voter, "vote", {
            "endorsed_subproblems": [
                {"candidate_id": voter, "subproblem_id": "s1"}
            ],
        })
        for i, voter in enumerate(expected)
    )
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    complete = StrategyRun(
        "S9", tuple(outputs), len(outputs), 2, (), expected,
    )
    assert decoder(StrategyId.S9, complete).decision.rule == "majority"

    for missing_voter in expected:
        incomplete = tuple(
            item for item in outputs
            if not (item.action == "vote" and item.agent_id == missing_voter)
        )
        with pytest.raises(StrategyDecisionError, match="exactly one ballot per voter; missing"):
            decoder(StrategyId.S9, StrategyRun(
                "S9", incomplete, len(incomplete), 2, (), expected,
            ))


def test_s9_rejects_duplicate_ballots_and_non_voter_ballots():
    prompt, extraction, _, _ = fixture()
    expected = ("voter-1", "voter-2")
    base = (
        candidate_out(0, "voter-1"),
        candidate_out(1, "voter-2"),
        out(2, "voter-1", "vote", {"endorsed_subproblems": []}),
        out(3, "voter-2", "vote", {"endorsed_subproblems": []}),
    )
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    duplicate = (*base, out(4, "voter-1", "vote", {"endorsed_subproblems": []}))
    with pytest.raises(StrategyDecisionError, match="duplicate ballot"):
        decoder(StrategyId.S9, StrategyRun(
            "S9", duplicate, len(duplicate), 2, (), expected,
        ))
    unexpected = (*base, out(4, "observer", "vote", {"endorsed_subproblems": []}))
    with pytest.raises(StrategyDecisionError, match="non-voter"):
        decoder(StrategyId.S9, StrategyRun(
            "S9", unexpected, len(unexpected), 2, (), expected,
        ))


def test_s9_rejects_missing_configured_voter_draft():
    prompt, extraction, _, _ = fixture()
    expected = ("voter-1", "voter-2")
    outputs = (
        candidate_out(0, "voter-1"),
        out(1, "voter-1", "vote", {"endorsed_subproblems": []}),
        out(2, "voter-2", "vote", {"endorsed_subproblems": []}),
    )
    with pytest.raises(StrategyDecisionError, match="candidate drafts do not match"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S9, StrategyRun(
            "S9", outputs, len(outputs), 2, (), expected,
        ))


@pytest.mark.parametrize("member_count", [1, 3, 5])
def test_s3_requires_complete_configured_member_drafts_and_rankings(member_count):
    prompt, extraction, _, _ = fixture()
    expected = tuple(f"member-{i}" for i in range(1, member_count + 1))
    outputs = [candidate_out(i, member) for i, member in enumerate(expected)]
    outputs.extend(
        out(member_count + i, member, "rank", {"ranking": list(expected)})
        for i, member in enumerate(expected)
    )
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    complete = StrategyRun("S3", tuple(outputs), len(outputs), 2, (), expected)
    assert decoder(StrategyId.S3, complete).decision.rule == "rank-sum"

    for missing in expected:
        incomplete = tuple(
            item for item in outputs
            if not (item.action == "rank" and item.agent_id == missing)
        )
        with pytest.raises(StrategyDecisionError, match="exactly one ranking per member; missing"):
            decoder(StrategyId.S3, StrategyRun(
                "S3", incomplete, len(incomplete), 2, (), expected,
            ))


def test_s3_rejects_unexpected_and_duplicate_rankings():
    prompt, extraction, _, _ = fixture()
    expected = ("member-1", "member-2")
    base = (
        candidate_out(0, "member-1"),
        candidate_out(1, "member-2"),
        out(2, "member-1", "rank", {"ranking": list(expected)}),
        out(3, "member-2", "rank", {"ranking": list(expected)}),
    )
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    duplicate = (*base, out(4, "member-1", "rank", {"ranking": list(expected)}))
    with pytest.raises(StrategyDecisionError, match="duplicate ranking"):
        decoder(StrategyId.S3, StrategyRun(
            "S3", duplicate, len(duplicate), 2, (), expected,
        ))
    unexpected = (*base, out(4, "observer", "rank", {"ranking": list(expected)}))
    with pytest.raises(StrategyDecisionError, match="non-member"):
        decoder(StrategyId.S3, StrategyRun(
            "S3", unexpected, len(unexpected), 2, (), expected,
        ))


def test_s3_rejects_missing_configured_member_draft():
    prompt, extraction, _, _ = fixture()
    expected = ("member-1", "member-2")
    outputs = (
        candidate_out(0, "member-1"),
        out(1, "member-1", "rank", {"ranking": list(expected)}),
        out(2, "member-2", "rank", {"ranking": list(expected)}),
    )
    with pytest.raises(StrategyDecisionError, match="candidate drafts do not match"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S3, StrategyRun(
            "S3", outputs, len(outputs), 2, (), expected,
        ))


def test_s3_rejects_incomplete_ranking_permutation():
    prompt, extraction, _, _ = fixture()
    expected = ("member-1", "member-2")
    outputs = (
        candidate_out(0, "member-1"),
        candidate_out(1, "member-2"),
        out(2, "member-1", "rank", {"ranking": ["member-1"]}),
        out(3, "member-2", "rank", {"ranking": list(expected)}),
    )
    with pytest.raises(StrategyDecisionError, match="invalid ranking evidence"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S3, StrategyRun(
            "S3", outputs, len(outputs), 2, (), expected,
        ))


def test_s3_legacy_run_without_roster_requires_observed_members_and_rankings():
    prompt, extraction, _, _ = fixture()
    outputs = (
        candidate_out(0, "member-1"),
        candidate_out(1, "member-2"),
        out(2, "member-1", "rank", {"ranking": ["member-1", "member-2"]}),
        out(3, "member-2", "rank", {"ranking": ["member-2", "member-1"]}),
    )
    assert ProtocolDecisionDecoder(prompt, extraction)(
        StrategyId.S3, run(*outputs),
    ).decision.rule == "rank-sum"
