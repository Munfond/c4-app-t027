"""Software fixtures verify synchrony/calibration/artifact contracts, not model quality."""
import json
from argparse import Namespace
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from scripts.collect_active_sensing import capture_request, collect, disk_reserve
from src.simulation.carla_rig import (
    CAMERAS,
    OPTICAL,
    SEMANTIC_DTYPE,
    RigRecorder,
    camera_intrinsic,
    radar_xyz,
    sha256_file,
    verify_episode,
)


def args_for(root, **kwargs):
    return Namespace(**dict({"output": root, "seconds": 0.1, "hz": 20, "map": "Town01",
                             "weather": "clear", "vehicles": 0, "pedestrians": 0, "seed": 42,
                             "spawn": 0, "route": "spawn", "width": 640, "height": 360,
                             "include_64": True, "traffic_placement": "nearest_spawn"}, **kwargs))


def test_optical_projection_center_left_and_above():
    # A point forward lies at principal point; CARLA left and up project left/up.
    points = np.array([[10, 0, 0, 1], [10, -2, 0, 1], [10, 0, 2, 1.]])
    optical = (points @ OPTICAL.T)[:, :3]
    uvw = optical @ camera_intrinsic(640, 360, 90).T
    uv = uvw[:, :2] / uvw[:, 2:3]
    np.testing.assert_allclose(uv[0], [320, 180])
    assert uv[1, 0] < 320 and uv[2, 1] < 180
    np.testing.assert_allclose(np.column_stack((optical, np.ones(3))) @ np.linalg.inv(OPTICAL).T, points)


def test_radar_coordinates_do_not_fabricate_vector_velocity():
    raw = np.array([[9, 0, 0, 10], [-3, np.pi / 2, 0, 10], [1, 0, np.pi / 2, 5]])
    np.testing.assert_allclose(radar_xyz(raw), [[10, 0, 0], [0, 10, 0], [0, 0, 5]], atol=1e-5)
    assert radar_xyz(np.zeros((0, 4))).shape == (0, 3)


def make_fixture(root, monkeypatch):
    import sys
    # No live CARLA dependency. Actor list is empty in this artifact contract fixture.
    monkeypatch.setitem(sys.modules, "carla", SimpleNamespace())
    root.mkdir()
    request = capture_request(args_for(root))
    recorder = RigRecorder(root, request["rig_options"], 0.05)
    matrix = np.eye(4)
    class Packet:
        frame = 101
        timestamp = 5.05
        transform = SimpleNamespace(get_matrix=lambda: matrix)
        width, height = 640, 360
        def __init__(self, payload):
            self.raw_data = payload
        def save_to_disk(self, path):
            Image.new("RGB", (self.width, self.height)).save(path)
    for frame_id in (101, 102):
        packets = {}
        for name in recorder.specs:
            if "CAM" in name:
                bgra = np.zeros((360, 640, 4), np.uint8)
                if name.startswith("GT_"):
                    bgra[:, :, 2] = 1
                payload = bgra.tobytes()
            elif name == "GT_LIDAR":
                semantic = np.zeros(1, SEMANTIC_DTYPE)
                semantic["x"] = 10
                semantic["tag"] = 3
                payload = semantic.tobytes()
            else:
                payload = np.array([[0, 0, 0, 10] if name.startswith("RADAR") else [10, 0, 0, 0.5]],
                                   dtype="<f4").tobytes()
            packet = Packet(payload)
            packet.frame = frame_id
            packet.timestamp = frame_id * 0.05
            packets[name] = packet
        snapshot = SimpleNamespace(frame=frame_id, timestamp=SimpleNamespace(elapsed_seconds=frame_id * 0.05))
        ego = SimpleNamespace(id=99, get_velocity=lambda: SimpleNamespace(x=1, y=0, z=0))
        recorder.record(packets, snapshot, matrix, [], ego)
    scenario = SimpleNamespace(frames=2, model_dump=lambda: request["scenario"])
    recorder.finish(scenario, {"source": "carla", "server_version": "fixture-not-real"})
    return recorder


def rewrite_metadata(root, edit):
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    artifact = manifest["frames"][0]["metadata"]
    path = root / artifact["path"]
    data = json.loads(path.read_text())
    edit(data)
    path.write_text(json.dumps(data))
    artifact.update(bytes=path.stat().st_size, sha256=sha256_file(path))
    manifest_path.write_text(json.dumps(manifest))


def test_full_rig_inventory_and_separate_gt_verify(tmp_path, monkeypatch):
    root = tmp_path / "capture"
    make_fixture(root, monkeypatch)
    report = verify_episode(root)
    assert report["frames"] == 2 and report["sensors"] == 20
    assert report["perception_ready"] is False
    assert set(CAMERAS) <= set(report["element_totals"])
    data = json.loads((root / "frame_00000.json").read_text())
    assert data["sensors"]["GT_CAM_FRONT"]["artifact"]["path"].startswith("ground_truth/")
    assert data["sensors"]["CAM_FRONT"]["artifact"]["path"].startswith("inputs/")
    tags = np.load(root / data["sensors"]["GT_CAM_FRONT"]["artifact"]["path"])
    assert np.all(tags == 1)


@pytest.mark.parametrize("mutation,match", [
    (lambda data: data["sensors"]["CAM_FRONT"].update(frame_id=999), "synchrony"),
    (lambda data: data["sensors"]["LIDAR_TOP"]["sensor_to_ego_lab"][0].__setitem__(3, 5), "Extrinsic"),
    (lambda data: data["sensors"]["GT_LIDAR"].update(ground_truth_only=False), "GT/input"),
])
def test_rejects_misaligned_or_leaked_capture(tmp_path, monkeypatch, mutation, match):
    root = tmp_path / "capture"
    make_fixture(root, monkeypatch)
    rewrite_metadata(root, mutation)
    with pytest.raises(ValueError, match=match):
        verify_episode(root)


def test_corrupted_measurement_is_rejected(tmp_path, monkeypatch):
    root = tmp_path / "capture"
    make_fixture(root, monkeypatch)
    (root / "inputs/frame_00000/LIDAR_TOP.npz").write_bytes(b"damaged")
    with pytest.raises(ValueError, match="checksum"):
        verify_episode(root)


def test_request_bounded_and_20hz_without_changing_api_cadence(tmp_path):
    from src.models.experiments import ScenarioSpec
    request = capture_request(args_for(tmp_path, seconds=60))
    assert request["scenario"]["frames"] == 1200
    assert request["scenario"]["capture_interval"] == 0.05
    assert ScenarioSpec().capture_interval == 0.5
    assert disk_reserve(request) > 1024 ** 3
    with pytest.raises(ValueError, match="seconds"):
        capture_request(args_for(tmp_path, seconds=121))


def test_existing_episode_not_overwritten(tmp_path):
    with pytest.raises(ValueError, match="already exists"):
        collect(args_for(tmp_path))


def test_sensor_reader_feeds_gate_and_keeps_ground_truth_out(tmp_path, monkeypatch):
    from src.active_sensing.core import default_profiles
    from src.active_sensing.episode_inputs import RawEpisode
    from src.active_sensing.gate import gate_capture
    root = tmp_path / "capture"
    make_fixture(root, monkeypatch)
    episode = RawEpisode(root)
    capture, observation = episode.inputs(0)
    assert observation.camera_health == "ok" and observation.radar_targets == 5
    assert "weather" not in vars(observation) and "ground_truth" not in capture
    profiles = {p.model: p for p in default_profiles() if p.model_hz == 10 and p.tasks == ("detection",)}
    lidar = gate_capture(capture, profiles["official_lidar"])
    assert set(lidar["streams"]) == {"lidar"}
    assert lidar["streams"]["lidar"]["intensity_policy"] == "CARLA_raw_0_to_1"
    crn = gate_capture(capture, profiles["crn"])
    assert set(crn["streams"]) == {"camera", "radar"}
    assert len(crn["streams"]["camera"]) == 6 and len(crn["streams"]["radar"]) == 5
    assert crn["streams"]["radar"]["front"]["vector_velocity_available"] is False
    assert crn["detector_adapter_validated"] is False
    assert all("ground_truth" not in str(r) for r in crn["streams"]["camera"].values())
