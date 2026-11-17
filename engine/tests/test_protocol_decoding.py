import json
import pytest
from sociodec.extraction import ExtractionResult, Hypothesis, aggregate_extractions
from sociodec.models.prompt import Constraint, ConstraintKind, Interpretation, Prompt, Requirement, RequirementType, SourceSpan
from sociodec.protocol_decoding import ObjectionKind, ProtocolDecodeError, parse_candidate, parse_hypothesis_verdicts, parse_protocol_output
from sociodec.runtime import ProtocolOutput


def fixtures():
    text = "Build an accessible service within budget."
    requirement = Requirement("Build accessible service", RequirementType.TARGET, "service", SourceSpan(0, len(text)))
    hypothesis = Hypothesis("Provide an appeal route", RequirementType.DELIVERABLE, "legal", "Public services often require review.")
    constraint = Constraint("Within budget", ConstraintKind.HARD)
    prompt = Prompt(text, Interpretation("Build service", constraints=(constraint,), deliverables=("Service plan",)))
    extraction = aggregate_extractions((ExtractionResult(requirements=(requirement,), hypotheses=(hypothesis,), extractor_id="extractor-1"),))
    candidate = {
        "candidate_id": "draft-A",
        "subproblems": [{
            "id": "s1", "question": "Design accessible service",
            "inputs": ["service requirements"], "output": "Service plan",
            "local_constraints": [{"kind": "hard", "statement": "Within budget"}],
            "covered_requirements": [{"type": "target", "domain": "service", "statement": "Build accessible service"}],
        }],
        "dependencies": [], "kappa": {"Service plan": ["s1"]},
    }
    return prompt, extraction, candidate, hypothesis


def output(action, payload):
    return ProtocolOutput(0, "agent-1", 1, 1, action, json.dumps(payload), True, False)


def test_candidate_decodes_to_typed_decomposition_and_exact_source_references():
    prompt, extraction, raw, _ = fixtures()
    candidate = parse_candidate(raw, prompt=prompt, extraction=extraction)
    assert candidate.identifier == "draft-A"
    assert candidate.decomposition.subproblems[0].covered_requirements == extraction.requirements
    assert candidate.decomposition.subproblems[0].local_constraints == prompt.iota.constraints
    assert candidate.decomposition.kappa == {"Service plan": frozenset({"s1"})}


def test_candidate_rejects_requirement_not_in_aggregated_extraction():
    prompt, extraction, raw, _ = fixtures()
    raw["subproblems"][0]["covered_requirements"][0]["statement"] = "Invented requirement"
    with pytest.raises(ProtocolDecodeError, match="outside aggregated"):
        parse_candidate(raw, prompt=prompt, extraction=extraction)


def test_candidate_rejects_constraint_not_in_prompt():
    prompt, extraction, raw, _ = fixtures()
    raw["subproblems"][0]["local_constraints"][0]["statement"] = "Invented constraint"
    with pytest.raises(ProtocolDecodeError, match="outside prompt C"):
        parse_candidate(raw, prompt=prompt, extraction=extraction)


def test_candidate_rejects_dangling_dependency_and_unknown_composition_reference():
    prompt, extraction, raw, _ = fixtures()
    raw["dependencies"] = [{"source": "missing", "target": "s1"}]
    with pytest.raises(ProtocolDecodeError, match="Invalid decomposition"):
        parse_candidate(raw, prompt=prompt, extraction=extraction)
    raw["dependencies"] = []
    raw["kappa"] = {"Service plan": ["missing"]}
    with pytest.raises(ProtocolDecodeError, match="Invalid decomposition"):
        parse_candidate(raw, prompt=prompt, extraction=extraction)


def test_candidate_rejects_missing_declared_deliverable_key():
    prompt, extraction, raw, _ = fixtures()
    raw["kappa"] = {}
    with pytest.raises(ProtocolDecodeError, match="missing deliverable"):
        parse_candidate(raw, prompt=prompt, extraction=extraction)


def test_hypothesis_verdict_parser_requires_exact_extracted_hypothesis():
    _, extraction, _, hypothesis = fixtures()
    parsed = parse_hypothesis_verdicts([{
        "type": "deliverable", "domain": "legal", "statement": hypothesis.statement, "verdict": "confirmed",
    }], extraction)
    assert parsed[0].hypothesis == hypothesis
    assert parsed[0].verdict.value == "confirmed"
    with pytest.raises(ProtocolDecodeError, match="outside H-hat"):
        parse_hypothesis_verdicts([{
            "type": "deliverable", "domain": "legal", "statement": "invented", "verdict": "confirmed",
        }], extraction)


def test_hypothesis_verdict_parser_rejects_duplicate_verdicts():
    _, extraction, _, hypothesis = fixtures()
    item = {"type": "deliverable", "domain": "legal", "statement": hypothesis.statement, "verdict": "confirmed"}
    with pytest.raises(ProtocolDecodeError, match="Duplicate"):
        parse_hypothesis_verdicts([item, item], extraction)


def test_candidate_protocol_output_is_decoded():
    prompt, extraction, raw, _ = fixtures()
    message = parse_protocol_output(output("draft", {"candidate": raw}), prompt=prompt, extraction=extraction)
    assert message.action == "draft"
    assert message.candidate.identifier == "draft-A"


def test_critique_output_uses_only_typed_objection_categories():
    prompt, extraction, _, _ = fixtures()
    message = parse_protocol_output(output("critique", {"objections": [{
        "kind": "hidden_dependency", "subject": "s1 -> s2",
        "rationale": "The data agreement must precede exchange.",
    }]}), prompt=prompt, extraction=extraction)
    assert message.objections[0].kind is ObjectionKind.HIDDEN_DEPENDENCY
    with pytest.raises(ProtocolDecodeError, match="Invalid objection"):
        parse_protocol_output(output("critique", {"objections": [{
            "kind": "unsupported", "subject": "x", "rationale": "why",
        }]}), prompt=prompt, extraction=extraction)


def test_rank_vote_judge_summary_split_and_defence_actions_decode():
    prompt, extraction, _, _ = fixtures()
    rank = parse_protocol_output(output("rank", {"ranking": ["A", "B"]}), prompt=prompt, extraction=extraction)
    assert rank.ranking == ("A", "B")
    with pytest.raises(ProtocolDecodeError, match="duplicate"):
        parse_protocol_output(output("rank", {"ranking": ["A", "A"]}), prompt=prompt, extraction=extraction)
    vote = parse_protocol_output(output("vote", {"endorsed_subproblems": [{"candidate_id": "A", "subproblem_id": "s1"}]}), prompt=prompt, extraction=extraction)
    assert vote.endorsed_subproblems == (("A", "s1"),)
    judge = parse_protocol_output(output("judge", {"selected_candidate_id": "A", "rationale": "Best coverage."}), prompt=prompt, extraction=extraction)
    assert judge.selected_candidate_id == "A"
    summary = parse_protocol_output(output("summarise", {
        "summary": "The drafts differ on sequencing.", "agreements": ["Accessible service"],
        "disagreements": ["Review before deployment"],
    }), prompt=prompt, extraction=extraction)
    assert summary.agreements == ("Accessible service",)
    split = parse_protocol_output(output("split", {"partitions": {"specialist-1": "Legal", "specialist-2": "Technical"}}), prompt=prompt, extraction=extraction)
    assert split.partitions[0] == ("specialist-1", "Legal")
    defence = parse_protocol_output(output("defend", {"defence": "This plan preserves independent review."}), prompt=prompt, extraction=extraction)
    assert defence.rationale.startswith("This plan")


def test_parser_rejects_malformed_json_and_unknown_action():
    prompt, extraction, _, _ = fixtures()
    malformed = ProtocolOutput(0, "a", 1, 1, "draft", "{bad", True, False)
    with pytest.raises(ProtocolDecodeError, match="Invalid JSON"):
        parse_protocol_output(malformed, prompt=prompt, extraction=extraction)
    unknown = ProtocolOutput(0, "a", 1, 1, "unknown", "{}", True, False)
    with pytest.raises(ProtocolDecodeError, match="Unsupported action"):
        parse_protocol_output(unknown, prompt=prompt, extraction=extraction)
