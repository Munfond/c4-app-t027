"""Measured occupancy-proxy research replay. Never a safety/detection benchmark."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import gymnasium as gym
import numpy as np

PROFILES = (1.0, 0.5, 0.25)
OBSERVATION_ABI = "occupancy-sensor-context-previous-latency-v1"


def lidar_features(points, intensity, keep=1.0, seed=27):
    from legacy.streamlit_lab.tools.local.nuscenes_local import NuScenesMini

    if keep not in PROFILES:
        raise ValueError("Unsupported point retention")
    if points.ndim != 2 or points.shape[1] != 3 or intensity.shape != (len(points),):
        raise ValueError("Invalid raw LiDAR arrays")
    if not np.isfinite(points).all() or not np.isfinite(intensity).all():
        raise ValueError("Nonfinite LiDAR input")
    if keep != 1:
        selected = np.random.default_rng(seed).permutation(len(points))[: max(1, int(len(points) * keep))]
        points, intensity = points[selected], intensity[selected]
    points, intensity = NuScenesMini.strip_body(points, intensity)
    obstacle = (points[:, 2] > 0.3) & (points[:, 2] < 3)
    r, c, valid = NuScenesMini.cells(points[obstacle, :2])
    count = np.zeros((200, 200))
    np.add.at(count, (r, c), 1)
    height = np.full((200, 200), -np.inf)
    np.maximum.at(height, (r, c), points[obstacle, 2][valid])
    ra, ca, all_valid = NuScenesMini.cells(points[:, :2])
    all_count = np.zeros((200, 200))
    total = np.zeros((200, 200))
    np.add.at(all_count, (ra, ca), 1)
    np.add.at(total, (ra, ca), intensity[all_valid])
    features = np.zeros((7, 200, 200), np.float32)
    features[0] = np.log1p(count) / 3
    features[1] = np.where(np.isfinite(height), (height + 1) / 5, 0)
    features[2] = np.log1p(all_count) / 3
    features[3] = total / np.maximum(all_count, 1) / 255
    return features


def quality(confusion):
    cm = np.asarray(confusion)
    if cm.shape != (3, 3) or not np.issubdtype(cm.dtype, np.integer) or (cm < 0).any() or cm.sum() != 40000:
        raise ValueError("Require full 200x200 proxy confusion counts")
    tp = int(cm[1:, 1:].sum())
    union = int(cm[1:, :].sum() + cm[:, 1:].sum() - tp)
    occupied = tp / union if union else None
    object_union = int(cm[2, :].sum() + cm[:, 2].sum() - cm[2, 2])
    object_iou = int(cm[2, 2]) / object_union if object_union else None
    supported = [v for v in (occupied, object_iou) if v is not None]
    return {
        "occupied_iou": occupied,
        "object_iou": object_iou,
        "score": float(np.mean(supported)) if supported else 0.0,
    }


def load_dataset(path: Path):
    path = Path(path)
    seal = json.loads(path.with_suffix(".seal.json").read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest() != seal["dataset_sha256"]:
        raise ValueError("Dataset changed after measurement")
    data = json.loads(path.read_text())
    if data.get("kind") != "measured_occupancy_proxy_replay" or data.get("observation_abi") != OBSERVATION_ABI:
        raise ValueError("Wrong task or observation ABI")
    if data.get("label_policy") != "lidar-persistence-static-proxy+annotated-object-footprints":
        raise ValueError("Unknown reference labels")
    if data.get("timing_scope") != "cpu_wall_point_preprocessing_and_inference":
        raise ValueError("Wrong measured latency scope")
    if data.get("status") != "completed" or data.get("profiles") != list(PROFILES):
        raise ValueError("Require complete measured matrix")
    scenes, tokens, split_counts = set(), set(), {}
    for episode in data["episodes"]:
        if (
            episode["scene"] in scenes
            or episode["split"] not in ("train", "validation", "test")
            or not episode["steps"]
        ):
            raise ValueError("Scene leakage or empty episode")
        scenes.add(episode["scene"])
        split_counts[episode["split"]] = split_counts.get(episode["split"], 0) + 1
        for step in episode["steps"]:
            if step["token"] in tokens:
                raise ValueError("Frame leakage")
            tokens.add(step["token"])
            obs = step["observation"]
            if len(obs) != 6 or any(
                type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in obs
            ):
                raise ValueError("Observation must contain only bounded sensor context")
            if len(step["outcomes"]) != 3:
                raise ValueError("Missing measured action")
            for result in step["outcomes"]:
                quality(result["confusion"])
                ms = result["latency_ms"]
                if type(ms) not in (int, float) or not math.isfinite(ms) or ms <= 0:
                    raise ValueError("Missing measured latency")
                file = (path.parent / result["artifact"]).resolve()
                if (
                    not file.is_relative_to(path.parent.resolve())
                    or hashlib.sha256(file.read_bytes()).hexdigest() != result["artifact_sha256"]
                ):
                    raise ValueError("Perception artifact changed")
                with np.load(file, allow_pickle=False) as artifact:
                    labels, prediction, inputs = artifact["labels"], artifact["prediction"], artifact["x"]
                    if labels.shape != (200, 200) or prediction.shape != labels.shape or inputs.shape != (4, 200, 200):
                        raise ValueError("Invalid saved perception shapes")
                    if (
                        not np.isin(labels, [0, 1, 2]).all()
                        or not np.isin(prediction, [0, 1, 2]).all()
                        or not np.isfinite(inputs).all()
                    ):
                        raise ValueError("Invalid perception values")
                    cm = np.bincount((labels.astype(int) * 3 + prediction).ravel(), minlength=9).reshape(3, 3)
                    if (
                        cm.tolist() != result["confusion"]
                        or hashlib.sha256(labels.tobytes()).hexdigest() != step["label_sha256"]
                    ):
                        raise ValueError("Outcome differs from saved proxy reference")
                    if hashlib.sha256(inputs.tobytes()).hexdigest() != result["input_sha256"]:
                        raise ValueError("Saved input differs from measured tensor")

    if set(split_counts) != {"train", "validation", "test"}:
        raise ValueError("Need separate train/validation/test scenes")
    return data


class OccupancyProxyEnv(gym.Env):
    """PPO observation never contains proxy labels or counterfactual outcomes."""

    def __init__(self, data, split="train"):
        self.episodes = [e for e in data["episodes"] if e["split"] == split]
        if not self.episodes:
            raise ValueError("Missing split")
        self.action_space = gym.spaces.Discrete(3)
        self.observation_space = gym.spaces.Box(0, 1, shape=(10,), dtype=np.float32)
        self.deadline_ms = float(data["deadline_ms"])
        if not math.isfinite(self.deadline_ms) or self.deadline_ms <= 0:
            raise ValueError("Invalid deadline")
        self.index = 0
        self.previous = 0
        self.previous_latency = 0.0

    def vector(self):
        observation = self.episode["steps"][self.index]["observation"]
        return np.asarray(
            observation
            + [min(self.previous_latency / self.deadline_ms, 1)]
            + [float(i == self.previous) for i in range(3)],
            dtype=np.float32,
        )

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        selected = options.get("episode", 0) if options else int(self.np_random.integers(len(self.episodes)))
        self.episode = self.episodes[selected]
        self.index = 0
        self.previous = 0
        self.previous_latency = 0.0
        return self.vector(), {"scene": self.episode["scene"]}

    def step(self, action):
        if not self.action_space.contains(action):
            raise ValueError("Invalid retention action")
        result = self.episode["steps"][self.index]["outcomes"][int(action)]
        scores = quality(result["confusion"])
        latency = result["latency_ms"]
        late = latency > self.deadline_ms
        switched = int(action) != self.previous
        reward = scores["score"] - 0.05 * (latency / self.deadline_ms) - 0.2 * float(late) - 0.01 * float(switched)
        self.previous = int(action)
        self.previous_latency = latency
        self.index += 1
        done = self.index == len(self.episode["steps"])
        vector = np.zeros(10, np.float32) if done else self.vector()
        return (
            vector,
            reward,
            done,
            False,
            {**scores, "latency_ms": latency, "late": late, "switched": switched, "retention": PROFILES[int(action)]},
        )
