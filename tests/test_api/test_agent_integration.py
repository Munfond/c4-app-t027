"""Regressions at the CARLA/replay integration boundary."""
import pytest

from src.models.experiments import SensorStudySpec
from src.services import experiment_store as store
from src.services import sensor_studies as studies


def test_absolute_quality_floor_excludes_even_the_baseline(monkeypatch):
    fake = {
        "id": "study", "status": "completed", "source": "carla",
        "spec": {"scenarios": [{}], "max_iou_drop": 0.02, "min_occupied_iou": 0.3},
        "jobs": [],
    }
    for profile, iou, rate in (("baseline", 0.1, 1000), ("half", 0.09, 500)):
        fake["jobs"].append({
            "id": profile, "environment": 0, "profile": profile, "status": "succeeded", "error": None,
            "result": {
                "manifest": {"reference_sha256": "paired", "sensor_cost": {
                    "estimated_lidar_bytes_per_second": rate}},
                "models": {"occupancy_lidar": {"metrics": {"occupied_iou": iou}}},
            },
        })
    monkeypatch.setattr(studies, "get", lambda _: fake)
    report = studies.comparison("study")
    assert report["environments"][0]["provisional_selected"] is None


def test_quality_floor_can_be_configured_but_is_bounded():
    payload = {"scenarios": [{}], "profiles": [{"name": "half", "lidar": {}}]}
    assert SensorStudySpec(**payload).min_occupied_iou == 0.3
    assert SensorStudySpec(**payload, min_occupied_iou=0.6).min_occupied_iou == 0.6
    with pytest.raises(ValueError):
        SensorStudySpec(**payload, min_occupied_iou=1.1)


@pytest.mark.asyncio
async def test_capture_download_uses_scoped_store(client, tmp_path, monkeypatch):
    capture_id = "a" * 32
    scoped = tmp_path / "session"
    target = scoped / capture_id / "capture" / "frame_0000.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"scope":"session"}')
    monkeypatch.setattr(store, "get", lambda _: {
        "spec": {"request": {"source": "carla", "capture_id": capture_id}}})
    with store.scope(scoped):
        response = await client.get(f"/api/v1/experiments/{'b' * 32}/capture/0/json")
    assert response.status_code == 200
    assert response.json() == {"scope": "session"}


@pytest.mark.asyncio
async def test_capture_does_not_fall_back_to_another_session(client, tmp_path, monkeypatch):
    capture_id = "a" * 32
    target = tmp_path / "other-session" / capture_id / "capture" / "frame_0000.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"scope":"other"}')
    monkeypatch.setattr(store, "get", lambda _: {
        "spec": {"request": {"source": "carla", "capture_id": capture_id}}})
    with store.scope(tmp_path / "current-session"):
        response = await client.get(f"/api/v1/experiments/{'b' * 32}/capture/0/json")
    assert response.status_code == 404
