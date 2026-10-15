"""Run a frozen occupancy policy on current measured LiDAR; no reference labels accepted."""

import hashlib
import time
from pathlib import Path

import numpy as np

from src.active_sensing.native_contract import ABI, BASELINE, PROFILES, sensor_context
from src.inference.bev import lidar_features


class NativeOnlineController:
    def __init__(self, perception, choose, adapter, *, mode="ppo"):
        self.perception, self.choose, self.adapter = perception, choose, adapter
        self.mode = mode
        self.current = BASELINE
        self.next_index = 0
        self.trace = []
        # Warm model shape outside frame timing, and disclose warmup instead of hiding it.
        start = time.perf_counter()
        perception.predict([{"x": np.zeros((7, 200, 200), np.float32)}], 0)
        self.warmup_ms = (time.perf_counter() - start) * 1000

    def process(self, request, root):
        index = request["index"]
        if (
            type(index) is not int
            or index != self.next_index
            or type(request["current_action"]) is not int
            or request["current_action"] != self.current
        ):
            raise ValueError("Out-of-order decision/current profile mismatch")
        if type(request.get("frame_id")) is not int or type(request.get("final")) is not bool:
            raise ValueError("Invalid live frame identity")
        artifact = Path(root) / f"signal-{index:04d}.npz"
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != request["signal_sha256"]:
            raise ValueError("Selected sensor signal changed")
        with np.load(artifact, allow_pickle=False) as signal:
            if set(signal.files) != {"points", "intensity"}:
                raise ValueError("Actor input must contain raw selected signal only")
            points, intensity = signal["points"], signal["intensity"]
        start = time.perf_counter()
        x = lidar_features(points, intensity)
        x[3] *= self.adapter["gain"]
        prediction = self.perception.predict([{"x": x}], 0)["occupancy"]
        perception_ms = (time.perf_counter() - start) * 1000
        timing = getattr(self.perception, "timing", None)
        model_ms = timing[-1] if timing else None
        observation = np.asarray(
            sensor_context(points, intensity)
            + [min(perception_ms / 500, 1)]
            + [float(a == self.current) for a in range(12)],
            np.float32,
        )
        next_action, policy_ms = self.current, None
        if not request["final"]:
            start = time.perf_counter()
            next_action = self.choose(observation, index)
            policy_ms = (time.perf_counter() - start) * 1000
            if type(next_action) is not int or not 0 <= next_action < 12:
                raise ValueError("Policy produced an unsupported physical profile")
        name = Path(root).parent / "online-predictions" / f"{index:04d}.npz"
        name.parent.mkdir(exist_ok=True)
        np.savez_compressed(name, prediction=prediction, x=x[:4])
        row = {
            "index": index,
            "frame_id": request["frame_id"],
            "current_action": self.current,
            "current_profile": PROFILES[self.current],
            "next_action": next_action,
            "applies_to_capture_index": None if request["final"] else index + 1,
            "observation_abi": ABI,
            "observation": observation.tolist(),
            "signal_sha256": request["signal_sha256"],
            "cpu_feature_model_ms": perception_ms,
            "cpu_model_only_ms": model_ms,
            "cpu_policy_ms": policy_ms,
            "mode": self.mode,
            "prediction_sha256": hashlib.sha256(name.read_bytes()).hexdigest(),
        }
        self.trace.append(row)
        self.current, self.next_index = next_action, index + 1
        return {
            "status": "ok",
            "index": index,
            "frame_id": request["frame_id"],
            "signal_sha256": request["signal_sha256"],
            "next_action": next_action,
        }
