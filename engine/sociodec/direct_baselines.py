"""Direct E1 baseline adapters under the explicit operational profile v1.

The paper names six baselines but leaves several protocol details open. This
module freezes those details as a versioned implementation profile; it does
not claim that these choices are specified by the paper.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Mapping

from sociodec.catalogue import StrategyId
from sociodec.decisions import decomposition_distance
from sociodec.direct_e1 import DirectMethodAdapter, MethodRun
from sociodec.e1_protocol import BASELINES, E1Condition
from sociodec.equivalence import DEFAULT_MATCHER, equivalence_classes
from sociodec.extraction import AggregatedExtraction
from sociodec.models.decomposition import (
    Decomposition, Dependency, DeliverableComposition, Subproblem,
)
from sociodec.models.prompt import Prompt
from sociodec.protocol_decoding import parse_candidate
from sociodec.providers.base import ChatMessage, GenerationConfig, LLMProvider

BaselineProviderResolver = Callable[[E1Condition, str], LLMProvider]

PROFILE_ID = "e1-baselines-operational-profile-v1"
PROFILE_STATUS = "implementation_choice_not_fully_specified_by_paper"

BASELINE_CHOICES = {
    "single_plan_and_solve": "One MA/selected-model call returns a complete typed plan-and-solve decomposition.",
    "single_self_refinement": "One draft call, one separate self-critique call, and one revision call.",
    "single_self_consistency": "Exactly condition.call_budget independent samples; retain equivalence classes occurring in a strict majority, or the maximum-frequency classes if no strict majority exists.",
    "decomposer_plus_evaluator": "One decomposer call followed by one separate evaluator call; evaluator validates but does not mutate the candidate.",
    "multi_agent_debate": "Two independent drafts, condition.call_budget-3 structured debate turns, then one independent judge call selecting one draft; minimum budget three.",
    "nominal_multi_agent": "Three isolated drafts; choose the draft with greatest coverage of extracted requirements; ties resolve by draft order.",
}


@dataclass(frozen=True, slots=True)
class _Call:
    agent_id: str
    role: str
    model_id: str
    response: str
    input_text: str


class DirectBaselineAdapter(DirectMethodAdapter):
    """Execute exactly one baseline from the frozen operational profile v1."""

    def __init__(
        self,
        *,
        extraction: AggregatedExtraction,
        provider_resolver: BaselineProviderResolver,
        n_nominal: int = 3,
        temperature_draft: float = 0.7,
        temperature_critique: float = 0.2,
        max_tokens_decomposition: int = 1024,
        max_tokens_other: int = 512,
    ) -> None:
        if n_nominal != 3:
            raise ValueError("Profile v1 fixes nominal_multi_agent to three independent drafts (Table 13 n=3)")
        self.extraction = extraction
        self.provider_resolver = provider_resolver
        self.n_nominal = n_nominal
        self.temperature_draft = temperature_draft
        self.temperature_critique = temperature_critique
        self.max_tokens_decomposition = max_tokens_decomposition
        self.max_tokens_other = max_tokens_other

    def run(self, *, condition: E1Condition, prompt: Prompt, seed: int) -> MethodRun:
        baseline_id = condition.method_id
        if baseline_id not in BASELINES:
            raise ValueError("DirectBaselineAdapter accepts only registered E1 baseline IDs")
        budget = condition.call_budget
        calls: list[_Call] = []
        model_ids: dict[str, str] = {}

        def invoke(agent_id: str, role: str, instruction: str, payload: Mapping[str, object],
                   *, temperature: float, max_tokens: int) -> str:
            provider = self.provider_resolver(condition, agent_id)
            model_id = provider.model_name
            if not isinstance(model_id, str) or not model_id.strip():
                raise ValueError(f"Provider for {agent_id} must expose a model_name")
            model_ids[agent_id] = model_id
            user = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            response = provider.generate(
                [ChatMessage("system", instruction), ChatMessage("user", user)],
                GenerationConfig(temperature=temperature, max_new_tokens=max_tokens, seed=seed),
            )
            calls.append(_Call(agent_id, role, model_id, response.text, user))
            return response.text

        prompt_payload = {
            "prompt_text": prompt.text,
            "declared_goal": prompt.iota.goal,
            "inputs": list(prompt.iota.inputs),
            "constraints": [
                {"kind": c.kind.value, "statement": c.statement}
                for c in prompt.iota.constraints
            ],
            "deliverables": list(prompt.iota.deliverables),
            "requirements": [
                {"type": r.type.value, "domain": r.domain, "statement": r.statement}
                for r in self.extraction.requirements
            ],
            "hypotheses": [
                {"type": h.type.value, "domain": h.domain, "statement": h.statement}
                for h in self.extraction.hypotheses
            ],
            "output_contract": {
                "candidate_id": "string",
                "subproblems": [{
                    "id": "string", "question": "string", "inputs": [],
                    "output": "string", "local_constraints": [],
                    "covered_requirements": [{
                        "type": "target|constraint|deliverable",
                        "domain": "string", "statement": "exact extracted statement"
                    }]
                }],
                "dependencies": [{"source": "subproblem-id", "target": "subproblem-id"}],
                "kappa": {"exact declared deliverable": ["contributor-subproblem-id"]},
                "hypothesis_verdicts": [],
            },
        }

        def decode(raw: str, candidate_id: str) -> Decomposition:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Baseline model output root must be a JSON object")
            return parse_candidate(
                data.get("candidate", data), prompt=prompt,
                extraction=self.extraction, candidate_id=candidate_id,
            ).decomposition

        def draft(agent_id: str, extra: Mapping[str, object] | None = None) -> Decomposition:
            payload = dict(prompt_payload)
            if extra:
                payload["context"] = dict(extra)
            raw = invoke(
                agent_id, "draft",
                "Decompose the prompt using plan-and-solve reasoning. Return one complete typed decomposition as JSON only.",
                payload, temperature=self.temperature_draft,
                max_tokens=self.max_tokens_decomposition,
            )
            return decode(raw, f"{agent_id}-draft")

        def trace() -> tuple[dict[str, object], ...]:
            result = []
            for index, call in enumerate(calls):
                result.append({
                    "call_index": index, "agent_id": call.agent_id, "role": call.role,
                    "model": call.model_id, "input_sha256": _sha(call.input_text),
                    "output_sha256": _sha(call.response), "seed": seed,
                    "baseline_profile": PROFILE_ID,
                })
            return tuple(result)

        if baseline_id == "single_plan_and_solve":
            if budget < 1:
                raise ValueError("Plan-and-solve requires one method call")
            selected = draft("single-decomposer")

        elif baseline_id == "single_self_refinement":
            if budget < 3:
                raise ValueError("Profile v1 self-refinement requires three calls; registered budget is smaller")
            first = draft("self-refiner")
            critique = invoke(
                "self-refiner", "self_critique",
                "Critique your own decomposition. Identify concrete omissions, redundancy, incorrect dependencies, and constraint violations. Return JSON with an issues array; do not rewrite the decomposition.",
                {"prompt": prompt.text, "candidate": _decomposition_json(first)},
                temperature=self.temperature_critique, max_tokens=self.max_tokens_other,
            )
            raw = invoke(
                "self-refiner", "revision",
                "Revise the decomposition using the critique. Return a complete typed decomposition JSON only.",
                {**prompt_payload, "previous_candidate": _decomposition_json(first), "critique": critique},
                temperature=self.temperature_draft, max_tokens=self.max_tokens_decomposition,
            )
            selected = decode(raw, "self-refined")

        elif baseline_id == "single_self_consistency":
            samples = [draft("self-consistency-sampler") for _ in range(budget)]
            selected = _aggregate_frequent_subproblems(samples, self.extraction, prompt)

        elif baseline_id == "decomposer_plus_evaluator":
            if budget < 2:
                raise ValueError("Decomposer-plus-evaluator requires two method calls; registered budget is smaller")
            candidate = draft("decomposer")
            evaluation = invoke(
                "separate-evaluator", "evaluation",
                "Evaluate the candidate decomposition for coverage, acyclicity, solvability risks, faithfulness risks, and composition correctness. Return JSON with verdict (accept|reject), rationale, and findings. Do not rewrite or select another candidate.",
                {"prompt": prompt.text, "requirements": prompt_payload["requirements"],
                 "candidate": _decomposition_json(candidate)},
                temperature=0.0, max_tokens=self.max_tokens_other,
            )
            try:
                verdict = json.loads(evaluation)
            except json.JSONDecodeError as exc:
                raise ValueError("Evaluator must return structured JSON") from exc
            if not isinstance(verdict, dict) or verdict.get("verdict") not in {"accept", "reject"}:
                raise ValueError("Evaluator output must contain verdict accept|reject")
            selected = candidate

        elif baseline_id == "multi_agent_debate":
            if budget < 3:
                raise ValueError("Profile v1 debate requires at least three calls (two drafts and one judge)")
            left = draft("debater-1")
            right = draft("debater-2")
            debate_context = []
            for turn in range(budget - 3):
                speaker = "debater-1" if turn % 2 == 0 else "debater-2"
                other = right if speaker == "debater-1" else left
                own = left if speaker == "debater-1" else right
                argument = invoke(
                    speaker, "debate",
                    "Debate the decomposition, identify concrete strengths and defects, and defend or challenge specific subproblems. Return JSON with argument and proposed_changes. Do not output a replacement decomposition.",
                    {"prompt": prompt.text, "own_candidate": _decomposition_json(own),
                     "other_candidate": _decomposition_json(other), "prior_arguments": debate_context},
                    temperature=self.temperature_critique, max_tokens=self.max_tokens_other,
                )
                debate_context.append(argument)
            judgment = invoke(
                "independent-judge", "judge",
                "Select the better of the two candidate decompositions after reviewing the debate. Return JSON with selected_candidate_id (debater-1-draft|debater-2-draft) and rationale.",
                {"candidate_a": _decomposition_json(left), "candidate_b": _decomposition_json(right),
                 "debate": debate_context},
                temperature=0.0, max_tokens=self.max_tokens_other,
            )
            try:
                decision = json.loads(judgment)
            except json.JSONDecodeError as exc:
                raise ValueError("Debate judge must return structured JSON") from exc
            selected_id = decision.get("selected_candidate_id") if isinstance(decision, dict) else None
            if selected_id == "debater-1-draft":
                selected = left
            elif selected_id == "debater-2-draft":
                selected = right
            else:
                raise ValueError("Debate judge selected_candidate_id is invalid")

        elif baseline_id == "nominal_multi_agent":
            if budget < self.n_nominal:
                raise ValueError("Profile v1 nominal baseline requires three independent drafts")
            drafts = [draft(f"nominal-member-{i+1}") for i in range(self.n_nominal)]
            requirement_set = frozenset(self.extraction.requirements)
            # Selection uses extracted requirements, never gold benchmark labels.
            selected = max(
                enumerate(drafts),
                key=lambda pair: (len(pair[1].cov & requirement_set), -pair[0]),
            )[1]
        else:
            raise AssertionError("Unreachable baseline ID")

        if len(calls) > budget:
            raise RuntimeError(f"Baseline exceeded registered method-call budget: {len(calls)} > {budget}")
        metadata = {
            "baseline_id": baseline_id,
            "baseline_profile_id": PROFILE_ID,
            "baseline_profile_status": PROFILE_STATUS,
            "baseline_operational_choice": BASELINE_CHOICES[baseline_id],
            "method_calls": len(calls),
            "registered_method_call_budget": budget,
            "unused_method_call_budget": budget - len(calls),
            "model_ids": dict(model_ids),
            "selection_uses_gold_labels": False,
            "equivalence_matcher": "exact-output-local-constraints-v1" if baseline_id == "single_self_consistency" else None,
        }
        return MethodRun(selected, len(calls), trace(), (), metadata)


def _sha(value: str) -> str:
    import hashlib
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _decomposition_json(value: Decomposition) -> dict[str, object]:
    return {
        "subproblems": [{
            "id": s.identifier, "question": s.question, "inputs": list(s.inputs),
            "output": s.output,
            "local_constraints": [{"kind": c.kind.value, "statement": c.statement}
                                  for c in s.local_constraints],
            "covered_requirements": [{"type": r.type.value, "domain": r.domain,
                                      "statement": r.statement}
                                     for r in s.covered_requirements],
        } for s in value.subproblems],
        "dependencies": [{"source": a, "target": b} for a, b in sorted(value.E)],
        "kappa": {key: sorted(items) for key, items in value.kappa.items()},
    }


def _aggregate_frequent_subproblems(
    samples: list[Decomposition], extraction: AggregatedExtraction, prompt: Prompt,
) -> Decomposition:
    if not samples:
        raise ValueError("Self-consistency needs at least one sample")
    flattened = [subproblem for sample in samples for subproblem in sample.subproblems]
    labels = equivalence_classes(flattened, DEFAULT_MATCHER)
    groups: dict[int, list[Subproblem]] = defaultdict(list)
    for label, subproblem in zip(labels, flattened):
        groups[label].append(subproblem)
    minimum = len(samples) // 2 + 1
    chosen = [items for items in groups.values() if len(items) >= minimum]
    if not chosen:
        maximum = max(len(items) for items in groups.values())
        chosen = [items for items in groups.values() if len(items) == maximum]
    chosen.sort(key=lambda items: (-len(items), min(x.identifier for x in items)))
    representatives = [sorted(items, key=lambda x: (x.identifier, x.question))[0] for items in chosen]
    subproblems = tuple(
        Subproblem(
            f"sc-{index+1}", item.question, item.inputs, item.output,
            item.local_constraints, item.covered_requirements,
        )
        for index, item in enumerate(representatives)
    )
    old_to_new: dict[str, str] = {}
    for new, group in zip(subproblems, chosen):
        for item in group:
            old_to_new[item.identifier] = new.identifier
    edges = set()
    for sample in samples:
        for source, target in sample.E:
            if source in old_to_new and target in old_to_new:
                a, b = old_to_new[source], old_to_new[target]
                if a != b:
                    edges.add((a, b))
    deliverables = []
    for deliverable in prompt.iota.deliverables:
        contributors = set()
        for sample in samples:
            for old_id in sample.kappa.get(deliverable, frozenset()):
                if old_id in old_to_new:
                    contributors.add(old_to_new[old_id])
        if not contributors:
            raise ValueError(
                f"Self-consistency profile could not reconstruct contributors for declared deliverable {deliverable!r}; "
                "it will not invent a composition edge"
            )
        deliverables.append(DeliverableComposition(deliverable, tuple(sorted(contributors))))
    return Decomposition(
        subproblems,
        tuple(Dependency(a, b) for a, b in sorted(edges)),
        tuple(deliverables),
    )
