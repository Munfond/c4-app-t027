"""Bounded file IPC and physical sensor-bank selection; contains no Torch or GT actor inputs."""

import hashlib
import json
import time
from pathlib import Path

import numpy as np

from src.active_sensing.native_contract import BASELINE, PROFILES


def sensor_name(action):
    if type(action) is not int or not 0 <= action < 12:
        raise ValueError("Invalid physical LiDAR selector")
    return "lidar" if action == BASELINE else f"lidar_profile_{action}"


def sensor_bank(specs):
    result = dict(specs)
    for action, profile in enumerate(PROFILES):
        attrs = {**specs["lidar"][1], **{k: str(v) for k, v in profile.items()}}
        result[sensor_name(action)] = ("sensor.lidar.ray_cast", attrs)
    return result


class FileSensorGate:
    def __init__(self, root, timeout=30):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.current_action = BASELINE
        self.actual_attributes = {}

    def record_sensor(self, name, attrs):
        if name not in {sensor_name(a) for a in range(12)}:
            return
        action = BASELINE if name == "lidar" else int(name.rsplit("_", 1)[1])
        if any(float(attrs.get(key, "nan")) != value for key, value in PROFILES[action].items()):
            raise ValueError("Actual spawned sensor differs from physical profile")
        self.actual_attributes[name] = {
            k: attrs[k]
            for k in ("channels", "points_per_second", "range", "rotation_frequency", "upper_fov", "lower_fov")
        }

    def decide(self, points, intensity, index, frame_id, *, final=False):
        # Only the selected RAW signal crosses this boundary. No labels, validity masks,
        # actor poses, weather GT or unselected sensor streams enter the actor process.
        artifact = self.root / f"signal-{index:04d}.npz"
        np.savez_compressed(artifact, points=points, intensity=intensity)
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        request = {
            "index": index,
            "frame_id": frame_id,
            "current_action": self.current_action,
            "signal_sha256": digest,
            "final": final,
        }
        path = self.root / f"request-{index:04d}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(request))
        temporary.replace(path)
        response_path = self.root / f"response-{index:04d}.json"
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if response_path.is_file():
                response = json.loads(response_path.read_text())
                if any(response.get(k) != request[k] for k in ("index", "frame_id", "signal_sha256")):
                    raise ValueError("Stale/mismatched online decision response")
                if response.get("status") != "ok":
                    raise RuntimeError("Online policy process rejected sensor signal")
                action = response.get("next_action")
                sensor_name(action)
                self.current_action = action
                return action
            time.sleep(0.01)
        raise TimeoutError("Online policy response timed out; never reuse the previous response")
