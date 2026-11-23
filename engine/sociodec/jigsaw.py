"""Paper-aligned, deterministic Jigsaw facet construction for E1.

The paper defines facets from extracted requirement types and entities. Its
Figure 3(b) illustrates three facets: goals, constraints, and actors. The
specific grouping of the three requirement types into two requirement facets
is made explicit here as a versioned operationalization, not attributed as a
verbatim algorithm from the paper.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping

from sociodec.catalogue import StrategyId
from sociodec.experiments import content_hash
from sociodec.extraction import AggregatedExtraction
from sociodec.models.prompt import Prompt, Requirement, RequirementType


PAPER_S12_POLICY_ID = "paper-s12-3facet-v1"
PAPER_S12_POLICY_MANIFEST: dict[str, object] = {
    "schema_version": "sociodec-jigsaw-facet-policy-v1",
    "policy_id": PAPER_S12_POLICY_ID,
    "source_anchors": ["Table 4", "Figure 3(b)", "Section 5.1.2"],
    "facets": [
        {
            "agent_id": "expert-1",
            "facet_id": "goals_deliverables",
            "facet_kind": "requirement_types",
            "requirement_types": ["target", "deliverable"],
        },
        {
            "agent_id": "expert-2",
            "facet_id": "constraints",
            "facet_kind": "requirement_types",
            "requirement_types": ["constraint"],
        },
        {
            "agent_id": "expert-3",
            "facet_id": "actors_resources",
            "facet_kind": "entities_and_linked_requirements",
            "requirement_types": [],
        },
    ],
    "integrator_view": "FULL_PROMPT",
    "empty_facet_policy": "drop_empty_facet_without_model_call",
    "operationalization_note": (
        "The paper defines type-based requirement facets and an actor facet. "
        "This fixed three-facet grouping follows Figure 3(b)'s goals, constraints "
        "and actors example; target and deliverable are grouped together."
    ),
}
PAPER_S12_POLICY_SHA256 = content_hash(PAPER_S12_POLICY_MANIFEST)


@dataclass(frozen=True, slots=True)
class JigsawPromptViewBundle:
    """Facet views plus explicit accounting for empty facets and policy identity."""

    views: Mapping[str, str]
    active_facets: tuple[str, ...]
    dropped_facets: tuple[str, ...]
    policy_id: str
    policy_sha256: str
    facet_manifest: tuple[Mapping[str, object], ...]

    def as_manifest(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "active_facets": list(self.active_facets),
            "dropped_facets": list(self.dropped_facets),
            "facets": [dict(item) for item in self.facet_manifest],
        }


def _normalise_entity_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _requirement_payload(requirement: Requirement) -> dict[str, object]:
    span = requirement.source_span
    return {
        "statement": requirement.statement,
        "type": requirement.type.value,
        "domain": requirement.domain,
        "source_span": (
            {"start": span.start, "end": span.end} if span is not None else None
        ),
        "entity_names": list(requirement.entity_names),
    }


class PaperJigsawPromptViewFactory:
    """Build the registered three-facet S12 view without exposing the full prompt."""

    factory_id = PAPER_S12_POLICY_ID
    policy_sha256 = PAPER_S12_POLICY_SHA256

    def policy_manifest(self) -> dict[str, object]:
        return dict(PAPER_S12_POLICY_MANIFEST)

    def __call__(
        self,
        strategy_id: StrategyId,
        prompt: Prompt,
        extraction: AggregatedExtraction,
        agent_ids: tuple[str, ...],
    ) -> JigsawPromptViewBundle:
        if strategy_id is not StrategyId.S12:
            raise ValueError("PaperJigsawPromptViewFactory is only valid for S12")
        expected = ("expert-1", "expert-2", "expert-3", "integrator")
        if tuple(agent_ids) != expected:
            raise ValueError(
                "paper-s12-3facet-v1 requires expert-1, expert-2, expert-3 and integrator"
            )

        entities = {
            _normalise_entity_name(item.name): item for item in extraction.entities
        }
        linked: dict[str, list[Requirement]] = {key: [] for key in entities}
        for requirement in extraction.requirements:
            for entity_name in requirement.entity_names:
                key = _normalise_entity_name(entity_name)
                if key not in entities:
                    raise ValueError(
                        f"requirement references entity {entity_name!r} absent from N_hat"
                    )
                linked[key].append(requirement)

        type_facets = {
            "expert-1": (
                "goals_deliverables",
                ("target", "deliverable"),
                tuple(
                    item for item in extraction.requirements
                    if item.type in {RequirementType.TARGET, RequirementType.DELIVERABLE}
                ),
            ),
            "expert-2": (
                "constraints",
                ("constraint",),
                tuple(
                    item for item in extraction.requirements
                    if item.type is RequirementType.CONSTRAINT
                ),
            ),
        }
        views: dict[str, str] = {}
        active: list[str] = []
        dropped: list[str] = []
        facet_records: list[Mapping[str, object]] = []

        for agent_id, (facet_id, types, requirements) in type_facets.items():
            payload = {
                "schema_version": "sociodec-jigsaw-facet-view-v1",
                "policy_id": self.factory_id,
                "facet_id": facet_id,
                "facet_kind": "requirement_types",
                "requirement_types": list(types),
                "requirements": [_requirement_payload(item) for item in requirements],
                "instruction": (
                    "Decompose only the requirements in this facet. Do not infer "
                    "or solve requirements assigned to another facet. Return the "
                    "standard typed SocioDec decomposition candidate."
                ),
            }
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            views[agent_id] = encoded if requirements else f"EMPTY_FACET_DROPPED:{facet_id}"
            status = "active" if requirements else "dropped_empty"
            (active if requirements else dropped).append(agent_id)
            facet_records.append({
                "agent_id": agent_id,
                "facet_id": facet_id,
                "status": status,
                "item_count": len(requirements),
                "view_sha256": content_hash(payload) if requirements else None,
            })

        actor_payload = {
            "schema_version": "sociodec-jigsaw-facet-view-v1",
            "policy_id": self.factory_id,
            "facet_id": "actors_resources",
            "facet_kind": "entities_and_linked_requirements",
            "entities": [
                {
                    "name": entity.name,
                    "description": entity.description,
                    "requirements": [
                        _requirement_payload(item)
                        for item in linked[_normalise_entity_name(entity.name)]
                    ],
                }
                for entity in extraction.entities
            ],
            "instruction": (
                "Decompose the actor/resource facet. Consider each extracted "
                "entity and only the requirements explicitly linked to that "
                "entity. Do not assume that an entity is itself a requirement. "
                "Return the standard typed SocioDec decomposition candidate."
            ),
        }
        actor_content = json.dumps(actor_payload, ensure_ascii=False, sort_keys=True)
        actor_active = bool(extraction.entities)
        views["expert-3"] = actor_content if actor_active else "EMPTY_FACET_DROPPED:actors_resources"
        (active if actor_active else dropped).append("expert-3")
        facet_records.append({
            "agent_id": "expert-3",
            "facet_id": "actors_resources",
            "status": "active" if actor_active else "dropped_empty",
            "item_count": len(extraction.entities),
            "view_sha256": content_hash(actor_payload) if actor_active else None,
        })

        if not active:
            raise ValueError(
                "S12 cannot run because all three extracted facets are empty; "
                "the extraction must be reviewed before decomposition"
            )
        views["integrator"] = "FULL_PROMPT"
        return JigsawPromptViewBundle(
            views=views,
            active_facets=tuple(active),
            dropped_facets=tuple(dropped),
            policy_id=self.factory_id,
            policy_sha256=self.policy_sha256,
            facet_manifest=tuple(facet_records),
        )
