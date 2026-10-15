import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from src.active_sensing.native_online import NativeOnlineController
from src.simulation.online_sensor_gate import FileSensorGate, sensor_bank, sensor_name


class FixturePerception:
    def predict(self, frames, index):
        return {"occupancy": np.zeros((200, 200), np.uint8)}


def request(root, index=0, current=7, final=False, forbidden=False):
    artifact = root / f"signal-{index:04d}.npz"
    fields = {"points": np.array([[5.0, 0, 1.0], [10.0, 1, 0.6]]), "intensity": np.array([40.0, 60.0], np.float32)}
    if forbidden:
        fields["labels"] = np.ones((200, 200), np.uint8)
    np.savez_compressed(artifact, **fields)
    return {
        "index": index,
        "frame_id": 100 + index,
        "current_action": current,
        "final": final,
        "signal_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
    }


def test_only_selected_raw_signal_is_seen_and_action_targets_next_capture(tmp_path):
    root = tmp_path / "ipc"
    root.mkdir()
    seen = []

    def choose(obs, index):
        seen.append(obs.copy())
        return 0

    controller = NativeOnlineController(FixturePerception(), choose, {"gain": 0.1})
    first = controller.process(request(root), root)
    assert seen[0].shape == (19,) and seen[0][7 + 7] == 1
    assert first["next_action"] == 0 and controller.trace[0]["applies_to_capture_index"] == 1
    controller.process(request(root, index=1, current=0, final=True), root)
    assert len(seen) == 1 and controller.trace[1]["applies_to_capture_index"] is None
    assert controller.trace[1]["current_action"] == 0


def test_gt_tensor_and_stale_request_are_rejected(tmp_path):
    root = tmp_path / "ipc"
    root.mkdir()
    controller = NativeOnlineController(FixturePerception(), lambda obs, index: 7, {"gain": 0.1})
    with pytest.raises(ValueError, match="raw selected signal only"):
        controller.process(request(root, forbidden=True), root)
    signal = request(root)
    signal["index"] = 1
    with pytest.raises(ValueError, match="Out-of-order"):
        controller.process(signal, root)


def test_sensor_bank_uses_actual_channels_rates_not_post_thinning(tmp_path):
    specs = {
        "lidar": (
            "sensor.lidar.ray_cast",
            {
                "channels": "32",
                "points_per_second": "600000",
                "range": "100",
                "rotation_frequency": "20",
                "upper_fov": "10",
                "lower_fov": "-30",
            },
        ),
        "camera": ("sensor.camera.rgb", {}),
    }
    bank = sensor_bank(specs)
    assert len(bank) == 13 and bank[sensor_name(0)][1]["channels"] == "16"
    assert bank[sensor_name(11)][1]["points_per_second"] == "600000"
    assert specs["lidar"][1]["channels"] == "32"
    gate = FileSensorGate(tmp_path)
    gate.record_sensor(sensor_name(0), bank[sensor_name(0)][1])
    with pytest.raises(ValueError, match="differs"):
        gate.record_sensor(sensor_name(11), bank[sensor_name(0)][1])


def test_file_gate_refuses_stale_response_and_does_not_reuse_action(tmp_path):
    gate = FileSensorGate(tmp_path, timeout=0.5)
    (tmp_path / "response-0000.json").write_text(
        json.dumps({"status": "ok", "index": 9, "frame_id": 100, "signal_sha256": "x", "next_action": 0})
    )
    with pytest.raises(ValueError, match="Stale"):
        gate.decide(np.array([[5.0, 0, 1]]), np.array([40.0], np.float32), 0, 100)
    assert gate.current_action == 7


def test_valid_response_advances_gate_only_after_matching_frame_and_signal(tmp_path):
    gate = FileSensorGate(tmp_path, timeout=2)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(gate.decide, np.array([[5.0, 0, 1]]), np.array([40.0], np.float32), 0, 100)
        import time

        path = tmp_path / "request-0000.json"
        for _ in range(100):
            if path.exists():
                break
            time.sleep(0.01)
        req = json.loads(path.read_text())
        (tmp_path / "response-0000.json").write_text(json.dumps({**req, "status": "ok", "next_action": 11}))
        assert future.result(timeout=2) == 11 and gate.current_action == 11
