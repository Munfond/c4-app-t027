import json
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from src.config import PROJECT_ROOT, Settings
from src.inference.camera_replay import CameraDetector, camera_variant, detection_retention, weather_image
from src.models.experiments import ExperimentSpec
from src.models.replay import CameraReduction, PointReduction, ReplayStudySpec
from src.services import dataset_replay as replay
from src.services import experiment_store as store
from src.services import sensor_studies as studies
from src.services.experiment_runner import run_once


@pytest.fixture
def replay_data(tmp_path, monkeypatch):
    root = tmp_path / "raw"
    root.mkdir()
    pixels = np.random.default_rng(2).integers(0, 255, (64, 96, 3), dtype=np.uint8)
    Image.fromarray(pixels).save(root / "camera.jpg")
    (root / "sensor.bin").write_bytes(b"fixture")
    settings = Settings(_env_file=None, experiment_root=tmp_path / "experiments",
                        nusc_root=root, lab_data_root=PROJECT_ROOT / "data/lab")
    for module in ("src.services.experiment_store", "src.services.experiment_registry", "src.services.experiment_runner",
                   "src.services.dataset_replay", "src.inference.camera_replay", "src.inference.current",
                   "src.api.experiments", "src.agents.sensor_agent"):
        monkeypatch.setattr(f"{module}.get_settings", lambda: settings)
    points = np.array([[10 + i * 0.4, 4 + i * 0.2, 1] for i in range(20)], dtype=float)
    labels = np.zeros((200, 200), dtype=np.uint8)
    labels[100:130, 100:130] = 1
    keys = {}
    for channel in ["LIDAR_TOP", *replay.RADARS, *replay.CAMERAS]:
        keys[("token", channel)] = {"filename": "camera.jpg" if channel.startswith("CAM") else "sensor.bin",
                                    "prev": "", "calibrated_sensor_token": "calibration"}
    ds = SimpleNamespace(root=str(root), key=keys, sd={},
        cs={"calibration": {"translation": [0, 0, 0], "rotation": [1, 0, 0, 0]}},
        by_split={"val": ["token"]}, scene={"scene": {"name": "scene-0103", "token": "scene", "description": "fixture"}},
        sample={"token": {"scene_token": "scene", "timestamp": 0}},
        boxes=lambda token: [], keyframe_lidar=lambda token: (points.copy(), np.ones(20) * 100),
        keyframe_radar=lambda token, chans: [(points.copy(), np.ones(20) * 10, np.ones(20) * 2)],
        labels=lambda token: labels.copy(), pose=lambda token: (np.eye(3), np.zeros(3)))
    monkeypatch.setattr(replay, "dataset", lambda: ds)
    return settings, ds


def study_spec():
    return ReplayStudySpec(scenarios=[{"scene_id": "scene-0103", "frames": 1}],
        profiles=[{"name": "half", "lidar": {"keep_fraction": 0.5}, "radar": {"keep_fraction": 0.5},
                   "camera": {"scale": 0.5}}])


@pytest.mark.parametrize("message,expected", [
    ("scene 40", {"scene-0040"}),
    ("SCENE-0103, 40 frames", {"scene-0103"}),
    ("cảnh 916 và scene 103", {"scene-0916", "scene-0103"}),
    ("40 frames", set()),
    ("scene 12345", set()),
])
def test_explicit_scene_numbers(message, expected):
    from src.agents.replay_agent import requested_scenes

    assert requested_scenes(message) == expected


@pytest.mark.asyncio
async def test_unavailable_scene_rejected_before_llm(replay_data, monkeypatch):
    from src.agents import replay_agent

    settings, _ = replay_data
    settings.experiment_agent_enabled = True
    settings.openai_api_key = "mock-key"

    async def forbidden_provider(*args, **kwargs):
        pytest.fail("Unavailable scenes must not spend LLM tokens")

    monkeypatch.setattr(replay_agent, "completion", forbidden_provider)
    with pytest.raises(ValueError, match="scene-0040"):
        await replay_agent.start("Thử scene 40")
    assert store.recent() == []


@pytest.mark.asyncio
async def test_api_unavailable_scene_does_not_create_another_study(client, replay_data, monkeypatch):
    from src.agents import replay_agent

    settings, _ = replay_data
    settings.experiment_agent_enabled = True
    settings.openai_api_key = "mock-key"
    previous = studies.create(study_spec())

    async def forbidden_provider(*args, **kwargs):
        pytest.fail("Scene preflight must run before the provider")

    monkeypatch.setattr(replay_agent, "completion", forbidden_provider)
    response = await client.post("/api/v1/experiments/replay/agent/start", json={"message": "scene 40"})
    assert response.status_code == 422
    assert "scene-0040" in response.json()["detail"]
    assert [s["id"] for s in studies.recent()] == [previous["id"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("message,rejected", [("scene 916", True), ("scene 103, 40 frames", False)])
async def test_agent_cannot_substitute_explicit_scene(replay_data, monkeypatch, message, rejected):
    from src.agents import replay_agent

    settings, _ = replay_data
    settings.experiment_agent_enabled = True
    settings.openai_api_key = "mock-key"
    monkeypatch.setattr(replay_agent, "catalog", lambda: {
        "ready": True, "scenes": [{"id": "scene-0103"}, {"id": "scene-0916"}]
    })

    async def provider(*args, **kwargs):
        return {"choices": [{"message": {"tool_calls": [{"id": "scene-call", "function": {
            "name": "create_replay_study", "arguments": json.dumps(study_spec().model_dump())}}]}}]}

    monkeypatch.setattr(replay_agent, "completion", provider)
    if rejected:
        with pytest.raises(ValueError, match="không khớp"):
            await replay_agent.start(message)
        assert store.recent() == []
    else:
        study = await replay_agent.start(message)
        assert study["spec"]["scenarios"][0]["scene_id"] == "scene-0103"


def test_replay_validation_and_missing_raw(replay_data):
    settings, _ = replay_data
    with pytest.raises(ValueError):
        PointReduction(keep_fraction=2)
    with pytest.raises(ValueError):
        ReplayStudySpec(scenarios=study_spec().scenarios, profiles=[{"name": "baseline"}])
    with pytest.raises(ValueError):
        ReplayStudySpec(scenarios=study_spec().scenarios, profiles=study_spec().profiles, cameras=["../image"])
    (settings.nusc_root / "sensor.bin").unlink()
    with pytest.raises(FileNotFoundError):
        studies.create(study_spec())
    assert store.recent() == []


def test_missing_reference_sweep_rejects_study_before_queueing(replay_data):
    _, ds = replay_data
    ds.key[("token", "LIDAR_TOP")]["prev"] = "missing-sweep"
    ds.sd["missing-sweep"] = {"filename": "sweeps/LIDAR_TOP/missing.bin", "prev": ""}
    with pytest.raises(FileNotFoundError, match="nhãn tham chiếu IoU"):
        studies.create(study_spec())
    assert store.recent() == []


def test_reductions_preserve_original_reference_and_radar_channels(replay_data):
    settings, ds = replay_data
    commands = studies.trials(study_spec())
    baseline, base = replay.frames(commands[0]["spec"].replay, settings.experiment_root / "baseline", lambda *a: None)
    reduced, candidate = replay.frames(commands[1]["spec"].replay, settings.experiment_root / "half", lambda *a: None)
    np.testing.assert_array_equal(baseline[0]["labels"], reduced[0]["labels"])
    assert base["dataset_reference_sha256"] == candidate["dataset_reference_sha256"]
    assert candidate["sensor_cost"]["lidar_points"] == base["sensor_cost"]["lidar_points"] / 2
    assert candidate["sensor_cost"]["radar_points"] == base["sensor_cost"]["radar_points"] / 2
    expected = ds.bev_inputs("token") if hasattr(ds, "bev_inputs") else replay.radar_features(ds.keyframe_radar("token", ()))
    # Mean RCS and compensated speed remain measured values after point reduction.
    assert float(reduced[0]["x"][5].max()) == pytest.approx(10 / 50)
    assert float(reduced[0]["x"][6].max()) == pytest.approx(2 / 20)
    assert expected.shape == (3, 200, 200)
    assert candidate["camera"]["mode"] == "image_fidelity_only"
    assert candidate["camera"]["detection_retention"] is None


def test_sensor_coordinate_fov_and_stable_sampling():
    points = np.array([[0, 5, 0], [0, -5, 0], [5, 0, 0]], dtype=float)
    rotation = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
    out, indices = replay.reduce_points(points, PointReduction(horizontal_fov=30), np.random.default_rng(1),
                                       np.zeros(3), rotation)
    np.testing.assert_array_equal(indices, [0])
    np.testing.assert_array_equal(out, points[:1])


def test_weather_and_camera_metrics_are_deterministic():
    image = Image.fromarray(np.random.default_rng(3).integers(0, 255, (64, 96, 3), dtype=np.uint8))
    for weather in ("rain", "fog"):
        a = weather_image(image, weather, 0.5, np.random.default_rng(4))
        b = weather_image(image, weather, 0.5, np.random.default_rng(4))
        np.testing.assert_array_equal(np.asarray(a), np.asarray(b))
        assert not np.array_equal(np.asarray(image), np.asarray(a))
    _, baseline_bytes, baseline = camera_variant(image, CameraReduction())
    _, half_bytes, half = camera_variant(image, CameraReduction(scale=0.5, jpeg_quality=60))
    assert len(half_bytes) < len(baseline_bytes)
    assert half["psnr_db"] < baseline["psnr_db"]


def test_detector_retention_one_to_one_and_no_baseline():
    ref = np.array([[0, 0, 10, 10, 0.9, 1], [0, 0, 10, 10, 0.8, 1]])
    candidate = ref[:1]
    assert detection_retention(ref, candidate) == 0.5
    assert detection_retention(np.empty((0, 6)), candidate) is None
    assert detection_retention(ref, np.array([[0, 0, 10, 10, 0.9, 2]])) == 0


def test_camera_onnx_contract_and_coordinate_scaling(replay_data, monkeypatch):
    settings, _ = replay_data
    settings.replay_camera_onnx = settings.nusc_root / "detector.onnx"
    settings.replay_camera_onnx.write_bytes(b"fixture detector; never production weights")
    output = np.array([[[0, 0, 16, 16, 0.9, 1]]], dtype=np.float32)
    session = SimpleNamespace(get_inputs=lambda: [SimpleNamespace(shape=[1, 3, 32, 32], name="image")],
                              run=lambda *args: [output])
    import sys

    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(InferenceSession=lambda *args, **kwargs: session))
    detector = CameraDetector()
    boxes = detector.predict(Image.new("RGB", (100, 50)))
    assert boxes[0][:4] == [0, 0, 50, 25]
    assert detector.digest
    output = np.ones((1, 4, 8))
    with pytest.raises(ValueError, match="post-NMS"):
        detector.predict(Image.new("RGB", (100, 50)))


def test_real_checkpoint_worker_and_autoadvance(replay_data):
    # Inference uses all three repository checkpoints; raw input is a labeled fixture.
    study = studies.create(study_spec())
    first = run_once()
    assert first["status"] == "succeeded", first["error"]
    assert set(first["result"]["models"]) == {"occupancy_lidar", "occupancy_radar", "occupancy_lidar_radar"}
    studies.advance_pending_replays()
    second = run_once()
    assert second["status"] == "succeeded", second["error"]
    study = studies.get(study["id"])
    assert study["status"] == "completed"
    report = studies.comparison(study["id"])
    assert all(t["reference_matches_baseline"] for t in report["environments"][0]["trials"])
    assert report["environments"][0]["camera_evaluation_mode"] == "image_fidelity_only"
    json.dumps(report, allow_nan=False)


@pytest.mark.asyncio
async def test_replay_api_create_poll_preview_cancel(client, replay_data):
    catalog = await client.get("/api/v1/experiments/replay/catalog")
    assert catalog.json()["ready"]
    response = await client.post("/api/v1/experiments/replay/studies", json=study_spec().model_dump())
    assert response.status_code == 201, response.text
    study = response.json()
    assert (await client.get(f"/api/v1/experiments/sensor-agent/{study['id']}/comparison")).status_code == 409
    run_once()
    job_id = study["jobs"][0]["id"]
    preview = await client.get(f"/api/v1/experiments/{job_id}/sensor-preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["frame_id"] == "token"
    assert preview.json()["sensors"]["lidar"]["count"] == 20
    assert preview.json()["sensors"]["radar"]["count"] == 100
    assert (await client.get(f"/api/v1/experiments/{job_id}/sensor-preview?index=19")).status_code == 404
    for reference in ("true", "false"):
        response = await client.get(f"/api/v1/experiments/{job_id}/camera?reference={reference}")
        assert response.status_code == 200
    assert (await client.get(f"/api/v1/experiments/{job_id}/camera?channel=../../secret")).status_code == 404
    response = await client.post(f"/api/v1/experiments/sensor-agent/{study['id']}/cancel")
    assert response.json()["status"] == "cancelled"
    assert len(store.recent()) == 1


@pytest.mark.asyncio
async def test_replay_agent_creates_real_jobs_with_mock_provider(replay_data, monkeypatch):
    from src.agents import replay_agent

    settings, _ = replay_data
    settings.experiment_agent_enabled = True
    settings.openai_api_key = "mock-never-sent"

    async def provider(*args, **kwargs):
        return {"choices": [{"message": {"tool_calls": [{"id": "call_replay", "function": {
            "name": "create_replay_study", "arguments": study_spec().model_dump_json()}}]}}]}

    monkeypatch.setattr(replay_agent, "completion", provider)
    study = await replay_agent.start("Thử cả ba sensor")
    assert study["metadata"]["tool"] == "create_replay_study"
    assert len(store.recent()) == 1


@pytest.mark.asyncio
async def test_agent_reports_repeated_plan_and_distinguishes_changed_settings(replay_data, monkeypatch):
    from src.agents import replay_agent

    settings, _ = replay_data
    settings.experiment_agent_enabled = True
    settings.openai_api_key = "mock-never-sent"
    arguments = study_spec().model_dump()

    async def provider(*args, **kwargs):
        return {"choices": [{"message": {"tool_calls": [{"id": "call_plan", "function": {
            "name": "create_replay_study", "arguments": json.dumps(arguments)}}]}}]}

    monkeypatch.setattr(replay_agent, "completion", provider)
    first = await replay_agent.start("Thử cấu hình half")
    second = await replay_agent.start("Đánh giá lại giữ 50% điểm")
    assert first["metadata"]["same_plan_as"] is None
    assert second["metadata"]["same_plan_as"] == first["id"]
    assert second["metadata"]["request"] == "Đánh giá lại giữ 50% điểm"
    assert first["jobs"][0]["id"] != second["jobs"][0]["id"]
    arguments["profiles"][0]["lidar"]["keep_fraction"] = 0.25
    third = await replay_agent.start("Đổi LiDAR còn 25%")
    assert third["metadata"]["same_plan_as"] is None
    assert third["spec"]["profiles"][0]["lidar"]["keep_fraction"] == 0.25


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["baseline", "duplicate", "conflict", "custom_baseline", "baseline_only"])
async def test_agent_profile_normalization_and_diagnostics(replay_data, monkeypatch, case):
    from src.agents import replay_agent

    settings, _ = replay_data
    settings.experiment_agent_enabled = True
    settings.openai_api_key = "mock-secret-never-sent"
    arguments = study_spec().model_dump()
    candidate = arguments["profiles"][0]
    if case == "baseline":
        arguments["profiles"].insert(0, {"name": "baseline"})
    elif case in ("duplicate", "conflict"):
        duplicate = json.loads(json.dumps(candidate))
        if case == "conflict":
            duplicate["lidar"]["keep_fraction"] = 0.75
        arguments["profiles"].append(duplicate)
    elif case == "custom_baseline":
        arguments["profiles"].insert(0, {"name": "baseline", "lidar": {"keep_fraction": 0.5}})
    else:
        arguments["profiles"] = [{"name": "baseline"}]
    calls = []

    async def provider(*args, **kwargs):
        calls.append(True)
        return {"model": "mock-model", "usage": {"total_tokens": 123},
                "choices": [{"message": {"tool_calls": [{"id": "call_normalize", "function": {
                    "name": "create_replay_study", "arguments": json.dumps(arguments)}}]}}]}

    monkeypatch.setattr(replay_agent, "completion", provider)
    path = settings.experiment_root / "agent-plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if case in ("baseline", "duplicate"):
        study = await replay_agent.start("Compare baseline and half", diagnostics_path=path)
        assert [p["name"] for p in study["spec"]["profiles"]] == [candidate["name"]]
        assert len(studies.trials(ReplayStudySpec.model_validate(study["spec"]))) == 2
        assert study["metadata"]["corrections"]
        assert len(store.recent()) == 1
    else:
        with pytest.raises(ValueError):
            await replay_agent.start("Compare baseline and half", diagnostics_path=path)
        assert store.recent() == []
    diagnostic = json.loads(path.read_text(encoding="utf-8"))
    assert diagnostic["arguments"] == arguments
    assert diagnostic["usage"]["total_tokens"] == 123
    assert diagnostic["status"] == ("created" if case in ("baseline", "duplicate") else "rejected")
    assert settings.openai_api_key not in path.read_text(encoding="utf-8")
    assert len(calls) == 1


def test_replay_rejects_flow_models(replay_data):
    trial = studies.trials(study_spec())[0]["spec"].replay
    with pytest.raises(ValueError, match="occupancy"):
        store.create(ExperimentSpec(source="dataset_replay", replay=trial, model_ids=["flow_t1"]))


def test_agent_model_schema_lists_only_existing_checkpoints():
    from src.agents.sensor_agent import tool

    schema = tool("create_replay_study", "Replay", ReplayStudySpec.model_json_schema())["function"]["parameters"]
    assert schema["properties"]["model_ids"]["items"]["enum"] == [
        "occupancy_lidar", "occupancy_radar", "occupancy_lidar_radar"]
    invalid = study_spec().model_dump()
    invalid["model_ids"] = ["occupancy_model_1"]
    with pytest.raises(ValueError):
        ReplayStudySpec.model_validate(invalid)


def test_pair_selection_cannot_choose_weak_radar_only_for_low_cost():
    from src.services.replay_comparison import compare

    def measured(ious, payload, reference="same"):
        return {"manifest": {"reference_sha256": reference,
            "sensor_cost": {"lidar_payload_bytes": payload, "radar_payload_bytes": payload / 10,
                            "camera_encoded_bytes": payload},
            "camera": {"mode": "image_fidelity_only", "mean_psnr_db": 40, "detection_retention": None}},
            "models": {name: {"metrics": {"occupied_iou": iou}} for name, iou in zip(study_spec().model_ids, ious, strict=True)}}

    study = {"id": "fixture", "spec": study_spec().model_dump(), "jobs": [
        {"id": "baseline", "environment": 0, "profile": "baseline", "status": "succeeded", "error": None,
         "result": measured([0.8, 0.2, 0.81], 1000)},
        {"id": "half", "environment": 0, "profile": "half", "status": "succeeded", "error": None,
         "result": measured([0.795, 0.201, 0.1], 500)}]}
    study["spec"]["min_occupied_iou"] = 0
    env = compare(study)["environments"][0]
    assert env["model_choices"]["occupancy_radar"]["profile"] == "half"
    assert env["provisional_selected"]["model"] == "occupancy_lidar"
    assert env["provisional_selected"]["profile"] == "half"
    study["jobs"][1]["result"]["manifest"]["reference_sha256"] = "changed-source"
    assert compare(study)["environments"][0]["provisional_selected"]["profile"] == "baseline"
    study["jobs"][0]["status"] = "failed"
    env = compare(study)["environments"][0]
    assert env["provisional_selected"] is None
    assert env["camera_choice"] is None
    study["jobs"][0]["status"] = "succeeded"
    study["spec"]["min_occupied_iou"] = 0.95
    assert compare(study)["environments"][0]["provisional_selected"] is None


def test_no_camera_detection_evidence_never_selects_detector_profile():
    from src.services.replay_comparison import compare

    measured = {"manifest": {"reference_sha256": "same", "sensor_cost": {"camera_encoded_bytes": 100},
        "camera": {"mode": "detector_consistency", "mean_psnr_db": 50, "detection_retention": None}}, "models": {}}
    study = {"id": "fixture", "spec": study_spec().model_dump(), "jobs": [
        {"id": "baseline", "environment": 0, "profile": "baseline", "status": "succeeded", "error": None,
         "result": measured}]}
    assert compare(study)["environments"][0]["camera_choice"] is None
