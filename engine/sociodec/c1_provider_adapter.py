"""Provider-backed callbacks for paper-faithful C1 execution.

The executor owns phase ordering and bounded retries. This adapter owns prompt
construction, provider routing, strict decoding, and provider-call traces.
Author revisions receive only their own candidate plus anonymous objections.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Mapping

from sociodec.algorithm3_c1 import C1Callbacks, AnonymousObjections, AnonymousObjection
from sociodec.c1_decoding import parse_anonymous_objections_json, parse_c1_judge_json
from sociodec.decisions import Candidate
from sociodec.extraction import AggregatedExtraction
from sociodec.models.decomposition import Decomposition
from sociodec.models.prompt import Prompt
from sociodec.protocol_decoding import parse_candidate
from sociodec.providers.base import ChatMessage, GenerationConfig, LLMProvider


@dataclass(frozen=True, slots=True)
class C1ProviderTrace:
    phase: str
    model_id: str
    model_family: str
    provider: str
    returned_model: str
    latency_ms: float
    input_sha256: str
    output_sha256: str


class C1ProviderAdapter:
    """Create strict C1 callbacks from configured providers and model families.

    model_ids maps actor IDs to model IDs; model_families maps model IDs to
    family labels. The judge family is checked by Algorithm3C1Executor itself.
    """

    def __init__(
        self,
        *,
        prompt: Prompt,
        extraction: AggregatedExtraction,
        providers: Mapping[str, LLMProvider],
        model_ids: Mapping[str, str],
        model_families: Mapping[str, str],
        generation: GenerationConfig | None = None,
    ) -> None:
        if not providers or set(providers) != set(model_ids.values()):
            raise ValueError("providers must be configured for every referenced model_id")
        if set(model_ids.values()) - set(model_families):
            raise ValueError("every model_id needs a configured family")
        if any(not actor.strip() or not model.strip() for actor, model in model_ids.items()):
            raise ValueError("actor/model identifiers must be non-empty")
        self.prompt = prompt
        self.extraction = extraction
        self.providers = dict(providers)
        self.model_ids = dict(model_ids)
        self.model_families = dict(model_families)
        self.generation = generation or GenerationConfig(temperature=0.0, response_format="json")
        self.traces: list[C1ProviderTrace] = []

    def _invoke(self, phase: str, actor: str, prompt_text: str) -> str:
        model_id = self.model_ids[actor]
        provider = self.providers[model_id]
        family = self.model_families[model_id]
        messages = [
            ChatMessage("system", "Return only valid JSON matching the requested schema. Do not include markdown fences."),
            ChatMessage("user", prompt_text),
        ]
        started = time.perf_counter()
        result = provider.generate(messages, self.generation)
        latency = (time.perf_counter() - started) * 1000
        if not result.text.strip():
            raise ValueError(f"{phase} provider returned empty output")
        self.traces.append(C1ProviderTrace(
            phase, model_id, family, result.provider, result.model,
            round(latency, 3),
            hashlib.sha256(prompt_text.encode()).hexdigest(),
            hashlib.sha256(result.text.encode()).hexdigest(),
        ))
        return result.text

    def _candidate(self, actor: str, phase: str, instruction: str) -> Candidate:
        output = self._invoke(phase, actor, instruction)
        try:
            data = json.loads(output)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{phase} output must be JSON") from exc
        if not isinstance(data, dict):
            raise ValueError(f"{phase} JSON root must be object")
        candidate_payload = data.get("candidate", data)
        return parse_candidate(candidate_payload, prompt=self.prompt, extraction=self.extraction, candidate_id=actor)

    def callbacks(self, *, comparator_actor: str, synthesizer_actor: str, judge_actor: str,
                  algorithm1_check_and_repair) -> C1Callbacks[Candidate, Decomposition, Decomposition]:
        author_ids = tuple(actor for actor in self.model_ids if actor not in {
            comparator_actor, synthesizer_actor, judge_actor
        })

        def draft(actor: str) -> Candidate:
            return self._candidate(actor, "gen", (
                "Produce an independent decomposition for the task below. Do not consult other drafts. "
                "Return JSON with candidate containing subproblems, dependencies, and kappa.\n"
                f"Task: {self.prompt.text}\nExtraction: {self._extraction_text()}"
            ))

        def compare(candidates: Mapping[str, Candidate]) -> AnonymousObjections:
            anonymized = [
                {"candidate_label": f"draft-{i+1}", "decomposition": self._decomposition_payload(c.decomposition)}
                for i, c in enumerate(candidates.values())
            ]
            text = self._invoke("exa", comparator_actor, (
                "Compare the anonymous candidate decompositions and return JSON "
                '{"objections":[{"code":"...","statement":"...","evidence":"optional"}]}. '
                "Do not mention or infer authors.\nCandidates:\n" + json.dumps(anonymized, ensure_ascii=False)
            ))
            return parse_anonymous_objections_json(text, author_ids=author_ids)

        def revise(actor: str, own: Candidate, objections: AnonymousObjections) -> Candidate:
            own_payload = self._decomposition_payload(own.decomposition)
            objection_payload = [{"code": x.code, "statement": x.statement, "evidence": x.evidence}
                                for x in objections.items]
            return self._candidate(actor, "rev", (
                "Revise only your own candidate in response to anonymous objections. "
                "Peer candidates and author identities are not provided. Return candidate JSON.\n"
                "Your candidate:\n" + json.dumps(own_payload, ensure_ascii=False) +
                "\nAnonymous objections:\n" + json.dumps(objection_payload, ensure_ascii=False)
            ))

        def merge(candidates: Mapping[str, Candidate]) -> Decomposition:
            payload = [self._decomposition_payload(c.decomposition) for c in candidates.values()]
            candidate = self._candidate(synthesizer_actor, "merge", (
                "Merge these candidates into one decomposition. Return JSON with candidate containing "
                "subproblems, dependencies, and kappa.\nCandidates:\n" + json.dumps(payload, ensure_ascii=False)
            ))
            return candidate.decomposition

        def judge(candidate: Decomposition, candidates: Mapping[str, Candidate]):
            payload = {
                "merged": self._decomposition_payload(candidate),
                "candidate_pool": [self._decomposition_payload(c.decomposition) for c in candidates.values()],
            }
            text = self._invoke("dec", judge_actor, (
                "Evaluate the merged decomposition. Return exactly JSON: accept as "
                '{"verdict":"accept"} or reject with typed objections as '
                '{"verdict":"reject","objections":[{"code":"...","statement":"...","evidence":"optional"}]}. '
                "Do not include author identities.\n" + json.dumps(payload, ensure_ascii=False)
            ))
            return parse_c1_judge_json(text, author_ids=author_ids)

        def judge_revise(candidate: Decomposition, objections: AnonymousObjections) -> Decomposition:
            obj = [{"code": x.code, "statement": x.statement, "evidence": x.evidence}
                    for x in objections.items]
            revised = self._candidate(synthesizer_actor, "judge-revision", (
                "Revise the merged decomposition once using these judge objections. Return candidate JSON.\n"
                "Candidate:\n" + json.dumps(self._decomposition_payload(candidate), ensure_ascii=False) +
                "\nObjections:\n" + json.dumps(obj, ensure_ascii=False)
            ))
            return revised.decomposition

        return C1Callbacks(
            draft=draft, compare=compare, revise=revise, merge=merge, judge=judge,
            judge_revise=judge_revise, check_and_repair=algorithm1_check_and_repair,
            distance=lambda left, right: _candidate_distance(left, right),
        )

    def _extraction_text(self) -> str:
        return json.dumps({
            "requirements": [{"type": x.type.value, "domain": x.domain, "statement": x.statement}
                            for x in self.extraction.requirements],
            "hypotheses": [{"type": x.type.value, "domain": x.domain, "statement": x.statement}
                           for x in self.extraction.hypotheses],
        }, ensure_ascii=False)

    @staticmethod
    def _decomposition_payload(d: Decomposition) -> dict:
        return {
            "subproblems": [{
                "id": s.identifier, "question": s.question, "inputs": list(s.inputs),
                "output": s.output,
                "local_constraints": [{"kind": c.kind.value, "statement": c.statement}
                                    for c in s.local_constraints],
                "covered_requirements": [{"type": r.type.value, "domain": r.domain,
                                       "statement": r.statement} for r in s.covered_requirements],
            } for s in d.subproblems],
            "dependencies": [{"source": a, "target": b} for a, b in sorted(d.E)],
            "kappa": {key: sorted(value) for key, value in d.kappa.items()},
        }


def _candidate_distance(left: Candidate, right: Candidate) -> float:
    """A normalized structural distance; heuristic, not a paper-defined metric."""
    a, b = left.decomposition, right.decomposition
    sa = {(s.identifier, s.question.strip().casefold()) for s in a.subproblems}
    sb = {(s.identifier, s.question.strip().casefold()) for s in b.subproblems}
    ea, eb = set(a.E), set(b.E)
    ka = {(key, frozenset(value)) for key, value in a.kappa.items()}
    kb = {(key, frozenset(value)) for key, value in b.kappa.items()}
    union = sa | sb | ea | eb | ka | kb
    if not union:
        return 0.0
    intersection = sa & sb | ea & eb | ka & kb
    return 1.0 - len(intersection) / len(union)
