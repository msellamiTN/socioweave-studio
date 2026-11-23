from fastapi.testclient import TestClient

from socioweave_studio.api.app import app

client = TestClient(app)


def test_health_and_capabilities_keep_execution_disabled():
    assert client.get("/api/v1/health").json()["status"] == "ok"
    capabilities = client.get("/api/v1/capabilities").json()
    assert capabilities["configuration_preview"] is True
    assert capabilities["full_e1_preflight"] is True
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


def test_execution_and_provider_routes_are_not_exposed():
    assert client.post("/api/v1/runs", json={}).status_code in {404, 405}
    assert client.post("/api/v1/providers/execute", json={}).status_code in {404, 405}



def _write_fake_dataset_bundle(tmp_path):
    """Create paper-sized fixtures for API tests only; never benchmark evidence."""
    import json
    from sociodec.e1_protocol import ALL_DATASETS, EXPECTED_PROMPTS

    declarations = {}
    for dataset_id in ALL_DATASETS:
        path = tmp_path / f"{dataset_id}.jsonl"
        with path.open("w", encoding="utf-8") as stream:
            for index in range(EXPECTED_PROMPTS[dataset_id]):
                row = {
                    "example_id": f"{dataset_id}-{index:03d}",
                    "prompt_text": f"Test-only fixture prompt {index} for {dataset_id}",
                    "split": "test",
                    "metadata": {"fixture": True},
                    "reference_data": {"fixture_reference": index},
                }
                stream.write(json.dumps(row) + "\\n")
        declarations[dataset_id] = {
            "path": str(path),
            "source_version": "test-fixture-v1",
            "split": "test",
            "selection_protocol": "unit-test fixture; not benchmark evidence",
            "license_review_status": "approved",
            "selection_seed": 7,
        }
    return declarations


def test_e1_preflight_validates_full_grid_with_zero_provider_calls(tmp_path):
    response = client.post("/api/v1/preflights/e1", json={
        "sources": _write_fake_dataset_bundle(tmp_path),
        "n": 3, "k": 3, "T": 2,
    })
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["readiness"] == "CONFIG_PREFLIGHT_PASS"
    assert report["condition_count"] == 4550
    assert report["method_condition_count"] == 650
    assert report["matched_baseline_condition_count"] == 3900
    assert report["live_provider_calls"] == 0
    assert report["run_launch_enabled"] is False
    assert report["grid_errors"] == []
    assert len(report["snapshot_sha256"]) == 64


def test_e1_preflight_rejects_pending_license_and_nested_extra_keys(tmp_path):
    sources = _write_fake_dataset_bundle(tmp_path)
    sources["BREAK"]["license_review_status"] = "pending"
    response = client.post("/api/v1/preflights/e1", json={"sources": sources})
    assert response.status_code == 422
    assert "approved" in response.json()["detail"]

    sources = _write_fake_dataset_bundle(tmp_path)
    sources["BREAK"]["unexpected"] = "no"
    response = client.post("/api/v1/preflights/e1", json={"sources": sources})
    assert response.status_code == 422


def test_e1_preflight_requires_exact_five_dataset_sources(tmp_path):
    sources = _write_fake_dataset_bundle(tmp_path)
    sources.pop("BREAK")
    response = client.post("/api/v1/preflights/e1", json={"sources": sources})
    assert response.status_code == 422


def test_e1_preflight_rejects_missing_structured_reference(tmp_path):
    import json
    sources = _write_fake_dataset_bundle(tmp_path)
    source = tmp_path / "BREAK.jsonl"
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    rows[0]["reference_data"] = {}
    source.write_text("".join(json.dumps(row) + "\\n" for row in rows), encoding="utf-8")
    response = client.post("/api/v1/preflights/e1", json={"sources": sources})
    assert response.status_code == 422
    assert "reference_data is required" in response.json()["detail"]


def test_e1_preflight_never_exposes_run_launch_route():
    assert client.post("/api/v1/runs", json={}).status_code in {404, 405}
