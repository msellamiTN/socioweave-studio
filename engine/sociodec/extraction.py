"""Paper-aligned requirement extraction and multi-extractor aggregation.

Implements the extraction contract from Section 3.2, Definition 3:
each extractor maps x to typed explicit requirements, implicit hypotheses,
entities, ambiguity flags and potential conflict pairs. Aggregation unions
extractor outputs and deduplicates equivalent statements.

The default deduplicator is intentionally conservative (normalised exact
match). Semantic equivalence requires an explicitly supplied matcher.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Protocol

from sociodec.models.prompt import (
    Entity, Requirement, RequirementType, SourceSpan
)
from sociodec.providers.base import ChatMessage, GenerationConfig, LLMProvider


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """A candidate implicit requirement, pending a later verdict."""
    statement: str
    type: RequirementType
    domain: str
    rationale: str = ""
    entity_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.statement.strip() or not self.domain.strip():
            raise ValueError("Hypothesis statement and domain must be non-empty")


@dataclass(frozen=True, slots=True)
class AmbiguityFlag:
    """An explicit requirement or prompt fragment admitting readings."""
    subject: str
    readings: tuple[str, ...]
    explanation: str = ""

    def __post_init__(self) -> None:
        if not self.subject.strip() or len(self.readings) < 2:
            raise ValueError("An ambiguity needs a subject and at least two readings")


@dataclass(frozen=True, slots=True)
class ConflictPair:
    """Two requirement/hypothesis statements that may be incompatible."""
    left: str
    right: str
    explanation: str = ""

    def __post_init__(self) -> None:
        if not self.left.strip() or not self.right.strip() or self.left == self.right:
            raise ValueError("Conflict pair must contain two distinct statements")


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    requirements: tuple[Requirement, ...] = ()
    hypotheses: tuple[Hypothesis, ...] = ()
    entities: tuple[Entity, ...] = ()
    ambiguities: tuple[AmbiguityFlag, ...] = ()
    conflicts: tuple[ConflictPair, ...] = ()
    extractor_id: str = "unknown"
    raw_response: str | None = field(default=None, repr=False)


class RequirementExtractor(Protocol):
    @property
    def extractor_id(self) -> str: ...
    def extract(self, prompt_text: str) -> ExtractionResult: ...


class ExtractionFormatError(ValueError):
    """Raised when an extractor response violates the required JSON contract."""


def _normalise(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value)).strip()


def _json_payload(text: str) -> dict:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].strip().lower() in {"```", "```json"}:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ExtractionFormatError(f"Extractor returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ExtractionFormatError("Extractor JSON root must be an object")
    return value

def parse_extraction(text: str, prompt_text: str, extractor_id: str) -> ExtractionResult:
    """Parse and structurally validate one extractor's JSON result."""
    data = _json_payload(text)
    try:
        requirements = tuple(
            Requirement(
                statement=item["statement"],
                type=RequirementType(item["type"]),
                domain=item["domain"],
                source_span=SourceSpan(**item["source_span"]),
                entity_names=tuple(item.get("entity_names", ())),
            )
            for item in data.get("requirements", [])
        )
        for requirement in requirements:
            requirement.validate_against(prompt_text)

        hypotheses = tuple(
            Hypothesis(
                statement=item["statement"],
                type=RequirementType(item["type"]),
                domain=item["domain"],
                rationale=item.get("rationale", ""),
                entity_names=tuple(item.get("entity_names", ())),
            )
            for item in data.get("hypotheses", [])
        )
        entities = tuple(
            Entity(name=item["name"], description=item.get("description"))
            for item in data.get("entities", [])
        )
        ambiguities = tuple(
            AmbiguityFlag(
                subject=item["subject"],
                readings=tuple(item["readings"]),
                explanation=item.get("explanation", ""),
            )
            for item in data.get("ambiguities", [])
        )
        conflicts = tuple(
            ConflictPair(
                left=item["left"], right=item["right"],
                explanation=item.get("explanation", ""),
            )
            for item in data.get("conflicts", [])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ExtractionFormatError(f"Invalid extraction structure: {exc}") from exc

    return ExtractionResult(
        requirements=requirements, hypotheses=hypotheses, entities=entities,
        ambiguities=ambiguities, conflicts=conflicts,
        extractor_id=extractor_id, raw_response=text,
    )


class ProviderRequirementExtractor:
    """LLM-backed extractor; provider selection remains external/configurable."""

    def __init__(self, provider: LLMProvider, extractor_id: str,
                 generation: GenerationConfig | None = None) -> None:
        self.provider = provider
        self._extractor_id = extractor_id
        self.generation = generation or GenerationConfig(
            temperature=0.7, max_new_tokens=1024
        )

    @property
    def extractor_id(self) -> str:
        return self._extractor_id

    def extract(self, prompt_text: str) -> ExtractionResult:
        system = (
            "You are a requirement analyst. Extract only what is supported by "
            "the prompt. Return one JSON object and no markdown. Explicit "
            "requirements must be atomic, individually checkable and include "
            "a source_span with zero-based half-open character offsets into "
            "the exact prompt text. Use types target, constraint, deliverable. "
            "Implicit requirements must be hypotheses, never asserted facts. "
            "Entities are actors or objects, not requirements. Flag ambiguous "
            "readings and possible conflicting pairs. Do not invent spans."
        )
        user = (
            "Return JSON with keys requirements, hypotheses, entities, "
            "ambiguities, conflicts. Requirement fields: statement, type, "
            "domain, source_span {start,end}, entity_names. Hypothesis fields: "
            "statement,type,domain,rationale,entity_names. Entity fields: "
            "name,description. Ambiguity fields: subject,readings,explanation. "
            "Conflict fields: left,right,explanation.\n\nPROMPT TEXT:\n"
            + prompt_text
        )
        response = self.provider.generate(
            [ChatMessage("system", system), ChatMessage("user", user)],
            self.generation,
        )
        return parse_extraction(response.text, prompt_text, self.extractor_id)


@dataclass(frozen=True, slots=True)
class AggregatedExtraction:
    """Union/dedup result plus provenance and extractor-level evidence."""
    requirements: tuple[Requirement, ...]
    hypotheses: tuple[Hypothesis, ...]
    entities: tuple[Entity, ...]
    ambiguities: tuple[AmbiguityFlag, ...]
    conflicts: tuple[ConflictPair, ...]
    requirement_sources: dict[str, tuple[str, ...]]
    hypothesis_sources: dict[str, tuple[str, ...]]
    extractor_results: tuple[ExtractionResult, ...]

    @property
    def R_hat(self) -> tuple[Requirement, ...]:
        return self.requirements

    @property
    def H_hat(self) -> tuple[Hypothesis, ...]:
        return self.hypotheses

    @property
    def N_hat(self) -> tuple[Entity, ...]:
        return self.entities


EquivalenceMatcher = Callable[[object, object], bool]


def _provenance_key(item: object) -> str:
    """Stable key that preserves requirement type and domain identity."""
    kind = getattr(getattr(item, "type", None), "value", "")
    domain = getattr(item, "domain", "")
    statement = _normalise(getattr(item, "statement", ""))
    return f"{kind}|{domain}|{statement}"


def aggregate_extractions(
    results: tuple[ExtractionResult, ...] | list[ExtractionResult],
    matcher: EquivalenceMatcher | None = None,
) -> AggregatedExtraction:
    """Union extractor outputs and deduplicate equivalent statements.

    The default matcher is conservative: same normalised statement, type and
    domain. Inject a reviewed semantic matcher when broader equivalence is
    justified. Every merged item retains the IDs of contributing extractors.
    """
    def equivalent(a: object, b: object) -> bool:
        if matcher is not None:
            return matcher(a, b)
        return (
            getattr(a, "type", None) == getattr(b, "type", None)
            and getattr(a, "domain", None) == getattr(b, "domain", None)
            and _normalise(getattr(a, "statement", "")) ==
                _normalise(getattr(b, "statement", ""))
        )

    reqs: list[Requirement] = []
    hyps: list[Hypothesis] = []
    req_sources: dict[str, list[str]] = {}
    hyp_sources: dict[str, list[str]] = {}

    for result in results:
        for item in result.requirements:
            existing = next((x for x in reqs if equivalent(x, item)), None)
            key = _provenance_key(item)
            if existing is None:
                reqs.append(item)
                req_sources[key] = [result.extractor_id]
            else:
                req_sources.setdefault(_provenance_key(existing), []).append(result.extractor_id)
        for item in result.hypotheses:
            existing = next((x for x in hyps if equivalent(x, item)), None)
            key = _provenance_key(item)
            if existing is None:
                hyps.append(item)
                hyp_sources[key] = [result.extractor_id]
            else:
                hyp_sources.setdefault(_provenance_key(existing), []).append(result.extractor_id)

    entities_by_name: dict[str, Entity] = {}
    for result in results:
        for entity in result.entities:
            entities_by_name.setdefault(_normalise(entity.name), entity)

    def unique_by(items, key_fn):
        seen, output = set(), []
        for item in items:
            key = key_fn(item)
            if key not in seen:
                seen.add(key)
                output.append(item)
        return tuple(output)

    all_ambiguities = unique_by(
        [x for r in results for x in r.ambiguities],
        lambda x: (_normalise(x.subject), tuple(map(_normalise, x.readings))),
    )
    all_conflicts = unique_by(
        [x for r in results for x in r.conflicts],
        lambda x: tuple(sorted((_normalise(x.left), _normalise(x.right)))),
    )
    return AggregatedExtraction(
        requirements=tuple(reqs), hypotheses=tuple(hyps),
        entities=tuple(entities_by_name.values()),
        ambiguities=all_ambiguities, conflicts=all_conflicts,
        requirement_sources={k: tuple(v) for k, v in req_sources.items()},
        hypothesis_sources={k: tuple(v) for k, v in hyp_sources.items()},
        extractor_results=tuple(results),
    )


def run_extractors(
    prompt_text: str,
    extractors: tuple[RequirementExtractor, ...] | list[RequirementExtractor],
    matcher: EquivalenceMatcher | None = None,
) -> AggregatedExtraction:
    """Run q extractors independently, then apply the paper's union/dedup."""
    if not extractors:
        raise ValueError("At least one extractor is required")
    results = tuple(extractor.extract(prompt_text) for extractor in extractors)
    return aggregate_extractions(results, matcher=matcher)
