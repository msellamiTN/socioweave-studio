import copy
import json

import pytest

from sociodec.datasets import E1FrozenSnapshot
from sociodec.e1_extraction import (
    apply_human_audit, build_e1_extraction_bundle, validate_e1_extraction_bundle,
)
from sociodec.extraction import AmbiguityFlag, ConflictPair, ExtractionResult, Hypothesis
from sociodec.models.prompt import Requirement, RequirementType, SourceSpan
from sociodec.experiments import BenchmarkPrompt, content_hash


def _snapshot():
    examples = tuple(
        BenchmarkPrompt(
            "smart-administration", f"p{i}", f"Request {i}: provide service.",
            reference_data={"fixture_annotation": "synthetic test fixture only"},
        )
        for i in range(1, 6)
    )
    ids = [item.example_id for item in examples]
    entry = {
        "source_file": "synthetic-test-fixture.jsonl", "source_sha256": "f" * 64,
        "source_version": "fixture-v1", "split": "test",
        "selection_protocol": "synthetic unit-test fixture only", "selection_seed": None,
        "license_review_status": "approved", "paper_source_url": None,
        "prompt_case": "ambiguity, conflicting objectives, several institutions",
        "reference_provided": "requirement lists, hypotheses and reference decompositions reviewed by practitioners",
        "metrics": ["all Table 9 metrics, including V1 coverage and hypothesis verdicts"],
        "coverage_applicable": True, "source_release_status": "to_be_released_with_code",
        "prompt_count": len(ids), "prompt_ids": ids,
        "prompt_sha256": {item.example_id: item.prompt_hash for item in examples},
        "reference_data_sha256": {item.example_id: item.reference_data_hash for item in examples},
    }
    datasets = {"smart-administration": entry}
    manifest = {
        "schema_version": "e1-frozen-benchmark-snapshot-v1",
        "dataset_order": ["smart-administration"], "datasets": datasets,
        "total_prompt_count": len(examples),
        "snapshot_sha256": content_hash({"datasets": datasets}),
    }
    return E1FrozenSnapshot(examples, {"smart-administration": tuple(ids)}, manifest)


def _roster():
    return [
        {"extractor_id": f"extractor-{i}", "provider_org": f"provider-{i}",
         "model_id": f"model-{i}", "model_revision": f"revision-{i}",
         "config_sha256": str(i) * 64}
        for i in range(1, 4)
    ]


def _results(snapshot):
    output = {}
    for example in snapshot.examples:
        values = []
        for i in range(1, 4):
            requirement = Requirement(
                statement=f"Provide service step {i}", type=RequirementType("deliverable"),
                domain="service", source_span=SourceSpan(0, 7), entity_names=(),
            )
            hypothesis = Hypothesis(
                statement=f"Implicit condition {i}", type=RequirementType("constraint"),
                domain="service", rationale="synthetic fixture", entity_names=(),
            )
            values.append(ExtractionResult(
                requirements=(requirement,), hypotheses=(hypothesis,),
                entities=(), ambiguities=(AmbiguityFlag("service", ("public", "private")),),
                conflicts=(ConflictPair("condition A", "condition B"),),
                extractor_id=f"extractor-{i}", raw_response=json.dumps({"fixture": i}),
            ))
        output[(example.dataset, example.example_id)] = tuple(values)
    return output


def _build():
    snapshot = _snapshot()
    bundle = build_e1_extraction_bundle(
        snapshot=snapshot, extractor_roster=_roster(),
        results_by_prompt=_results(snapshot), audit_seed=1729,
    )
    return snapshot, bundle


def _complete(bundle):
    decisions = [
        {"item_id": item["item_id"], "reviewer_id": "human-reviewer-01",
         "decision": "correct", "rationale": "Reviewed against the source prompt.",
         "reviewed_at": "2026-11-21T12:00:00+00:00"}
        for item in bundle["audit_tasks"]
    ]
    return apply_human_audit(bundle, decisions)


def test_e1_extraction_requires_three_declared_unique_extractors():
    snapshot = _snapshot()
    with pytest.raises(ValueError, match="exactly three"):
        build_e1_extraction_bundle(
            snapshot=snapshot, extractor_roster=_roster()[:2],
            results_by_prompt=_results(snapshot), audit_seed=1,
        )
    roster = _roster()
    roster[2]["extractor_id"] = roster[1]["extractor_id"]
    with pytest.raises(ValueError, match="IDs must be distinct"):
        build_e1_extraction_bundle(
            snapshot=snapshot, extractor_roster=roster,
            results_by_prompt=_results(snapshot), audit_seed=1,
        )


def test_e1_extraction_requires_exactly_one_output_per_extractor_and_prompt():
    snapshot = _snapshot()
    results = _results(snapshot)
    results[("smart-administration", "p1")] = results[("smart-administration", "p1")][:2]
    with pytest.raises(ValueError, match="exactly one output"):
        build_e1_extraction_bundle(
            snapshot=snapshot, extractor_roster=_roster(),
            results_by_prompt=results, audit_seed=1,
        )


def test_e1_union_keeps_explicit_and_implicit_items_and_provenance():
    snapshot, bundle = _build()
    assert bundle["paper_protocol"] == {
        "extractor_count": 3, "aggregation": "union", "human_audit_fraction": 0.20,
    }
    assert bundle["union_item_count"] == 30
    assert bundle["audit_item_count"] == 6
    assert {item["kind"] for item in bundle["union_items"]} == {
        "explicit_requirement", "implicit_hypothesis",
    }
    assert all(len(item["extractor_sources"]) == 1 for item in bundle["union_items"])
    assert all(len(record["extractor_outputs"]) == 3 for record in bundle["records"])
    validate_e1_extraction_bundle(bundle, snapshot=snapshot, require_human_audit=False)


def test_e1_audit_sample_is_deterministic_and_content_addressed():
    snapshot, first = _build()
    _, second = _build()
    assert [x["item_id"] for x in first["audit_tasks"]] == [
        x["item_id"] for x in second["audit_tasks"]
    ]
    changed = copy.deepcopy(first)
    changed["audit_tasks"][0]["status"] = "audited"
    with pytest.raises(ValueError, match="SHA-256"):
        validate_e1_extraction_bundle(changed, snapshot=snapshot, require_human_audit=False)


def test_pending_human_audit_fails_closed():
    snapshot, bundle = _build()
    with pytest.raises(ValueError, match="incomplete"):
        validate_e1_extraction_bundle(bundle, snapshot=snapshot, require_human_audit=True)


def test_human_audit_requires_exact_sample_coverage_and_traceable_decisions():
    snapshot, bundle = _build()
    with pytest.raises(ValueError, match="cover every sampled item"):
        apply_human_audit(bundle, [])
    decisions = [
        {"item_id": item["item_id"], "reviewer_id": "reviewer",
         "decision": "correct", "rationale": "Checked source.",
         "reviewed_at": "2026-11-21T12:00:00+00:00"}
        for item in bundle["audit_tasks"]
    ]
    decisions[0]["reviewed_at"] = "2026-11-21T12:00:00"
    with pytest.raises(ValueError, match="timezone offset"):
        apply_human_audit(bundle, decisions)


def test_completed_human_audit_is_bound_to_bundle_and_validates():
    snapshot, bundle = _build()
    completed = _complete(bundle)
    assert completed["audit_status"] == "complete"
    assert completed["bundle_sha256"] != bundle["bundle_sha256"]
    validate_e1_extraction_bundle(completed, snapshot=snapshot, require_human_audit=True)



def test_e1_validator_rejects_union_tampering_even_when_all_hashes_are_recomputed():
    snapshot, bundle = _build()
    forged = copy.deepcopy(bundle)
    sampled = {item["item_id"] for item in forged["audit_tasks"]}
    target = next(item for item in forged["union_items"] if item["item_id"] not in sampled)
    target["statement"] = "forged statement with recomputed hashes"
    target["item_sha256"] = content_hash({"forged": target["statement"]})
    for record in forged["records"]:
        prompt_items = [
            item for item in forged["union_items"]
            if item["dataset"] == record["dataset"]
            and item["example_id"] == record["example_id"]
        ]
        record["union_sha256"] = content_hash(prompt_items)
    forged["bundle_sha256"] = content_hash({
        key: value for key, value in forged.items() if key != "bundle_sha256"
    })
    with pytest.raises(ValueError, match="union"):
        validate_e1_extraction_bundle(
            forged, snapshot=snapshot, require_human_audit=False,
        )


def test_e1_extraction_bundle_rejects_wrong_snapshot_and_tampered_union():
    snapshot, bundle = _build()
    changed = copy.deepcopy(bundle)
    changed["union_items"][0]["statement"] = "tampered"
    with pytest.raises(ValueError, match="SHA-256"):
        validate_e1_extraction_bundle(changed, snapshot=snapshot, require_human_audit=False)
    other = _snapshot()
    other_manifest = copy.deepcopy(other.manifest)
    other_manifest["datasets"]["smart-administration"]["source_sha256"] = "0" * 64
    other_manifest["snapshot_sha256"] = content_hash({"datasets": other_manifest["datasets"]})
    other = E1FrozenSnapshot(
        other.examples, other.expected_prompt_ids, other_manifest,
    )
    with pytest.raises(ValueError, match="different frozen dataset"):
        validate_e1_extraction_bundle(bundle, snapshot=other, require_human_audit=False)


def test_completed_bundle_restores_typed_aggregates_without_provider_calls():
    from sociodec.e1_extraction import load_e1_extraction_aggregates

    snapshot, bundle = _build()
    completed = _complete(bundle)
    restored = load_e1_extraction_aggregates(completed, snapshot=snapshot)
    assert set(restored) == {(item.dataset, item.example_id) for item in snapshot.examples}
    for aggregate in restored.values():
        assert len(aggregate.requirements) == 3
        assert len(aggregate.hypotheses) == 3
        assert len(aggregate.ambiguities) == 3
        assert len(aggregate.conflicts) == 3
