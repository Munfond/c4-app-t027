import pytest

from src.config import PROJECT_ROOT, Settings
from src.models.experiments import EngineerReview, SensorStudySpec
from src.services import agent_evidence as evidence
from src.services import experiment_store as store
from src.services import sensor_studies as studies


@pytest.fixture
def measured_study(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, experiment_root=tmp_path, lab_data_root=PROJECT_ROOT / "data/lab")
    monkeypatch.setattr(store, "get_settings", lambda: settings)
    monkeypatch.setattr("src.services.experiment_registry.get_settings", lambda: settings)

    def create(candidate_iou=0.49, candidate_cost=500, reference="same", failed=False):
        study = studies.create(SensorStudySpec(
            scenarios=[{"map": "Town01", "frames": 2, "vehicles": 2, "pedestrians": 0}],
            profiles=[{"name": "half", "lidar": {"points_per_second": 300000}}],
        ))
        for iou, cost, sha in ((0.5, 1000, "same"), (candidate_iou, candidate_cost, reference)):
            job = store.claim("test")
            result = {"manifest": {"reference_sha256": sha, "frames": [{"id": "one"}],
                                   "sensor_cost": {"estimated_lidar_bytes_per_second": cost}},
                      "models": {"occupancy_lidar": {"metrics": {"occupied_iou": iou,
                                                   "latency_model_only_ms": None}, "cache_hits": 1}}}
            is_failure = failed and job["id"] != study["jobs"][0]["id"]
            store.finish(job["id"], "test", "failed" if is_failure else "succeeded",
                         result=None if is_failure else result, error="sensor timeout" if is_failure else None)
            studies.advance(study["id"])
        return study["id"]
    return create


def decision(ident):
    return evidence.evidence(ident)["environments"][0]["decisions"][0]


def test_measured_improvement_and_traceability(measured_study):
    ident = measured_study()
    value = decision(ident)
    assert value["outcome"] == "improved"
    candidate = value["trials"][1]
    assert candidate["reduction"] == 0.5
    assert candidate["configuration"]["scenario"]["lidar"]["points_per_second"] == 300000
    assert candidate["checkpoint_sha256"]
    assert candidate["latency_model_only_ms"] is None
    assert "GPU" in value["explanation"]
    assert evidence.evidence(ident)["evidence_sha256"] == evidence.evidence(ident)["evidence_sha256"]


def test_no_improvement_is_not_forced_recommendation(measured_study):
    value = decision(measured_study(candidate_iou=0.1))
    assert value["outcome"] == "no_improvement"
    assert value["selected"] == "baseline"
    assert "below_minimum_iou" in value["trials"][1]["reasons"]
    assert "quality_drop_exceeds_limit" in value["trials"][1]["reasons"]
    assert decision(measured_study(candidate_cost=1200))["outcome"] == "no_improvement"


def test_failed_or_unpaired_trial_never_claims_no_possible_improvement(measured_study):
    assert decision(measured_study(reference="different"))["outcome"] == "inconclusive"
    assert decision(measured_study(failed=True))["outcome"] == "inconclusive"


@pytest.mark.asyncio
async def test_review_persists_snapshot_without_changing_metrics(client, measured_study):
    ident = measured_study()
    path = f"/api/v1/experiments/sensor-agent/{ident}"
    snapshot = (await client.get(path + "/evidence")).json()
    payload = {"reviewer": "Engineer", "verdict": "needs_evidence", "notes": "Need a held-out crowded scene",
               "evidence_sha256": snapshot["evidence_sha256"]}
    response = await client.post(path + "/reviews", json=payload)
    assert response.status_code == 201
    assert response.json()["used_for_training"] is False
    assert response.json()["reviewer_identity_verified"] is False
    assert (await client.get(path + "/evidence")).json() == snapshot
    assert len((await client.get(path + "/reviews")).json()["items"]) == 1
    with evidence.connection() as db:
        assert db.execute("SELECT snapshot FROM agent_reviews").fetchone()[0]
    invalid = payload | {"evidence_sha256": "0" * 64}
    assert (await client.post(path + "/reviews", json=invalid)).status_code == 409
    assert (await client.post(path + "/reviews", json=payload | {"notes": ""})).status_code == 422


def test_review_snapshot_outlives_temporary_capture_scope(measured_study, tmp_path):
    with store.scope(tmp_path / "temporary-session"):
        ident = measured_study()
        snapshot = evidence.evidence(ident)
        evidence.save_review(ident, EngineerReview(reviewer="Test engineer", verdict="needs_evidence",
            notes="Need additional measured scenes", evidence_sha256=snapshot["evidence_sha256"]))
    with evidence.connection() as db:
        assert db.execute("SELECT study_id FROM agent_reviews").fetchone()[0] == ident
    assert not (tmp_path / "temporary-session" / "engineer-feedback.sqlite3").exists()


def test_cannot_review_unfinished_study(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, experiment_root=tmp_path, lab_data_root=PROJECT_ROOT / "data/lab")
    monkeypatch.setattr(store, "get_settings", lambda: settings)
    monkeypatch.setattr("src.services.experiment_registry.get_settings", lambda: settings)
    study = studies.create(SensorStudySpec(scenarios=[{}], profiles=[{"name": "half", "lidar": {"points_per_second": 300000}}]))
    with pytest.raises(ValueError, match="complete"):
        evidence.save_review(study["id"], EngineerReview(reviewer="Engineer", verdict="accept",
            notes="Not yet measured results", evidence_sha256="0" * 64))


def test_replay_uses_per_model_reference_cost_and_keeps_camera_separate(monkeypatch):
    study = {"id": "1" * 32, "source": "dataset_replay", "checkpoint_sha256": "a" * 64,
             "spec": {"model_ids": ["occupancy_radar"], "max_iou_drop": 0.02, "min_occupied_iou": 0.3}}
    rows = [{"job_id": str(i) * 32, "profile": profile, "status": "succeeded", "error": None,
             "reference_matches_baseline": True, "sensor_cost": {"lidar_payload_bytes": 10000,
                                                                     "radar_payload_bytes": cost},
             "models": {"occupancy_radar": {"metrics": {"occupied_iou": 0.5}}}}
            for i, profile, cost in ((1, "baseline", 1000), (2, "half", 500))]
    monkeypatch.setattr(studies, "get", lambda _: study)
    monkeypatch.setattr(studies, "comparison", lambda _: {"environments": [{"environment": 0, "scenario": {},
        "trials": rows, "model_choices": {"occupancy_radar": {"profile": "half"}}}], "limitations": []})
    monkeypatch.setattr(store, "get", lambda _: {"spec": {"request": {}, "checkpoints": {}}, "result": {}})
    value = decision(study["id"])
    assert value["trials"][1]["reduction"] == 0.5
    assert value["cost_unit"] == "bytes/frame"
