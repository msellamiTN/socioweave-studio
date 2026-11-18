"""Strict protocol JSON decoding into paper-aligned typed objects."""
from __future__ import annotations
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from sociodec.decisions import Candidate
from sociodec.extraction import AggregatedExtraction, _normalise
from sociodec.models.decomposition import Decomposition, Subproblem, Dependency, DeliverableComposition
from sociodec.models.prompt import Prompt, RequirementType, ConstraintKind
from sociodec.runtime import ProtocolOutput
from sociodec.validation import HypothesisVerdict, HypothesisVerdictValue

class ProtocolDecodeError(ValueError):
    pass

class PeerReviewVerdict(StrEnum):
    ACCEPT = "accept"
    REVISE = "revise"

class ObjectionKind(StrEnum):
    MISSING_SUBPROBLEM = "missing_subproblem"
    REDUNDANT_SUBPROBLEM = "redundant_subproblem"
    HIDDEN_DEPENDENCY = "hidden_dependency"

@dataclass(frozen=True, slots=True)
class TypedObjection:
    kind: ObjectionKind
    subject: str
    rationale: str

@dataclass(frozen=True, slots=True)
class ProtocolMessage:
    action: str
    candidate: Candidate | None = None
    objections: tuple[TypedObjection, ...] = ()
    ranking: tuple[str, ...] = ()
    endorsed_subproblems: tuple[tuple[str, str], ...] = ()
    selected_candidate_id: str | None = None
    rationale: str = ""
    summary: str = ""
    agreements: tuple[str, ...] = ()
    disagreements: tuple[str, ...] = ()
    partitions: tuple[tuple[str, str], ...] = ()
    hypothesis_verdicts: tuple[HypothesisVerdict, ...] = ()
    peer_review_verdict: PeerReviewVerdict | None = None

def _obj(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise ProtocolDecodeError(f"{label} must be an object")
    return value

def _str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolDecodeError(f"{label} must be a non-empty string")
    return value

def _strings(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ProtocolDecodeError(f"{label} must be an array")
    return tuple(_str(x, f"{label}[{i}]") for i, x in enumerate(value))

def _json(text: str) -> dict:
    try:
        return _obj(json.loads(text.strip()), "response root")
    except json.JSONDecodeError as exc:
        raise ProtocolDecodeError(f"Invalid JSON: {exc}") from exc

def parse_candidate(value: Any, *, prompt: Prompt, extraction: AggregatedExtraction,
                    candidate_id: str | None = None) -> Candidate:
    data = _obj(value, "candidate")
    cid = candidate_id or _str(data.get("candidate_id"), "candidate_id")
    reqs = {(r.type.value, r.domain, _normalise(r.statement)): r for r in extraction.requirements}
    constraints = {(c.kind.value, _normalise(c.statement)): c for c in prompt.iota.constraints}
    raw_s, raw_e = data.get("subproblems"), data.get("dependencies")
    raw_k = _obj(data.get("kappa"), "kappa")
    if not isinstance(raw_s, list) or not isinstance(raw_e, list):
        raise ProtocolDecodeError("subproblems and dependencies must be arrays")
    subproblems = []
    for i, raw in enumerate(raw_s):
        item = _obj(raw, f"subproblems[{i}]")
        cov, local = item.get("covered_requirements", []), item.get("local_constraints", [])
        if not isinstance(cov, list) or not isinstance(local, list):
            raise ProtocolDecodeError("coverage and local constraints must be arrays")
        covered, local_constraints = [], []
        for ref in cov:
            ref = _obj(ref, "requirement reference")
            try:
                key = (RequirementType(_str(ref.get("type"), "requirement.type")).value,
                       _str(ref.get("domain"), "requirement.domain"),
                       _normalise(_str(ref.get("statement"), "requirement.statement")))
            except ValueError as exc:
                raise ProtocolDecodeError(f"Invalid requirement reference: {exc}") from exc
            if key not in reqs:
                raise ProtocolDecodeError("Requirement reference is outside aggregated R-hat")
            covered.append(reqs[key])
        for ref in local:
            ref = _obj(ref, "constraint reference")
            try:
                key = (ConstraintKind(_str(ref.get("kind"), "constraint.kind")).value,
                       _normalise(_str(ref.get("statement"), "constraint.statement")))
            except ValueError as exc:
                raise ProtocolDecodeError(f"Invalid constraint reference: {exc}") from exc
            if key not in constraints:
                raise ProtocolDecodeError("Constraint reference is outside prompt C")
            local_constraints.append(constraints[key])
        subproblems.append(Subproblem(
            _str(item.get("id"), "subproblem.id"),
            _str(item.get("question"), "subproblem.question"),
            _strings(item.get("inputs", []), "subproblem.inputs"),
            _str(item.get("output"), "subproblem.output"),
            tuple(local_constraints), tuple(covered)))
    dependencies = []
    for i, raw in enumerate(raw_e):
        item = _obj(raw, f"dependencies[{i}]")
        dependencies.append(Dependency(_str(item.get("source"), "dependency.source"),
                                       _str(item.get("target"), "dependency.target")))
    composition = tuple(DeliverableComposition(
        _str(key, "deliverable key"), _strings(value, "kappa contributor list"))
        for key, value in raw_k.items())
    try:
        d = Decomposition(tuple(subproblems), tuple(dependencies), composition)
        d.validate_against(prompt, extraction.requirements)
    except (TypeError, ValueError) as exc:
        raise ProtocolDecodeError(f"Invalid decomposition: {exc}") from exc
    return Candidate(cid, d)

def parse_hypothesis_verdicts(value: Any, extraction: AggregatedExtraction):
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ProtocolDecodeError("hypothesis_verdicts must be an array")
    index = {(h.type.value, h.domain, _normalise(h.statement)): h for h in extraction.hypotheses}
    result = []
    for raw in value:
        item = _obj(raw, "hypothesis verdict")
        try:
            key = (RequirementType(_str(item.get("type"), "verdict.type")).value,
                   _str(item.get("domain"), "verdict.domain"),
                   _normalise(_str(item.get("statement"), "verdict.statement")))
            verdict = HypothesisVerdictValue(_str(item.get("verdict"), "verdict.value"))
        except ValueError as exc:
            raise ProtocolDecodeError(f"Invalid hypothesis verdict: {exc}") from exc
        if key not in index:
            raise ProtocolDecodeError("Verdict references a hypothesis outside H-hat")
        result.append(HypothesisVerdict(index[key], verdict))
    if len({x.hypothesis for x in result}) != len(result):
        raise ProtocolDecodeError("Duplicate hypothesis verdict")
    return tuple(result)

def parse_protocol_output(output: ProtocolOutput, *, prompt: Prompt,
                          extraction: AggregatedExtraction,
                          candidate_id: str | None = None) -> ProtocolMessage:
    data = _json(output.text)
    action = output.action
    candidate, objections, ranking, ballots, partitions = None, (), (), (), ()
    selected, rationale, summary = None, "", ""
    peer_review_verdict = None
    agreements, disagreements = (), ()
    if action in {"draft", "revise", "counter_plan", "merge", "check"}:
        candidate = parse_candidate(data.get("candidate", data), prompt=prompt, extraction=extraction, candidate_id=candidate_id)
    elif action == "critique":
        raw = data.get("objections")
        if not isinstance(raw, list):
            raise ProtocolDecodeError("objections must be an array")
        parsed = []
        for x in raw:
            x = _obj(x, "objection")
            try:
                parsed.append(TypedObjection(
                    ObjectionKind(_str(x.get("kind"), "objection.kind")),
                    _str(x.get("subject"), "objection.subject"),
                    _str(x.get("rationale"), "objection.rationale")))
            except ValueError as exc:
                raise ProtocolDecodeError(f"Invalid objection: {exc}") from exc
        objections = tuple(parsed)
    elif action == "rank":
        ranking = _strings(data.get("ranking"), "ranking")
        if len(set(ranking)) != len(ranking):
            raise ProtocolDecodeError("ranking contains duplicate candidate ids")
    elif action == "vote":
        raw = data.get("endorsed_subproblems")
        if not isinstance(raw, list):
            raise ProtocolDecodeError("endorsed_subproblems must be an array")
        ballots = tuple((_str(_obj(x, "ballot").get("candidate_id"), "candidate_id"),
                         _str(x.get("subproblem_id"), "subproblem_id")) for x in raw)
        if len(set(ballots)) != len(ballots):
            raise ProtocolDecodeError("Duplicate ballot reference")
    elif action == "judge":
        rationale = _str(data.get("rationale"), "rationale")
        if "verdict" in data:
            try:
                peer_review_verdict = PeerReviewVerdict(_str(data.get("verdict"), "verdict"))
            except ValueError as exc:
                raise ProtocolDecodeError("Invalid peer-review verdict; expected accept or revise") from exc
        else:
            selected = _str(data.get("selected_candidate_id"), "selected_candidate_id")
    elif action == "summarise":
        summary = _str(data.get("summary"), "summary")
        agreements = _strings(data.get("agreements", []), "agreements")
        disagreements = _strings(data.get("disagreements", []), "disagreements")
    elif action == "split":
        raw = _obj(data.get("partitions"), "partitions")
        partitions = tuple((_str(k, "agent id"), _str(v, "partition")) for k, v in raw.items())
        if not partitions:
            raise ProtocolDecodeError("partitions must not be empty")
    elif action == "defend":
        rationale = _str(data.get("defence"), "defence")
    else:
        raise ProtocolDecodeError(f"Unsupported action: {action}")
    verdicts = parse_hypothesis_verdicts(data.get("hypothesis_verdicts"), extraction)
    return ProtocolMessage(action, candidate, objections, ranking, ballots, selected,
                           rationale, summary, agreements, disagreements, partitions, verdicts, peer_review_verdict)
