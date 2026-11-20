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


def _s7_complete_trace():
    raw = fixture()[3]
    return (
        ProtocolOutput(0, "party-1", 1, 1, "draft", json.dumps({"candidate": raw}), True, False),
        ProtocolOutput(1, "party-2", 1, 1, "draft", json.dumps({"candidate": raw}), True, False),
        ProtocolOutput(2, "party-1", 1, 2, "defend", json.dumps({"defence": "This plan maximises deliverable coverage."}), True, False),
        ProtocolOutput(3, "party-2", 1, 2, "defend", json.dumps({"defence": "This plan minimises duplicated subproblems."}), True, False),
        ProtocolOutput(4, "judge", 1, 3, "judge", json.dumps({
            "selected_candidate_id": "party-1", "rationale": "Coverage takes precedence under the rubric."
        }), True, False),
    )


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
            ProtocolOutput(0, "expert-1", 1, 1, "draft", json.dumps({"candidate": fixture()[3]}), True, False),
            ProtocolOutput(1, "expert-2", 1, 1, "draft", json.dumps({"candidate": fixture()[3]}), True, False),
            ProtocolOutput(2, "facilitator", 1, 2, "summarise", json.dumps({"summary": "Shared summary"}), True, False),
            ProtocolOutput(3, "expert-1", 2, 3, "revise", json.dumps({"candidate": fixture()[3]}), True, False),
            ProtocolOutput(4, "expert-2", 2, 3, "revise", json.dumps({"candidate": fixture()[3]}), True, False),
            ProtocolOutput(5, "facilitator", 2, 4, "summarise", json.dumps({"summary": "No remaining divergence"}), True, False),
        ), "consensus-medoid"),
        (StrategyId.S9, (
            candidate_out(0, "voter-1"), candidate_out(1, "voter-2"),
            out(2, "voter-1", "vote", {"endorsed_subproblems": [{"candidate_id": "voter-1", "subproblem_id": "s1"}]}),
            out(3, "voter-2", "vote", {"endorsed_subproblems": [{"candidate_id": "voter-2", "subproblem_id": "s1"}]}),
        ), "majority"),
        (StrategyId.S5, (
            candidate_out(0, "author"),
            out(1, "critic", "critique", {"objections": [{"kind": "missing_subproblem", "subject": "as-is analysis", "rationale": "The target cannot be planned without the current-state analysis."}]}),
            candidate_out(2, "author", "revise"),
            out(3, "judge", "judge", {"selected_candidate_id": "author", "rationale": "The revision addresses the objection."}),
        ), "authority"),
        (StrategyId.S6, (
            candidate_out(0, "decomposer-1"), candidate_out(1, "decomposer-2", "counter_plan"),
            candidate_out(2, "synthesizer", "merge"),
        ), "synthesis"),
        (StrategyId.S7, _s7_complete_trace(), "authority"),
        (StrategyId.S8, (
            candidate_out(0, "author"),
            out(1, "reviewer-1", "critique", {"objections": []}),
            out(2, "editor", "judge", {"verdict": "accept", "rationale": "Reviews addressed"}),
        ), "authority"),
        (StrategyId.S10, (
            candidate_out(0, "participant-1", "revise"),
            candidate_out(1, "participant-2", "revise"),
            out(2, "moderator", "judge", {"no_objection": True, "rationale": "No unresolved objection"}),
        ), "consensus"),
    ],
)
def test_strategy_decision_assembly_applies_paper_operator(sid, outputs, expected):
    prompt, extraction, _, _ = fixture()
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    strategy_run = run_s7(*outputs) if sid is StrategyId.S7 else run(*outputs)
    result = decoder(sid, strategy_run)
    assert result.decision.rule == expected
    assert len(result.decision.decomposition.kappa["Service plan"]) == 1
    assert result.decision.decomposition.subproblems[0].question == "Create service"


def test_s11_returns_party_one_latest_draft_when_runtime_confirms_paper_stop_rule():
    prompt, extraction, _, raw = fixture()
    party_one = dict(raw)
    party_one["subproblems"] = [dict(party_one["subproblems"][0], question="D1 latest", output="D1")]
    party_two = dict(raw)
    party_two["subproblems"] = [dict(party_two["subproblems"][0], question="D2 latest", output="D2")]
    outputs = (
        ProtocolOutput(0, "party-1", 1, 1, "draft", json.dumps({"candidate": raw}), True, False),
        ProtocolOutput(1, "party-2", 1, 1, "draft", json.dumps({"candidate": raw}), True, False),
        ProtocolOutput(2, "mediator", 1, 2, "summarise", json.dumps({
            "summary": "Agreements and disagreements", "agreements": ["scope"],
            "disagreements": ["ordering"],
        }), True, False),
        ProtocolOutput(3, "party-1", 1, 3, "revise", json.dumps({"candidate": party_one}), True, False),
        ProtocolOutput(4, "party-2", 1, 3, "revise", json.dumps({"candidate": party_two}), True, False),
    )
    converged = StrategyRun(
        "S11", outputs, 5, 3, (), ("party-1", "party-2", "mediator"),
        mediation_converged=True, mediation_stop_round=1, mediation_distance=0.04,
    )
    decision = ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S11, converged).decision
    assert decision.rule == "compromise"
    assert decision.selected_candidate_id == "party-1"
    assert decision.decomposition.subproblems[0].question == "D1 latest"
    assert "returns D1" in decision.rationale


def test_s11_compromise_requires_explicit_negotiated_result():
    prompt, extraction, d, _ = fixture()
    outputs = (
        ProtocolOutput(0, "party-1", 1, 1, "draft",
                       json.dumps({"candidate": fixture()[3]}), True, False),
        ProtocolOutput(1, "party-2", 1, 1, "draft",
                       json.dumps({"candidate": fixture()[3]}), True, False),
        ProtocolOutput(2, "mediator", 1, 2, "summarise",
                       json.dumps({"summary": "Balance cost and access",
                                   "agreements": ["access"],
                                   "disagreements": ["cost"]}), True, False),
        ProtocolOutput(3, "party-1", 1, 3, "revise",
                       json.dumps({"candidate": fixture()[3]}), True, False),
        ProtocolOutput(4, "party-2", 1, 3, "revise",
                       json.dumps({"candidate": fixture()[3]}), True, False),
    )
    configured = StrategyRun("S11", outputs, len(outputs), 3, (),
                              ("party-1", "party-2", "mediator"))
    with pytest.raises(StrategyDecisionError, match="explicit negotiated joint decomposition"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S11, configured)
    decoder = ProtocolDecisionDecoder(prompt, extraction, adjudications={
        StrategyId.S11: DecisionAdjudication(
            negotiated_decomposition=d, rationale="Both parties accepted the negotiated plan",
        ),
    })
    assert decoder(StrategyId.S11, configured).decision.rule == "compromise"


def test_s13_rejects_empty_critique_instead_of_inventing_a_separate_judge():
    prompt, extraction, _, _ = fixture()
    outputs = (
        candidate_out(0, "agent-A"),
        out(1, "agent-B", "critique", {"objections": []}),
        candidate_out(2, "agent-B", "revise"),
        out(3, "agent-A", "critique", {"objections": []}),
    )
    with pytest.raises(StrategyDecisionError, match="agent-B must provide typed objections"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S13, run_s13(*outputs))


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


def run_s8(*outputs, expected_agent_ids=None):
    stage_by_action = {"draft": 1, "critique": 2, "judge": 3, "revise": 4}
    staged = tuple(
        ProtocolOutput(item.step_index, item.agent_id, 1,
                       stage_by_action[item.action], item.action,
                       item.text, item.model_invoked, item.from_seed)
        for item in outputs
    )
    return StrategyRun("S8", staged, len(staged),
                       max(item.stage for item in staged), (),
                       expected_agent_ids)


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
    result = ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S8, run_s8(*outputs))
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
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S8, run_s8(*outputs))


def test_s8_rejects_duplicate_reviewer_critiques():
    prompt, extraction, _, _ = fixture()
    outputs = (
        candidate_out(0, "author"),
        out(1, "reviewer-1", "critique", {"objections": []}),
        out(2, "reviewer-1", "critique", {"objections": []}),
        out(3, "editor", "judge", {"verdict": "accept", "rationale": "Reviewed"}),
    )
    with pytest.raises(StrategyDecisionError, match="exactly one critique per reviewer"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S8, run_s8(*outputs))


def test_s8_rejects_critique_from_unregistered_role_name():
    prompt, extraction, _, _ = fixture()
    outputs = (
        candidate_out(0, "author"),
        out(1, "critic", "critique", {"objections": []}),
        out(2, "editor", "judge", {"verdict": "accept", "rationale": "Reviewed"}),
    )
    with pytest.raises(StrategyDecisionError, match="named reviewer critique"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S8, run_s8(*outputs))


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
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S8, run_s8(*outputs))

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
    assert decoder(StrategyId.S8, run_s8(*complete, expected_agent_ids=expected)).decision.rule == "authority"
    for missing_id in (f"reviewer-{i}" for i in range(1, reviewer_count + 1)):
        incomplete = tuple(item for item in complete if item.agent_id != missing_id)
        with pytest.raises(StrategyDecisionError, match="do not match expected roster"):
            decoder(StrategyId.S8, run_s8(*incomplete, expected_agent_ids=expected))


def test_s8_rejects_unexpected_reviewer_when_roster_is_known():
    prompt, extraction, _, _ = fixture()
    outputs = (
        candidate_out(0, "author"),
        out(1, "reviewer-1", "critique", {"objections": []}),
        out(2, "reviewer-2", "critique", {"objections": []}),
        out(3, "editor", "judge", {"verdict": "accept", "rationale": "Reviewed"}),
    )
    known_roster = run_s8(
        *outputs, expected_agent_ids=("author", "reviewer-1", "editor"),
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
        StrategyId.S8, run_s8(*outputs),
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


def _s4_outputs(rounds=2, *, omit=None, duplicate=None):
    raw = fixture()[3]
    outputs = []
    index = 0
    for round_number in range(1, rounds + 1):
        action = "draft" if round_number == 1 else "revise"
        stage = 2 * round_number - 1
        for expert in ("expert-1", "expert-2"):
            if omit == (round_number, expert):
                continue
            outputs.append(ProtocolOutput(
                index, expert, round_number, stage, action,
                json.dumps({"candidate": raw}), True, False,
            ))
            index += 1
        if duplicate == (round_number, "expert-1"):
            outputs.append(ProtocolOutput(
                index, "expert-1", round_number, stage, action,
                json.dumps({"candidate": raw}), True, False,
            ))
            index += 1
        outputs.append(ProtocolOutput(
            index, "facilitator", round_number, 2 * round_number,
            "summarise", json.dumps({"summary": f"Round {round_number} summary"}),
            True, False,
        ))
        index += 1
    return tuple(outputs)


def test_s4_requires_every_configured_expert_in_every_round():
    prompt, extraction, _, _ = fixture()
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    outputs = _s4_outputs(2, omit=(2, "expert-2"))
    with pytest.raises(StrategyDecisionError, match="round 2 expert roster mismatch"):
        decoder(StrategyId.S4, StrategyRun(
            "S4", outputs, len(outputs), 4, (),
            ("expert-1", "expert-2", "facilitator"),
        ))


def test_s4_requires_exactly_one_facilitator_summary_per_round():
    prompt, extraction, _, _ = fixture()
    outputs = tuple(x for x in _s4_outputs(2) if not (x.round == 1 and x.agent_id == "facilitator"))
    with pytest.raises(StrategyDecisionError, match="round 1 requires exactly one facilitator summary"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S4, StrategyRun(
            "S4", outputs, len(outputs), 4, (),
            ("expert-1", "expert-2", "facilitator"),
        ))


def test_s4_rejects_duplicate_expert_drafts_within_a_round():
    prompt, extraction, _, _ = fixture()
    outputs = _s4_outputs(2, duplicate=(2, "expert-1"))
    with pytest.raises(StrategyDecisionError, match="duplicate expert drafts"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S4, StrategyRun(
            "S4", outputs, len(outputs), 4, (),
            ("expert-1", "expert-2", "facilitator"),
        ))


def test_s4_requires_contiguous_rounds():
    prompt, extraction, _, _ = fixture()
    outputs = tuple(x for x in _s4_outputs(2) if x.round != 1)
    with pytest.raises(StrategyDecisionError, match="contiguous from round 1"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S4, StrategyRun(
            "S4", outputs, len(outputs), 2, (),
            ("expert-1", "expert-2", "facilitator"),
        ))


def test_s4_legacy_run_validates_observed_expert_roster_per_round():
    prompt, extraction, _, _ = fixture()
    outputs = _s4_outputs(2)
    result = ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S4, StrategyRun(
        "S4", outputs, len(outputs), 4, (),
    ))
    assert result.decision.rule == "consensus-medoid"



def _s5_complete_trace():
    return (
        candidate_out(0, "author"),
        out(1, "critic", "critique", {"objections": [{"kind": "hidden_dependency", "subject": "data-sharing agreement", "rationale": "Interoperability depends on permission to exchange data."}]}),
        candidate_out(2, "author", "revise"),
        out(3, "judge", "judge", {"selected_candidate_id": "author", "rationale": "The revision answers the objection."}),
    )


def test_s5_rejects_missing_critic_or_revision_or_judge_steps():
    prompt, extraction, _, _ = fixture()
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    complete = _s5_complete_trace()
    for incomplete in (complete[:1] + complete[2:], complete[:2] + complete[3:], complete[:3]):
        with pytest.raises(StrategyDecisionError, match="ordered four-step trace"):
            decoder(StrategyId.S5, run(*incomplete))


def test_s5_rejects_reordered_or_duplicate_critic_trace():
    prompt, extraction, _, _ = fixture()
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    complete = _s5_complete_trace()
    reordered = (complete[0], complete[2], complete[1], complete[3])
    with pytest.raises(StrategyDecisionError, match="ordered four-step trace"):
        decoder(StrategyId.S5, run(*reordered))
    duplicated = (complete[0], complete[1], complete[1], complete[2], complete[3])
    with pytest.raises(StrategyDecisionError, match="ordered four-step trace"):
        decoder(StrategyId.S5, run(*duplicated))


def test_s5_judge_must_select_the_revised_author_candidate():
    prompt, extraction, _, _ = fixture()
    outputs = list(_s5_complete_trace())
    outputs[-1] = out(3, "judge", "judge", {
        "selected_candidate_id": "other", "rationale": "Select another candidate."
    })
    with pytest.raises(StrategyDecisionError, match="may select only a supplied candidate"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S5, run(*outputs))



def _s6_complete_trace():
    return (
        candidate_out(0, "decomposer-1"),
        candidate_out(1, "decomposer-2", "counter_plan"),
        candidate_out(2, "synthesizer", "merge"),
    )


def test_s6_rejects_missing_counter_plan_or_synthesis():
    prompt, extraction, _, _ = fixture()
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    complete = _s6_complete_trace()
    for incomplete in ((complete[0], complete[2]), complete[:2]):
        with pytest.raises(StrategyDecisionError, match="ordered three-step trace"):
            decoder(StrategyId.S6, run(*incomplete))


def test_s6_rejects_reordered_or_duplicate_dialectical_steps():
    prompt, extraction, _, _ = fixture()
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    complete = _s6_complete_trace()
    for invalid in ((complete[1], complete[0], complete[2]),
                    (complete[0], complete[1], complete[1], complete[2])):
        with pytest.raises(StrategyDecisionError, match="ordered three-step trace"):
            decoder(StrategyId.S6, run(*invalid))


def test_s6_counter_plan_is_a_typed_candidate_action():
    prompt, extraction, _, _ = fixture()
    result = ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S6, run(*_s6_complete_trace()))
    assert result.decision.rule == "synthesis"


def test_s7_requires_both_independent_drafts_defences_and_judge():
    prompt, extraction, _, _ = fixture()
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    complete = _s7_complete_trace()
    assert decoder(StrategyId.S7, run_s7(*complete)).decision.rule == "authority"
    for invalid in (complete[:4], complete[:3] + complete[4:],
                    complete[:2] + complete[3:4] + complete[4:],
                    complete[:2] + complete[3:4] + complete[2:3] + complete[4:]):
        with pytest.raises(StrategyDecisionError):
            decoder(StrategyId.S7, run_s7(*invalid))


def run_s7(*outputs):
    return StrategyRun("S7", tuple(outputs), len(outputs), 3, (),
                       ("party-1", "party-2", "judge"))


def test_s7_rejects_wrong_parallel_stage_structure_and_non_neutral_roster():
    prompt, extraction, _, _ = fixture()
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    complete = list(_s7_complete_trace())
    complete[1] = ProtocolOutput(1, "party-2", 1, 2, "draft",
                                 complete[1].text, True, False)
    with pytest.raises(StrategyDecisionError, match="parallel draft/defence stages"):
        decoder(StrategyId.S7, run_s7(*complete))
    with pytest.raises(StrategyDecisionError, match="configured roster"):
        decoder(StrategyId.S7, StrategyRun(
            "S7", _s7_complete_trace(), 5, 3, (),
            ("party-1", "party-2", "party-3"),
        ))


def test_s7_judge_must_select_one_of_the_two_submitted_cases():
    prompt, extraction, _, _ = fixture()
    outputs = list(_s7_complete_trace())
    outputs[-1] = ProtocolOutput(
        4, "judge", 1, 3, "judge",
        json.dumps({"selected_candidate_id": "outsider", "rationale": "Outside case"}),
        True, False,
    )
    with pytest.raises(StrategyDecisionError, match="may select only a supplied candidate"):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S7, run_s7(*outputs))



def test_s8_requires_parallel_review_stage_and_editor_after_all_reviews():
    prompt, extraction, _, _ = fixture()
    outputs = (
        candidate_out(0, "author"),
        out(1, "reviewer-1", "critique", {"objections": []}),
        out(2, "reviewer-2", "critique", {"objections": []}),
        out(3, "editor", "judge", {"verdict": "accept", "rationale": "Reviewed"}),
    )
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    valid = run_s8(*outputs)
    assert decoder(StrategyId.S8, valid).decision.rule == "authority"

    serial_reviews = list(valid.outputs)
    serial_reviews[2] = ProtocolOutput(
        2, "reviewer-2", 1, 3, "critique",
        serial_reviews[2].text, True, False,
    )
    invalid = StrategyRun("S8", tuple(serial_reviews), 4, 3, (), None)
    with pytest.raises(StrategyDecisionError, match="stages 1/2/3/4"):
        decoder(StrategyId.S8, invalid)


def test_s8_rejects_editor_before_reviewers_and_revision_outside_stage_four():
    prompt, extraction, _, _ = fixture()
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    draft = candidate_out(0, "author")
    review = out(1, "reviewer-1", "critique", {"objections": []})
    editor = out(2, "editor", "judge", {"verdict": "revise", "rationale": "Revise"})
    revision = candidate_out(3, "author", "revise")

    reordered = run_s8(draft, editor, review, revision)
    with pytest.raises(StrategyDecisionError, match="author draft, parallel reviewer critiques"):
        decoder(StrategyId.S8, reordered)

    valid = run_s8(draft, review, editor, revision)
    changed = list(valid.outputs)
    changed[-1] = ProtocolOutput(3, "author", 1, 3, "revise",
                                 changed[-1].text, True, False)
    with pytest.raises(StrategyDecisionError, match="stages 1/2/3/4"):
        decoder(StrategyId.S8, StrategyRun("S8", tuple(changed), 4, 3, (), None))


def test_s8_requires_single_round_and_exact_configured_author_editor_roster():
    prompt, extraction, _, _ = fixture()
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    outputs = run_s8(
        candidate_out(0, "author"),
        out(1, "reviewer-1", "critique", {"objections": []}),
        out(2, "editor", "judge", {"verdict": "accept", "rationale": "Reviewed"}),
    )
    wrong_round = tuple(
        ProtocolOutput(x.step_index, x.agent_id, 2 if x.agent_id == "reviewer-1" else 1,
                       x.stage, x.action, x.text, x.model_invoked, x.from_seed)
        for x in outputs.outputs
    )
    with pytest.raises(StrategyDecisionError, match="single-round"):
        decoder(StrategyId.S8, StrategyRun("S8", wrong_round, 3, 3, (), None))
    with pytest.raises(StrategyDecisionError, match="configured roster"):
        decoder(StrategyId.S8, run_s8(
            *outputs.outputs, expected_agent_ids=("author", "reviewer-1"),
        ))


def _s13_complete_trace():
    raw = fixture()[3]
    return (
        ProtocolOutput(0, "agent-A", 1, 1, "draft", json.dumps({"candidate": raw}), True, False),
        ProtocolOutput(1, "agent-B", 1, 2, "critique", json.dumps({
            "objections": [{"kind": "missing_subproblem", "subject": "s1",
                            "rationale": "The initial plan omits a required component."}]
        }), True, False),
        ProtocolOutput(2, "agent-B", 1, 3, "revise", json.dumps({"candidate": raw}), True, False),
        ProtocolOutput(3, "agent-A", 1, 4, "critique", json.dumps({
            "objections": [{"kind": "hidden_dependency", "subject": "s1",
                            "rationale": "The repaired plan does not justify the prerequisite."}]
        }), True, False),
    )


def run_s13(*outputs, expected_agent_ids=("agent-A", "agent-B")):
    return StrategyRun("S13", tuple(outputs), len(outputs), 4, (), expected_agent_ids)


def test_s13_role_reversal_returns_b_repaired_candidate_after_a_final_critique():
    prompt, extraction, _, _ = fixture()
    result = ProtocolDecisionDecoder(prompt, extraction)(
        StrategyId.S13, run_s13(*_s13_complete_trace()),
    )
    assert result.decision.rule == "authority"
    assert result.decision.selected_candidate_id == "agent-B"


@pytest.mark.parametrize("mutation", ["missing", "reordered", "wrong_stage", "wrong_round"])
def test_s13_rejects_incomplete_or_malformed_role_reversal_trace(mutation):
    prompt, extraction, _, _ = fixture()
    outputs = list(_s13_complete_trace())
    if mutation == "missing":
        outputs.pop(2)
    elif mutation == "reordered":
        outputs[1], outputs[2] = outputs[2], outputs[1]
    elif mutation == "wrong_stage":
        item = outputs[2]
        outputs[2] = ProtocolOutput(item.step_index, item.agent_id, item.round, 2,
                                    item.action, item.text, item.model_invoked, item.from_seed)
    else:
        item = outputs[3]
        outputs[3] = ProtocolOutput(item.step_index, item.agent_id, 2, item.stage,
                                    item.action, item.text, item.model_invoked, item.from_seed)
    with pytest.raises(StrategyDecisionError):
        ProtocolDecisionDecoder(prompt, extraction)(
            StrategyId.S13, run_s13(*outputs),
        )


def test_s13_requires_typed_objections_in_both_roles_and_exact_roster():
    prompt, extraction, _, _ = fixture()
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    outputs = list(_s13_complete_trace())
    outputs[1] = ProtocolOutput(
        1, "agent-B", 1, 2, "critique", json.dumps({"objections": []}), True, False,
    )
    with pytest.raises(StrategyDecisionError, match="agent-B must provide typed objections"):
        decoder(StrategyId.S13, run_s13(*outputs))
    with pytest.raises(StrategyDecisionError, match="configured roster"):
        decoder(StrategyId.S13, run_s13(
            *_s13_complete_trace(), expected_agent_ids=("agent-A", "agent-B", "agent-C"),
        ))



def test_s11_rejects_invalid_stage_order_round_and_roster():
    prompt, extraction, d, _ = fixture()
    outputs = (
        ProtocolOutput(0, "party-1", 1, 1, "draft", json.dumps({"candidate": fixture()[3]}), True, False),
        ProtocolOutput(1, "party-2", 1, 1, "draft", json.dumps({"candidate": fixture()[3]}), True, False),
        ProtocolOutput(2, "mediator", 1, 2, "summarise", json.dumps({
            "summary": "Both want reliable access but disagree on cost.",
            "agreements": ["reliable access"], "disagreements": ["cost allocation"],
        }), True, False),
        ProtocolOutput(3, "party-1", 1, 3, "revise", json.dumps({"candidate": fixture()[3]}), True, False),
        ProtocolOutput(4, "party-2", 1, 3, "revise", json.dumps({"candidate": fixture()[3]}), True, False),
    )
    decoder = ProtocolDecisionDecoder(prompt, extraction, adjudications={
        StrategyId.S11: DecisionAdjudication(
            negotiated_decomposition=d, rationale="Parties accepted the joint draft",
        ),
    })
    valid = StrategyRun("S11", outputs, 5, 3, (), ("party-1", "party-2", "mediator"))
    assert decoder(StrategyId.S11, valid).decision.rule == "compromise"
    wrong_stage = list(outputs)
    item = wrong_stage[4]
    wrong_stage[4] = ProtocolOutput(item.step_index, item.agent_id, item.round, 2,
                                    item.action, item.text, item.model_invoked, item.from_seed)
    with pytest.raises(StrategyDecisionError, match="summary stage followed by parallel revision stage"):
        decoder(StrategyId.S11, StrategyRun("S11", tuple(wrong_stage), 5, 3, (),
                                            ("party-1", "party-2", "mediator")))
    wrong_round = list(outputs)
    item = wrong_round[4]
    wrong_round[4] = ProtocolOutput(item.step_index, item.agent_id, 2, item.stage,
                                    item.action, item.text, item.model_invoked, item.from_seed)
    with pytest.raises(StrategyDecisionError, match="S11 round 1 requires"):
        decoder(StrategyId.S11, StrategyRun("S11", tuple(wrong_round), 5, 3, (),
                                            ("party-1", "party-2", "mediator")))
    with pytest.raises(StrategyDecisionError, match="configured roster"):
        decoder(StrategyId.S11, StrategyRun("S11", outputs, 5, 3, (),
                                            ("party-1", "party-2")))


def test_s11_requires_mediator_summary_to_state_agreements_or_disagreements():
    prompt, extraction, d, _ = fixture()
    outputs = (
        ProtocolOutput(0, "party-1", 1, 1, "draft", json.dumps({"candidate": fixture()[3]}), True, False),
        ProtocolOutput(1, "party-2", 1, 1, "draft", json.dumps({"candidate": fixture()[3]}), True, False),
        ProtocolOutput(2, "mediator", 1, 2, "summarise", json.dumps({"summary": "There are differences."}), True, False),
        ProtocolOutput(3, "party-1", 1, 3, "revise", json.dumps({"candidate": fixture()[3]}), True, False),
        ProtocolOutput(4, "party-2", 1, 3, "revise", json.dumps({"candidate": fixture()[3]}), True, False),
    )
    decoder = ProtocolDecisionDecoder(prompt, extraction, adjudications={
        StrategyId.S11: DecisionAdjudication(
            negotiated_decomposition=d, rationale="Agreed joint plan",
        ),
    })
    with pytest.raises(StrategyDecisionError, match="agreements or disagreements"):
        decoder(StrategyId.S11, StrategyRun(
            "S11", outputs, 5, 3, (), ("party-1", "party-2", "mediator"),
        ))



def _s10_round_trace(rounds=1, participants=("participant-1", "participant-2")):
    outputs = []
    index = 0
    for round_number in range(1, rounds + 1):
        for participant in participants:
            outputs.append(ProtocolOutput(
                index, participant, round_number, index + 1, "revise",
                json.dumps({"candidate": fixture()[3]}), True, False,
            ))
            index += 1
    outputs.append(ProtocolOutput(
        index, "moderator", rounds, index + 1, "judge",
        json.dumps({"no_objection": True,
                    "rationale": "No participant objects to the shared draft."}),
        True, False,
    ))
    return tuple(outputs)


def test_s10_validates_sequential_shared_deliberation_rounds_and_final_closure():
    prompt, extraction, _, _ = fixture()
    outputs = _s10_round_trace(rounds=2)
    strategy_run = StrategyRun(
        "S10", outputs, len(outputs), len(outputs), (),
        ("participant-1", "participant-2", "moderator"),
    )
    result = ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S10, strategy_run)
    assert result.decision.rule == "consensus"
    assert result.decision.selected_candidate_id == "participant-2"


@pytest.mark.parametrize("mutation", ["missing_turn", "reordered", "early_moderator", "wrong_stage"])
def test_s10_rejects_incomplete_or_nonsequential_deliberation(mutation):
    prompt, extraction, _, _ = fixture()
    outputs = list(_s10_round_trace(rounds=1))
    if mutation == "missing_turn":
        outputs.pop(1)
    elif mutation == "reordered":
        outputs[0], outputs[1] = outputs[1], outputs[0]
    elif mutation == "early_moderator":
        outputs.insert(1, outputs.pop())
    else:
        item = outputs[1]
        outputs[1] = ProtocolOutput(item.step_index, item.agent_id, item.round, 1,
                                    item.action, item.text, item.model_invoked, item.from_seed)
    run_value = StrategyRun(
        "S10", tuple(outputs), len(outputs), len({x.stage for x in outputs}), (),
        ("participant-1", "participant-2", "moderator"),
    )
    with pytest.raises(StrategyDecisionError):
        ProtocolDecisionDecoder(prompt, extraction)(StrategyId.S10, run_value)


def test_s10_rejects_missing_moderator_or_wrong_configured_roster():
    prompt, extraction, _, _ = fixture()
    outputs = _s10_round_trace()
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    with pytest.raises(StrategyDecisionError, match="final moderator closure"):
        decoder(StrategyId.S10, StrategyRun(
            "S10", outputs[:-1], len(outputs) - 1, 2, (),
            ("participant-1", "participant-2", "moderator"),
        ))
    with pytest.raises(StrategyDecisionError, match="include the moderator"):
        decoder(StrategyId.S10, StrategyRun(
            "S10", outputs, len(outputs), 3, (), ("participant-1", "participant-2"),
        ))



def _s11_iterative_trace(rounds=2):
    outputs = [
        ProtocolOutput(0, "party-1", 1, 1, "draft",
                       json.dumps({"candidate": fixture()[3]}), True, False),
        ProtocolOutput(1, "party-2", 1, 1, "draft",
                       json.dumps({"candidate": fixture()[3]}), True, False),
    ]
    index = 2
    for round_number in range(1, rounds + 1):
        summary_stage = 2 * round_number
        for agent_id, action, stage in (
            ("mediator", "summarise", summary_stage),
            ("party-1", "revise", summary_stage + 1),
            ("party-2", "revise", summary_stage + 1),
        ):
            if action == "summarise":
                payload = {
                    "summary": f"Neutral mediation summary round {round_number}",
                    "agreements": ["Shared objective"],
                    "disagreements": ["Task order"],
                }
            else:
                payload = {"candidate": fixture()[3]}
            outputs.append(ProtocolOutput(
                index, agent_id, round_number, stage, action,
                json.dumps(payload), True, False,
            ))
            index += 1
    return tuple(outputs)


def test_s11_validates_multiple_complete_mediation_rounds():
    prompt, extraction, d, _ = fixture()
    outputs = _s11_iterative_trace(rounds=3)
    run_value = StrategyRun(
        "S11", outputs, len(outputs), 7, (),
        ("party-1", "party-2", "mediator"),
    )
    decoder = ProtocolDecisionDecoder(prompt, extraction, adjudications={
        StrategyId.S11: DecisionAdjudication(
            negotiated_decomposition=d,
            rationale="The parties accepted the explicit negotiated decomposition.",
        ),
    })
    result = decoder(StrategyId.S11, run_value)
    assert result.decision.rule == "compromise"


@pytest.mark.parametrize("mutation", ["missing_party_turn", "missing_summary_evidence", "wrong_round", "wrong_stage"])
def test_s11_rejects_incomplete_iterative_rounds(mutation):
    prompt, extraction, d, _ = fixture()
    outputs = list(_s11_iterative_trace(rounds=2))
    if mutation == "missing_party_turn":
        outputs.pop(7)
    elif mutation == "missing_summary_evidence":
        item = outputs[5]
        outputs[5] = ProtocolOutput(
            item.step_index, item.agent_id, item.round, item.stage, item.action,
            json.dumps({"summary": "No explicit agreement or disagreement"}),
            item.model_invoked, item.from_seed,
        )
    elif mutation == "wrong_round":
        item = outputs[5]
        outputs[5] = ProtocolOutput(item.step_index, item.agent_id, 3, item.stage,
                                    item.action, item.text, item.model_invoked, item.from_seed)
    else:
        item = outputs[6]
        outputs[6] = ProtocolOutput(item.step_index, item.agent_id, item.round, item.stage - 1,
                                    item.action, item.text, item.model_invoked, item.from_seed)
    run_value = StrategyRun(
        "S11", tuple(outputs), len(outputs), 5, (),
        ("party-1", "party-2", "mediator"),
    )
    decoder = ProtocolDecisionDecoder(prompt, extraction, adjudications={
        StrategyId.S11: DecisionAdjudication(
            negotiated_decomposition=d, rationale="Explicit negotiation result",
        ),
    })
    with pytest.raises(StrategyDecisionError):
        decoder(StrategyId.S11, run_value)


def _s13_complete_trace():
    raw = fixture()[3]
    return (
        ProtocolOutput(0, "agent-A", 1, 1, "draft", json.dumps({"candidate": raw}), True, False),
        ProtocolOutput(1, "agent-B", 1, 2, "critique", json.dumps({
            "objections": [{"kind": "missing_subproblem", "subject": "s1",
                            "rationale": "The initial plan omits a required component."}]
        }), True, False),
        ProtocolOutput(2, "agent-B", 1, 3, "revise", json.dumps({"candidate": raw}), True, False),
        ProtocolOutput(3, "agent-A", 1, 4, "critique", json.dumps({
            "objections": [{"kind": "hidden_dependency", "subject": "s1",
                            "rationale": "The repaired plan does not justify the prerequisite."}]
        }), True, False),
    )


def run_s13(*outputs, expected_agent_ids=("agent-A", "agent-B")):
    return StrategyRun("S13", tuple(outputs), len(outputs), 4, (), expected_agent_ids)


def test_s13_role_reversal_returns_b_repaired_candidate_after_a_final_critique():
    prompt, extraction, _, _ = fixture()
    result = ProtocolDecisionDecoder(prompt, extraction)(
        StrategyId.S13, run_s13(*_s13_complete_trace()),
    )
    assert result.decision.rule == "authority"
    assert result.decision.selected_candidate_id == "agent-B"


@pytest.mark.parametrize("mutation", ["missing", "reordered", "wrong_stage", "wrong_round"])
def test_s13_rejects_incomplete_or_malformed_role_reversal_trace(mutation):
    prompt, extraction, _, _ = fixture()
    outputs = list(_s13_complete_trace())
    if mutation == "missing":
        outputs.pop(2)
    elif mutation == "reordered":
        outputs[1], outputs[2] = outputs[2], outputs[1]
    elif mutation == "wrong_stage":
        item = outputs[2]
        outputs[2] = ProtocolOutput(item.step_index, item.agent_id, item.round, 2,
                                    item.action, item.text, item.model_invoked, item.from_seed)
    else:
        item = outputs[3]
        outputs[3] = ProtocolOutput(item.step_index, item.agent_id, 2, item.stage,
                                    item.action, item.text, item.model_invoked, item.from_seed)
    with pytest.raises(StrategyDecisionError):
        ProtocolDecisionDecoder(prompt, extraction)(
            StrategyId.S13, run_s13(*outputs),
        )


def test_s13_requires_typed_objections_in_both_roles_and_exact_roster():
    prompt, extraction, _, _ = fixture()
    decoder = ProtocolDecisionDecoder(prompt, extraction)
    outputs = list(_s13_complete_trace())
    outputs[1] = ProtocolOutput(
        1, "agent-B", 1, 2, "critique", json.dumps({"objections": []}), True, False,
    )
    with pytest.raises(StrategyDecisionError, match="agent-B must provide typed objections"):
        decoder(StrategyId.S13, run_s13(*outputs))
    with pytest.raises(StrategyDecisionError, match="configured roster"):
        decoder(StrategyId.S13, run_s13(
            *_s13_complete_trace(), expected_agent_ids=("agent-A", "agent-B", "agent-C"),
        ))
