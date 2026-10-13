import json

import numpy as np
import pytest

from src.config import PROJECT_ROOT, Settings
from src.evaluation.bev import BevEvaluator, recommend
from src.inference.bev import carla_to_ego, lidar_features
from src.models.experiments import ExperimentSpec
from src.services import experiment_store as store
from src.simulation.carla_capture import matching_sensor


@pytest.fixture
def experiment_settings(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None, experiment_root=tmp_path / "experiments", lab_data_root=PROJECT_ROOT / "data/lab"
    )
    for module in (
        "src.services.experiment_store",
        "src.services.experiment_registry",
        "src.api.experiments",
        "src.services.experiment_runner",
        "src.agents.experiment_agent",
    ):
        monkeypatch.setattr(f"{module}.get_settings", lambda: settings)
    return settings


def test_idempotency_and_serial_claim(experiment_settings):
    first = store.create(ExperimentSpec(), "same")
    assert store.create(ExperimentSpec(), "same")["id"] == first["id"]
    with pytest.raises(ValueError, match="different"):
        store.create(ExperimentSpec(scenario={"weather": "rain"}), "same")
    second = store.create(ExperimentSpec(), "second")
    assert store.claim("worker1")["id"] == first["id"]
    assert store.claim("worker2") is None
    store.touch(first["id"], "worker1", "capture")
    store.finish(first["id"], "worker2", "succeeded")
    assert store.get(first["id"])["status"] == "running"
    store.finish(first["id"], "worker1", "succeeded", result={"ok": True})
    assert store.claim("worker2")["id"] == second["id"]


def test_cancel_during_run_does_not_publish_success(experiment_settings):
    job = store.create(ExperimentSpec())
    store.claim("worker")
    store.cancel(job["id"])
    with pytest.raises(InterruptedError, match="Cancelled"):
        store.touch(job["id"], "worker", "inference")
    store.finish(job["id"], "worker", "succeeded", result={})
    assert store.get(job["id"])["status"] == "cancelled"


def test_queue_quota_does_not_break_idempotent_retry(experiment_settings):
    experiment_settings.experiment_max_pending = 1
    first = store.create(ExperimentSpec(), "first")
    assert store.create(ExperimentSpec(), "first")["id"] == first["id"]
    with pytest.raises(ValueError, match="queue limit"):
        store.create(ExperimentSpec(), "second")


@pytest.mark.asyncio
async def test_production_experiments_are_opt_in(client, experiment_settings):
    experiment_settings.app_env = "production"
    assert (await client.post("/api/v1/experiments", json={})).status_code == 503
    assert store.recent() == []


@pytest.mark.asyncio
async def test_agent_tool_plan_is_validated_and_does_not_enqueue(client, experiment_settings, monkeypatch):
    from src.agents import experiment_agent

    experiment_settings.experiment_agent_enabled = True
    experiment_settings.openai_api_key = "test-key-not-used"
    captured = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "draft_experiment",
                                        "arguments": ExperimentSpec().model_dump_json(),
                                    }
                                }
                            ]
                        }
                    }
                ],
                "usage": {"total_tokens": 10},
                "model": "test-model",
            }

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            captured.append(kwargs["json"])
            return FakeResponse()

    monkeypatch.setattr(experiment_agent.httpx, "AsyncClient", FakeClient)
    response = await client.post("/api/v1/experiments/plan", json={"message": "Lập thí nghiệm LiDAR"})
    assert response.status_code == 200
    assert response.json()["executed"] is False
    assert store.recent() == []
    assert len(captured) == 1
    assert captured[0]["max_tokens"] == 700
    assert captured[0]["tools"][0]["function"]["strict"] is True


@pytest.mark.asyncio
async def test_api_rejects_incompatible_radar_and_unknown_models(client, experiment_settings):
    for model_id in ("flow_t4", "occupancy_radar", "../bad"):
        response = await client.post("/api/v1/experiments", json={"model_ids": [model_id]})
        assert response.status_code == 422
    assert (await client.post("/api/v1/experiments", json={"scenario": {"frames": 82}})).status_code == 422
    assert (await client.post("/api/v1/experiments", json={"source": "nuscenes"})).status_code == 422


@pytest.mark.asyncio
async def test_create_poll_and_cancel(client, experiment_settings):
    response = await client.post("/api/v1/experiments", json={}, headers={"Idempotency-Key": "test"})
    assert response.status_code == 201
    ident = response.json()["id"]
    assert (await client.get(f"/api/v1/experiments/{ident}")).json()["status"] == "queued"
    assert (await client.post(f"/api/v1/experiments/{ident}/cancel")).json()["status"] == "cancelled"
    assert (await client.get("/api/v1/experiments/not-an-id")).status_code == 422


@pytest.mark.asyncio
async def test_agent_disabled_never_creates_job(client, experiment_settings):
    response = await client.post("/api/v1/experiments/plan", json={"message": "Chạy mưa"})
    assert response.status_code == 503
    assert store.recent() == []


def test_evaluator_ignores_unobserved_and_handles_empty_classes():
    evaluator = BevEvaluator()
    frame = {
        "labels": np.array([[0, 2], [1, 2]], np.uint8),
        "valid": np.array([[True, True], [False, True]]),
        "flow": np.zeros((2, 2, 2)),
        "flow_valid": np.array([[False, True], [False, False]]),
    }
    prediction = {"occupancy": np.array([[0, 2], [2, 0]], np.uint8), "flow": np.full((2, 2, 2), 3.0)}
    evaluator.add(frame, prediction)
    result = evaluator.report([10, 20])
    assert result["evaluated_cells"] == 3
    assert result["occupied_iou"] == 0.5
    assert result["class_iou"]["static"] is None
    assert result["flow_epe_m_s"] == pytest.approx(np.sqrt(18))
    assert recommend({"a": {"metrics": result}}, max_latency_ms=5)["selected"] is None
    cached = evaluator.report([])
    assert cached["latency_model_only_ms"] is None
    assert recommend({"a": {"metrics": cached}}, max_latency_ms=500)["selected"] is None


def test_carla_coordinate_conversion_and_lidar_features():
    sensor = np.eye(4)
    sensor[:3, 3] = [10, 2, 1]
    point = carla_to_ego(np.array([[1, 3, 0]]), sensor, np.eye(4))
    np.testing.assert_allclose(point, [[11, -5, 1]])
    x = lidar_features(point, [255])
    row, col = 122, 90
    assert x[0, row, col] == pytest.approx(np.log(2) / 3)
    assert x[1, row, col] == pytest.approx(0.4)
    assert x[3, row, col] == 1


def test_sensor_future_frame_is_not_silently_matched():
    import queue
    from types import SimpleNamespace

    q = queue.Queue()
    q.put(SimpleNamespace(frame=11))
    with pytest.raises(RuntimeError, match="skipped"):
        matching_sensor(q, 10, 1, lambda: None)


def test_worker_evaluates_same_frames_and_reuses_cache(experiment_settings, monkeypatch):
    from src.services import experiment_runner as runner

    calls = []
    frame = {
        "id": "fixed",
        "x": np.zeros((7, 200, 200), np.float32),
        "labels": np.ones((200, 200), np.uint8),
        "valid": np.ones((200, 200), bool),
        "flow": np.zeros((2, 200, 200), np.float32),
        "flow_valid": np.zeros((200, 200), bool),
        "rotation": np.eye(3),
        "translation": np.zeros(3),
    }
    monkeypatch.setattr(
        runner, "nuscenes_frames", lambda spec, pulse: ([frame], {"source": "nuscenes", "limitations": []})
    )

    class FakeCheckpoint:
        def __init__(self, name, device):
            self.digest = "fixed-checkpoint"
            self.task = "occupancy"
            self.device = device
            self.timing = []
            self.torch = type("Runtime", (), {"__version__": "test"})

        def predict(self, frames, index):
            calls.append(index)
            self.timing.append(1)
            return {"occupancy": np.ones((200, 200), np.uint8), "flow": None}

    monkeypatch.setattr("src.inference.current.CurrentCheckpoint", FakeCheckpoint)
    spec = ExperimentSpec(source="nuscenes", scene_id="scene-0103")
    store.create(spec)
    first = runner.run_once()
    assert first["status"] == "succeeded"
    assert first["result"]["models"]["occupancy_lidar"]["metrics"]["occupied_iou"] == 1
    store.create(spec)
    second = runner.run_once()
    assert second["result"]["models"]["occupancy_lidar"]["cache_hits"] == 1
    assert calls == [0]
    assert json.dumps(second["result"], allow_nan=False)


def test_capture_progress_is_bounded_and_only_for_running_jobs(experiment_settings):
    job = store.create(ExperimentSpec())
    store.claim("progress-test")
    path = experiment_settings.experiment_root / job["id"] / "capture/progress.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"completed": 2, "total": 4}))
    assert store.get(job["id"])["capture_progress"] == {"completed": 2, "total": 4}
    path.write_text(json.dumps({"completed": 5, "total": 4}))
    assert store.get(job["id"])["capture_progress"] is None
    path.write_text("{")
    assert store.get(job["id"])["capture_progress"] is None
    path.write_text(json.dumps({"completed": 4, "total": 4}))
    store.finish(job["id"], "progress-test", "succeeded", result={})
    assert store.get(job["id"])["capture_progress"] is None
