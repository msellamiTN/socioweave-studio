"""Small-model end-to-end runtime for T4 engineering smoke tests.

This profile exercises requirement extraction, aggregation, typed decomposition
parsing and structural validation with one quantized local model. It is NOT a
paper-faithful MA/MB/MC/ME experiment and its outputs are not scientific results.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sociodec.extraction import (
    AggregatedExtraction, ProviderRequirementExtractor, run_extractors,
)
from sociodec.models.decomposition import (
    Decomposition, DeliverableComposition, Dependency, Subproblem,
)
from sociodec.models.prompt import (
    Constraint, ConstraintKind, Entity, Interpretation, Prompt, RequirementType,
)
from sociodec.providers.base import ChatMessage, GenerationConfig, LLMProvider
from sociodec.providers.huggingface_local import HuggingFaceLocalProvider
from sociodec.validation import ValidationReport, validate_decomposition


DEFAULT_MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"


@dataclass(frozen=True, slots=True)
class SmallModelConfig:
    model_id: str = DEFAULT_MODEL_ID
    revision: str | None = None
    load_in_4bit: bool = True
    max_input_tokens: int = 4096
    extractor_count: int = 3
    extraction_tokens: int = 768
    decomposition_tokens: int = 1024
    seed: int = 17

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("model_id must be non-empty")
        if self.max_input_tokens < 256:
            raise ValueError("max_input_tokens must be >= 256")
        if self.extractor_count != 3:
            raise ValueError("The paper's requirement-extraction setting is q=3")
        if self.extraction_tokens < 64 or self.decomposition_tokens < 128:
            raise ValueError("token limits are too small for structured outputs")
        if self.seed < 0:
            raise ValueError("seed must be non-negative")


@dataclass(frozen=True, slots=True)
class SmallModelRun:
    model_id: str
    prompt_text: str
    extraction: AggregatedExtraction
    prompt: Prompt
    decomposition: Decomposition
    validation: ValidationReport
    provider_calls: int
    input_tokens: int
    output_tokens: int
    mode: str = "engineering_smoke_only"

    @property
    def structural_valid(self) -> bool:
        return self.validation.structural_valid

    def report(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "scientific_result": False,
            "model_id": self.model_id,
            "prompt_text": self.prompt_text,
            "provider_calls": self.provider_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "requirements": len(self.extraction.requirements),
            "hypotheses": len(self.extraction.hypotheses),
            "entities": len(self.extraction.entities),
            "ambiguities": len(self.extraction.ambiguities),
            "conflicts": len(self.extraction.conflicts),
            "subproblems": len(self.decomposition.subproblems),
            "dependencies": len(self.decomposition.dependencies),
            "structural_valid": self.structural_valid,
            "checks": {
                "V1_coverage": self.validation.v1_coverage.status.value,
                "V2_acyclicity": self.validation.v2_acyclicity.status.value,
                "V3_solvability": self.validation.v3_solvability.status.value,
                "V4_faithfulness": self.validation.v4_faithfulness.status.value,
                "V5_composition": self.validation.v5_composition.status.value,
                "hypothesis_verdicts": self.validation.hypothesis_verdicts.status.value,
            },
            "findings": [
                {"code": item.code, "message": item.message, "subjects": list(item.subjects)}
                for item in self.validation.failures
            ],
        }


def build_t4_provider(config: SmallModelConfig | None = None) -> HuggingFaceLocalProvider:
    """Construct, but do not eagerly load, the default quantized T4 provider."""
    cfg = config or SmallModelConfig()
    return HuggingFaceLocalProvider(
        model_id=cfg.model_id,
        revision=cfg.revision,
        load_in_4bit=cfg.load_in_4bit,
        max_input_tokens=cfg.max_input_tokens,
    )


def _decomposition_payload(text: str) -> dict[str, Any]:
    value = json.loads(text.strip())
    if not isinstance(value, dict):
        raise ValueError("decomposition response root must be a JSON object")
    required = {"subproblems", "dependencies", "composition"}
    missing = required - set(value)
    if missing:
        raise ValueError(f"decomposition response missing keys: {sorted(missing)}")
    if not isinstance(value["subproblems"], list) or not value["subproblems"]:
        raise ValueError("subproblems must be a non-empty array")
    if not isinstance(value["dependencies"], list) or not isinstance(value["composition"], dict):
        raise ValueError("dependencies must be an array and composition must be an object")
    return value


def parse_decomposition(
    text: str,
    *,
    requirements: tuple,
    constraints: tuple[Constraint, ...],
) -> Decomposition:
    """Parse a model response into D=(S,E,kappa), rejecting invented references."""
    data = _decomposition_payload(text)
    requirement_by_statement = {item.statement: item for item in requirements}
    constraint_by_statement = {item.statement: item for item in constraints}
    subproblems = []
    for index, item in enumerate(data["subproblems"], start=1):
        if not isinstance(item, dict):
            raise ValueError(f"subproblems[{index - 1}] must be an object")
        covered_names = item.get("covered_requirements", [])
        local_names = item.get("local_constraints", [])
        if not isinstance(covered_names, list) or not isinstance(local_names, list):
            raise ValueError("covered_requirements and local_constraints must be arrays")
        unknown_requirements = set(covered_names) - set(requirement_by_statement)
        unknown_constraints = set(local_names) - set(constraint_by_statement)
        if unknown_requirements or unknown_constraints:
            raise ValueError(
                "model referenced unknown requirement/constraint labels: "
                f"{sorted(unknown_requirements)} / {sorted(unknown_constraints)}"
            )
        subproblems.append(Subproblem(
            identifier=str(item.get("id", f"sp-{index}")),
            question=item["question"],
            inputs=tuple(item.get("inputs", ())),
            output=item["output"],
            local_constraints=tuple(constraint_by_statement[x] for x in local_names),
            covered_requirements=tuple(requirement_by_statement[x] for x in covered_names),
        ))
    dependencies = tuple(
        Dependency(item["source_id"], item["target_id"])
        for item in data["dependencies"]
    )
    composition = tuple(
        DeliverableComposition(key, tuple(value))
        for key, value in data["composition"].items()
    )
    return Decomposition(tuple(subproblems), dependencies, composition)


def run_small_model_core(
    prompt_text: str,
    *,
    provider: LLMProvider | None = None,
    config: SmallModelConfig | None = None,
) -> SmallModelRun:
    """Run q=3 extraction -> union/dedup -> decomposition -> V1/V2/V5 checks.

    All three extractors use the same small model. This tests the core pipeline
    and aggregation implementation; it does not measure model diversity.
    """
    cfg = config or SmallModelConfig()
    model = provider or build_t4_provider(cfg)
    if hasattr(model, "load"):
        model.load()  # type: ignore[attr-defined]

    extraction_generation = GenerationConfig(
        temperature=0.7, max_new_tokens=cfg.extraction_tokens, seed=cfg.seed,
    )
    extractors = tuple(
        ProviderRequirementExtractor(
            model, f"small-model-extractor-{index + 1}", extraction_generation,
        )
        for index in range(cfg.extractor_count)
    )
    extraction = run_extractors(prompt_text, extractors)

    constraints = tuple(
        Constraint(item.statement, ConstraintKind.HARD)
        for item in extraction.requirements
        if item.type is RequirementType.CONSTRAINT
    )
    deliverables = tuple(
        item.statement for item in extraction.requirements
        if item.type is RequirementType.DELIVERABLE
    )
    goal = next(
        (item.statement for item in extraction.requirements if item.type is RequirementType.TARGET),
        prompt_text[:500],
    )
    prompt = Prompt(
        prompt_text,
        Interpretation(
            goal=goal,
            constraints=constraints,
            deliverables=deliverables,
            entities=extraction.entities,
        ),
        identifier="small-model-smoke",
    )

    requirements = extraction.requirements
    prompt.validate_explicit_requirements(requirements)
    requirement_lines = [
        {"statement": item.statement, "type": item.type.value, "domain": item.domain}
        for item in requirements
    ]
    system = (
        "You are a task decomposition engine. Return strict JSON only. "
        "Do not invent requirements or constraints. Every covered requirement "
        "must exactly match one supplied statement. Dependencies must be "
        "acyclic. Every declared deliverable must have at least one contributor."
    )
    user = (
        "Decompose the prompt into atomic, executable subproblems. Return keys "
        "subproblems, dependencies, composition. Each subproblem has id, "
        "question, inputs (array), output, covered_requirements (array of exact "
        "requirement statements), local_constraints (array of exact constraint "
        "statements). Dependencies are objects with source_id and target_id. "
        "Composition is an object mapping each deliverable to contributor IDs.\n"
        f"PROMPT: {prompt_text}\n"
        f"REQUIREMENTS: {json.dumps(requirement_lines, ensure_ascii=False)}\n"
        f"CONSTRAINTS: {json.dumps([x.statement for x in constraints], ensure_ascii=False)}\n"
        f"DELIVERABLES: {json.dumps(list(deliverables), ensure_ascii=False)}"
    )
    result = model.generate(
        [ChatMessage("system", system), ChatMessage("user", user)],
        GenerationConfig(
            temperature=0.7, max_new_tokens=cfg.decomposition_tokens, seed=cfg.seed + 1,
        ),
    )
    decomposition = parse_decomposition(
        result.text, requirements=requirements, constraints=constraints,
    )
    validation = validate_decomposition(prompt, requirements, decomposition)
    # Token usage for extraction is not currently exposed by ExtractionResult;
    # count only the decomposition call exactly and report extraction as unknown.
    return SmallModelRun(
        model_id=getattr(model, "model_name", "injected-provider"),
        prompt_text=prompt_text,
        extraction=extraction,
        prompt=prompt,
        decomposition=decomposition,
        validation=validation,
        provider_calls=cfg.extractor_count + 1,
        input_tokens=result.input_tokens or 0,
        output_tokens=result.output_tokens or 0,
    )
