from fastapi.testclient import TestClient

from socioweave_studio.api.app import app
from sociodec.provider_factory import E1ProviderRegistry, ProviderSpec
from sociodec.jigsaw import PAPER_S12_POLICY_ID, PAPER_S12_POLICY_SHA256

client = TestClient(app)


def test_health_and_capabilities_keep_execution_disabled():
    assert client.get("/api/v1/health").json()["status"] == "ok"
    capabilities = client.get("/api/v1/capabilities").json()
    assert capabilities["configuration_preview"] is True
    assert capabilities["full_e1_preflight"] is False
    assert capabilities["engine_campaign_preflight"] is True
    assert capabilities["e1_dataset_grid_preflight"] is True
    assert capabilities["run_launch"] is False
    assert capabilities["provider_execution"] is False


def test_dataset_catalogue_exposes_exact_registered_counts():
    response = client.get("/api/v1/datasets")
    assert response.status_code == 200
    rows = response.json()["datasets"]
    assert {row["id"]: row["expected_prompts"] for row in rows} == {
        "BREAK": 100,
        "StrategyQA": 100,
        "TaskBench": 100,
        "TravelPlanner": 100,
        "smart-administration": 60,
    }


def test_dataset_registry_exposes_engine_contract_and_non_persistent_evidence_boundary():
    response = client.get("/api/v1/datasets")
    assert response.status_code == 200
    payload = response.json()
    assert payload["registry_mode"] == "engine_catalogue_read_only"
    assert payload["evidence_persistence"] is False
    assert "not persisted" in payload["evidence_boundary"].lower()
    rows = {row["id"]: row for row in payload["datasets"]}
    assert set(rows) == {"BREAK", "StrategyQA", "TaskBench", "TravelPlanner", "smart-administration"}
    assert rows["BREAK"]["evidence_contract"]["evidence_state"] == "NOT_PERSISTED"
    assert rows["BREAK"]["evidence_contract"]["license_review_required"] is True
    assert rows["TravelPlanner"]["metadata"]["coverage_applicable"] == "annotated_constraints_only"
    assert rows["smart-administration"]["expected_prompts"] == 60
    assert rows["smart-administration"]["metadata"]["source_release_status"] == "to_be_released_with_code"


def test_config_preview_uses_engine_call_formula_and_never_launches():
    response = client.post("/api/v1/config-previews", json={
        "strategy_id": "S1",
        "datasets": ["BREAK"],
        "model_mode": "homogeneous",
        "n": 3,
        "k": 3,
        "T": 2,
        "seed_indices": [0, 1],
    })
    assert response.status_code == 200
    result = response.json()
    assert result["expected_prompt_count"] == 100
    assert result["condition_count"] == 2
    assert result["estimated_method_calls"] == result["method_calls_per_prompt"] * 200
    assert result["fixed_executor_calls"] is None
    assert result["live_provider_calls"] == 0
    assert result["run_launch_enabled"] is False


def test_config_preview_rejects_unknown_strategy_duplicate_and_invalid_seed():
    base = {
        "strategy_id": "S1",
        "datasets": ["BREAK"],
        "model_mode": "homogeneous",
        "seed_indices": [0],
    }
    assert client.post("/api/v1/config-previews", json={**base, "strategy_id": "invented"}).status_code == 422
    assert client.post("/api/v1/config-previews", json={**base, "datasets": ["BREAK", "BREAK"]}).status_code == 422
    assert client.post("/api/v1/config-previews", json={**base, "seed_indices": [5]}).status_code == 422


def test_config_preview_rejects_extra_fields():
    response = client.post("/api/v1/config-previews", json={
        "strategy_id": "S1",
        "datasets": ["BREAK"],
        "model_mode": "homogeneous",
        "run_shell": "echo unsafe",
    })
    assert response.status_code == 422


def test_strategy_catalogue_is_served_from_engine_definitions():
    response = client.get("/api/v1/strategies")
    assert response.status_code == 200
    rows = response.json()["strategies"]
    assert len(rows) == 13
    assert {row["id"] for row in rows} >= {"S1", "S12", "S10"}
    assert next(row for row in rows if row["id"] == "S1")["call_formula"] == "n+2"


def test_operator_web_interface_is_served_same_origin():
    page = client.get("/")
    assert page.status_code == 200
    assert "SOCIOWEAVE Studio" in page.text
    script = client.get("/assets/app.js")
    assert script.status_code == 200
    assert "config-previews" in script.text
    assert "preflights/e1/campaign" in script.text
    assert "jigsaw/policy" in script.text


def test_execution_and_provider_routes_are_not_exposed():
    assert client.post("/api/v1/runs", json={}).status_code in {404, 405}
    assert client.post("/api/v1/providers/execute", json={}).status_code in {404, 405}





def _write_fake_dataset_bundle(tmp_path):
    """Paper-count-sized test fixtures, explicitly not benchmark evidence."""
    import json
    from sociodec.e1_protocol import ALL_DATASETS, EXPECTED_PROMPTS

    declarations = {}
    for dataset_id in ALL_DATASETS:
        path = tmp_path / f"{dataset_id}.jsonl"
        with path.open("w", encoding="utf-8") as stream:
            for index in range(EXPECTED_PROMPTS[dataset_id]):
                row = {
                    "example_id": f"{dataset_id}-{index:03d}",
                    "prompt_text": f"Test fixture prompt {index} for {dataset_id}",
                    "split": "test",
                    "metadata": {"fixture": True},
                    "reference_data": {"fixture_reference": index},
                }
                stream.write(json.dumps(row) + "\n")
        declarations[dataset_id] = {
            "path": str(path),
            "source_version": "test-fixture-v1",
            "split": "test",
            "selection_protocol": "test fixture only; not benchmark evidence",
            "license_review_status": "approved",
            "selection_seed": 7,
            "source_url": f"https://fixture.invalid/{dataset_id}",
            "source_revision": "fixture-commit-0123456789abcdef",
            "license_url": "https://fixture.invalid/license",
            "license_identifier": "TEST-FIXTURE-ONLY",
            "license_review_evidence": "unit-test fixture; not benchmark data",
            "license_reviewed_by": "test-suite",
            "license_reviewed_at": "2026-01-01T00:00:00Z",
            "eligible_population_count": EXPECTED_PROMPTS[dataset_id],
        }
    return declarations




def _provider_manifest_fixture():
    """Build a complete non-secret Table 13 manifest using identity-only specs."""
    agents = {
        "coordinator", "specialist-1", "specialist-2", "specialist-3",
        "expert-1", "expert-2", "expert-3", "integrator",
        "participant-1", "participant-2", "participant-3", "aggregator",
        "member-1", "member-2", "member-3", "voter-1", "voter-2", "voter-3",
        "facilitator", "author", "critic", "judge", "decomposer-1", "decomposer-2",
        "synthesizer", "reviewer-1", "reviewer-2", "reviewer-3", "editor",
        "agent-A", "agent-B", "party-1", "party-2", "mediator", "moderator",
        "single-decomposer", "self-refiner", "self-consistency-sampler",
        "decomposer", "separate-evaluator", "debater-1", "debater-2",
        "independent-judge", "nominal-member-1", "nominal-member-2", "nominal-member-3",
    }
    family_a = {
        "coordinator", "specialist-1", "expert-1", "participant-1", "member-1",
        "voter-1", "author", "decomposer-1", "reviewer-1", "agent-A", "party-1",
        "single-decomposer", "self-consistency-sampler", "decomposer", "debater-1",
        "nominal-member-1",
    }
    family_b = {
        "specialist-2", "expert-2", "participant-2", "member-2", "voter-2",
        "critic", "decomposer-2", "reviewer-2", "agent-B", "party-2",
        "self-refiner", "debater-2", "nominal-member-2",
    }

    def spec(family):
        if family == "MA":
            return ProviderSpec(
                backend="openai-compatible", model_id="model-ma",
                base_url="https://ma.example.invalid/v1", api_key_env="MA_API_KEY",
                provider_name="provider-a", family_id="MA", provider_org="Provider-A",
                weight_access="closed-weight", model_revision="model-ma",
                access_date="2026-11-20",
            )
        if family == "MB":
            return ProviderSpec(
                backend="huggingface-local", model_id="org/model-mb",
                provider_name="huggingface-local", family_id="MB",
                provider_org="Provider-B", weight_access="open-weight",
                model_size="small", model_revision="a" * 40,
                access_date="2026-11-20",
            )
        return ProviderSpec(
            backend="huggingface-local", model_id="org/model-mc",
            provider_name="huggingface-local", family_id="MC",
            provider_org="Provider-C", weight_access="open-weight",
            model_size="large", model_revision="b" * 40,
            access_date="2026-11-20",
        )

    homogeneous = {agent: spec("MA") for agent in agents}
    heterogeneous = {
        agent: spec("MA" if agent in family_a else "MB" if agent in family_b else "MC")
        for agent in agents
    }
    executor = ProviderSpec(
        backend="openai-compatible", model_id="fixed-executor-model",
        base_url="https://me.example.invalid/v1", api_key_env="ME_API_KEY",
        provider_name="executor-provider", family_id="ME",
        provider_org="Executor-Provider", weight_access="closed-weight",
        model_revision="fixed-executor-model", access_date="2026-11-20",
    )
    registry = E1ProviderRegistry(
        assignments={"homogeneous": homogeneous, "heterogeneous": heterogeneous},
        executor=executor,
    )
    return registry.campaign_manifest(executor_id="fixed-me")


def test_snapshot_manifest_verifier_accepts_exact_preflight_manifest(tmp_path):
    response = client.post("/api/v1/preflights/e1", json={
        "sources": _write_fake_dataset_bundle(tmp_path),
    })
    assert response.status_code == 200, response.text
    manifest = response.json()["snapshot_manifest"]
    verified = client.post("/api/v1/snapshots/verify", json={
        "snapshot_manifest": manifest,
    })
    assert verified.status_code == 200, verified.text
    report = verified.json()
    assert report["verification"] == "MANIFEST_INTEGRITY_VALID"
    assert report["evidence_state"] == "HASH_CONSISTENCY_ONLY"
    assert report["snapshot_sha256"] == manifest["snapshot_sha256"]
    assert report["dataset_count"] == 5
    assert report["total_prompt_count"] == 460
    assert report["source_files_rechecked"] is False
    assert report["live_provider_calls"] == 0
    assert report["e1_ready"] is False


def test_snapshot_manifest_verifier_rejects_tampered_digest_and_duplicate_ids(tmp_path):
    import copy
    response = client.post("/api/v1/preflights/e1", json={
        "sources": _write_fake_dataset_bundle(tmp_path),
    })
    manifest = response.json()["snapshot_manifest"]
    tampered = copy.deepcopy(manifest)
    tampered["snapshot_sha256"] = "0" * 64
    result = client.post("/api/v1/snapshots/verify", json={"snapshot_manifest": tampered})
    assert result.status_code == 422
    assert "does not match" in result.json()["detail"]

    tampered = copy.deepcopy(manifest)
    tampered["datasets"]["BREAK"]["prompt_ids"][1] = tampered["datasets"]["BREAK"]["prompt_ids"][0]
    result = client.post("/api/v1/snapshots/verify", json={"snapshot_manifest": tampered})
    assert result.status_code == 422
    assert "must be unique" in result.json()["detail"]


def test_snapshot_manifest_verifier_rejects_missing_dataset_or_hash_keys(tmp_path):
    import copy
    response = client.post("/api/v1/preflights/e1", json={
        "sources": _write_fake_dataset_bundle(tmp_path),
    })
    manifest = response.json()["snapshot_manifest"]
    tampered = copy.deepcopy(manifest)
    del tampered["datasets"]["BREAK"]["reference_data_sha256"]
    result = client.post("/api/v1/snapshots/verify", json={"snapshot_manifest": tampered})
    assert result.status_code == 422
    assert "reference_data_sha256 keys" in result.json()["detail"]


def test_e1_preflight_validates_complete_grid_without_live_calls(tmp_path):
    response = client.post("/api/v1/preflights/e1", json={
        "sources": _write_fake_dataset_bundle(tmp_path),
    })
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["readiness"] == "DATASET_GRID_PREFLIGHT_PASS"
    assert report["evidence_state"] == "DATASET_GRID_PREFLIGHT_PASS"
    assert report["preflight_scope"] == "dataset_snapshot_and_condition_grid_only"
    assert report["condition_count"] == 4550
    assert report["method_condition_count"] == 650
    assert report["matched_baseline_condition_count"] == 3900
    assert report["live_provider_calls"] == 0
    assert report["run_launch_enabled"] is False
    assert report["grid_errors"] == []
    assert len(report["snapshot_sha256"]) == 64


def test_e1_preflight_fails_closed_for_pending_license_and_extra_metadata(tmp_path):
    sources = _write_fake_dataset_bundle(tmp_path)
    sources["BREAK"]["license_review_status"] = "pending"
    result = client.post("/api/v1/preflights/e1", json={"sources": sources})
    assert result.status_code == 422
    assert "approved" in result.json()["detail"]

    sources = _write_fake_dataset_bundle(tmp_path)
    sources["BREAK"]["secret"] = "not-allowed"
    result = client.post("/api/v1/preflights/e1", json={"sources": sources})
    assert result.status_code == 422


def test_e1_preflight_requires_all_five_dataset_files(tmp_path):
    sources = _write_fake_dataset_bundle(tmp_path)
    del sources["BREAK"]
    result = client.post("/api/v1/preflights/e1", json={"sources": sources})
    assert result.status_code == 422


def test_e1_preflight_requires_structured_reference_data(tmp_path):
    import json
    sources = _write_fake_dataset_bundle(tmp_path)
    source = tmp_path / "BREAK.jsonl"
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    rows[0]["reference_data"] = {}
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    result = client.post("/api/v1/preflights/e1", json={"sources": sources})
    assert result.status_code == 422
    assert "reference_data is required" in result.json()["detail"]



def test_engine_campaign_preflight_validates_full_rosters_and_executor_without_calls(tmp_path):
    response = client.post("/api/v1/preflights/e1/campaign", json={
        "sources": _write_fake_dataset_bundle(tmp_path),
        "provider_manifest": _provider_manifest_fixture(),
        "s12_prompt_view_factory_id": PAPER_S12_POLICY_ID,
        "s12_prompt_view_factory_sha256": PAPER_S12_POLICY_SHA256,
    })
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["readiness"] == "CAMPAIGN_CONFIGURATION_PREFLIGHT_PASS"
    assert report["evidence_state"] == "CAMPAIGN_CONFIGURATION_PREFLIGHT_PASS"
    assert report["e1_ready"] is False
    assert report["condition_count"] == 4550
    assert report["provider_rosters_validated"] == 38
    assert report["model_modes"] == ["heterogeneous", "homogeneous"]
    assert report["live_provider_calls"] == 0
    assert report["run_launch_enabled"] is False
    assert report["s12_prompt_view_factory"]["callback_executed_during_preflight"] is False
    assert report["s12_prompt_view_factory"]["factory_id"] == PAPER_S12_POLICY_ID
    assert report["s12_prompt_view_factory"]["policy_sha256"] == PAPER_S12_POLICY_SHA256
    assert report["runtime_campaign_manifest"]["runtime_policy"]["jigsaw"]["factory_id"] == PAPER_S12_POLICY_ID
    assert report["runtime_campaign_manifest"]["runtime_policy"]["jigsaw"]["policy_sha256"] == PAPER_S12_POLICY_SHA256
    assert len(report["runtime_campaign_manifest_sha256"]) == 64
    assert len(report["engine_report"]["provider_manifest_sha256"]) == 64
    assert any("S12 per-prompt facet-generation audit" in item for item in report["remaining_evidence_gates"])


def test_engine_campaign_preflight_rejects_provider_manifest_credentials(tmp_path):
    manifest = _provider_manifest_fixture()
    manifest["api_key"] = "must-not-be-accepted"
    response = client.post("/api/v1/preflights/e1/campaign", json={
        "sources": _write_fake_dataset_bundle(tmp_path),
        "provider_manifest": manifest,
        "s12_prompt_view_factory_id": PAPER_S12_POLICY_ID,
        "s12_prompt_view_factory_sha256": PAPER_S12_POLICY_SHA256,
    })
    assert response.status_code == 422
    assert "forbidden" in response.json()["detail"]


def test_engine_campaign_preflight_rejects_tampered_family_catalogue(tmp_path):
    manifest = _provider_manifest_fixture()
    manifest["model_family_catalogue"]["MA"]["provider_org"] = "Unverified-Other"
    response = client.post("/api/v1/preflights/e1/campaign", json={
        "sources": _write_fake_dataset_bundle(tmp_path),
        "provider_manifest": manifest,
        "s12_prompt_view_factory_id": PAPER_S12_POLICY_ID,
        "s12_prompt_view_factory_sha256": PAPER_S12_POLICY_SHA256,
    })
    assert response.status_code == 422



def test_registered_jigsaw_policy_endpoint_is_versioned_and_hash_addressed():
    response = client.get("/api/v1/jigsaw/policy")
    assert response.status_code == 200
    result = response.json()
    assert result["factory_id"] == PAPER_S12_POLICY_ID
    assert result["policy_sha256"] == PAPER_S12_POLICY_SHA256
    assert result["policy_manifest"]["policy_id"] == PAPER_S12_POLICY_ID


def test_studio_research_overview_exposes_only_current_capabilities():
    page = client.get("/")
    assert page.status_code == 200
    for section_id in ("overview", "configuration", "e1-preflight"):
        assert f'id="{section_id}"' in page.text
    assert "Run launch" in page.text
    assert "Current evidence gates" in page.text
    script = client.get("/assets/app.js")
    assert "renderOverview" in script.text
    assert 'capabilities.evidence_state' in script.text


def test_evidence_writes_are_disabled_without_instance_token(monkeypatch, tmp_path):
    monkeypatch.delenv("SOCIOWEAVE_EVIDENCE_WRITE_TOKEN", raising=False)
    monkeypatch.setenv("SOCIOWEAVE_EVIDENCE_DIR", str(tmp_path))
    response = client.post("/api/v1/evidence/events", json={
        "actor_claim": "operator-a", "subject": "BREAK", "payload": {"claim": "license reviewed"}
    })
    assert response.status_code == 503
    status = client.get("/api/v1/evidence/status").json()
    assert status["write_enabled"] is False
    assert status["multi_user_authorization"] is False
    assert status["execution_enabled"] is False


def test_evidence_attestation_requires_token_and_is_explicitly_self_reported(monkeypatch, tmp_path):
    monkeypatch.setenv("SOCIOWEAVE_EVIDENCE_DIR", str(tmp_path))
    monkeypatch.setenv("SOCIOWEAVE_EVIDENCE_WRITE_TOKEN", "test-instance-token")
    payload = {"actor_claim": "operator-a", "subject": "BREAK@release-1", "payload": {"claim": "reviewed"}}
    assert client.post("/api/v1/evidence/events", json=payload).status_code == 401
    response = client.post(
        "/api/v1/evidence/events", json=payload,
        headers={"Authorization": "Bearer test-instance-token"},
    )
    assert response.status_code == 200, response.text
    assert "self-reported" in response.json()["interpretation"]
    report = client.get("/api/v1/evidence/ledger/verify").json()
    assert report["verification"] == "LEDGER_CHAIN_VALID"
    assert report["event_count"] == 1
    assert report["actor_identity"] == "self_asserted_claim_not_authenticated_identity"


def test_evidence_ledger_detects_payload_tampering(monkeypatch, tmp_path):
    import sqlite3
    monkeypatch.setenv("SOCIOWEAVE_EVIDENCE_DIR", str(tmp_path))
    monkeypatch.setenv("SOCIOWEAVE_EVIDENCE_WRITE_TOKEN", "test-instance-token")
    headers = {"Authorization": "Bearer test-instance-token"}
    for index in range(2):
        response = client.post("/api/v1/evidence/events", headers=headers, json={
            "actor_claim": "operator-a", "subject": f"dataset-{index}",
            "payload": {"claim": "reviewed", "index": index},
        })
        assert response.status_code == 200
    database = tmp_path / "ledger.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("UPDATE evidence_events SET payload_json = ? WHERE sequence = 1", ('{"claim":"altered"}',))
    connection.commit()
    connection.close()
    report = client.get("/api/v1/evidence/ledger/verify").json()
    assert report["verification"] == "LEDGER_CHAIN_INVALID"
    assert any("event hash mismatch" in item for item in report["errors"])


def test_content_addressed_blob_archive_rechecks_uploaded_bytes(monkeypatch, tmp_path):
    import hashlib
    monkeypatch.setenv("SOCIOWEAVE_EVIDENCE_DIR", str(tmp_path))
    monkeypatch.setenv("SOCIOWEAVE_EVIDENCE_WRITE_TOKEN", "test-instance-token")
    headers = {"Authorization": "Bearer test-instance-token"}
    content = b"immutable source fixture; not benchmark evidence"
    digest = hashlib.sha256(content).hexdigest()
    stored = client.put(f"/api/v1/evidence/blobs/{digest}", content=content, headers=headers)
    assert stored.status_code == 200, stored.text
    assert stored.json()["stored"] is True
    repeated = client.put(f"/api/v1/evidence/blobs/{digest}", content=content, headers=headers)
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    verified = client.get(f"/api/v1/evidence/blobs/{digest}/verify")
    assert verified.status_code == 200
    assert verified.json()["verification"] == "SOURCE_BLOB_HASH_VALID"
    mismatch = client.put(f"/api/v1/evidence/blobs/{'0' * 64}", content=content, headers=headers)
    assert mismatch.status_code == 422


def test_evidence_payload_rejects_secret_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("SOCIOWEAVE_EVIDENCE_DIR", str(tmp_path))
    monkeypatch.setenv("SOCIOWEAVE_EVIDENCE_WRITE_TOKEN", "test-instance-token")
    response = client.post(
        "/api/v1/evidence/events",
        headers={"Authorization": "Bearer test-instance-token"},
        json={"actor_claim": "operator-a", "subject": "BREAK", "payload": {"api_key": "never-store"}},
    )
    assert response.status_code == 422
