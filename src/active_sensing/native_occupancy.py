"""Causal twelve-profile replay on observed CARLA reference cells; research only."""

import hashlib
import json
import math
from pathlib import Path

import gymnasium as gym
import numpy as np

ABI = "native-current-profile-next-frame-v1"
PROFILES = [{"channels": c, "points_per_second": r} for c in (16, 32, 64) for r in (150000, 300000, 450000, 600000)]
BASELINE = 7
REWARD = {"latency_weight": 0.05, "late_penalty": 0.2, "switch_penalty": 0.01}


def sensor_context(points, intensity):
    points, intensity = np.asarray(points), np.asarray(intensity)
    if points.ndim != 2 or points.shape[1] != 3 or intensity.shape != (len(points),):
        raise ValueError("Invalid raw sensor context")
    if not len(points) or not np.isfinite(points).all() or not np.isfinite(intensity).all():
        raise ValueError("Missing or nonfinite raw sensor context")
    if (intensity < 0).any() or (intensity > 255).any() or (np.abs(points) > 2000).any():
        raise ValueError("Raw sensor values outside recorded domain")
    radius = np.linalg.norm(points[:, :2], axis=1)
    near = (points[:, 0] > 3.7) & (points[:, 0] < 20) & (np.abs(points[:, 1]) < 5)
    obstacle = (points[:, 2] > 0.3) & (points[:, 2] < 3)
    return [
        min(float(np.log1p(len(points)) / np.log1p(100000)), 1),
        float((near & obstacle).mean()),
        min(float(radius.mean() / 100), 1),
        min(float(radius.std() / 50), 1),
        float(obstacle.mean()),
        float(np.clip(intensity.mean() / 255, 0, 1)),
    ]


def quality(confusion, *, max_cells=40000):
    cm = np.asarray(confusion)
    if cm.shape != (3, 3) or not np.issubdtype(cm.dtype, np.integer) or (cm < 0).any() or not 0 < cm.sum() <= max_cells:
        raise ValueError("Require observed-cell 200x200 confusion")
    tp = int(cm[1:, 1:].sum())
    occupied_union = int(cm[1:, :].sum() + cm[:, 1:].sum() - tp)
    object_union = int(cm[2].sum() + cm[:, 2].sum() - cm[2, 2])
    occupied = tp / occupied_union if occupied_union else None
    objects = int(cm[2, 2]) / object_union if object_union else None
    values = [v for v in (occupied, objects) if v is not None]
    return {"occupied_iou": occupied, "object_iou": objects, "score": float(np.mean(values)) if values else 0.0}


def read_sealed(path):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != path.with_suffix(".sha256").read_text().strip():
        raise ValueError("Changed sealed research evidence")
    return json.loads(path.read_text()), digest


def load_dataset(path):
    path = Path(path)
    data, _ = read_sealed(path)
    if (
        data.get("kind") != "native_occupancy_measured_replay_v1"
        or data.get("status") != "measured"
        or data.get("observation_abi") != ABI
        or data.get("profiles") != PROFILES
        or data.get("baseline_action") != BASELINE
        or data.get("reward") != REWARD
        or data.get("deadline_ms") != 500
        or data.get("timing_scope") != "cpu_wall_feature_preprocessing_and_inference"
        or data.get("deployment_ready") is not False
    ):
        raise ValueError("Wrong native research replay protocol")
    from src.inference.bev import lidar_features

    splits, contexts, poses = {}, set(), {}
    for episode in data["episodes"]:
        split = episode["split"]
        context = (episode["route"], episode["seed"])
        if context in contexts or split not in ("train", "validation", "test") or len(episode["steps"]) != 20:
            raise ValueError("Duplicated context or incomplete episode")
        contexts.add(context)
        splits[split] = splits.get(split, 0) + 1
        object_support = 0
        for index, step in enumerate(episode["steps"]):
            if step["frame"] != index or len(step["outcomes"]) != 12:
                raise ValueError("Incomplete action matrix")
            reference = None
            for outcome in step["outcomes"]:
                quality(outcome["confusion"])
                latency = outcome["latency_ms"]
                if type(latency) not in (int, float) or not math.isfinite(latency) or latency <= 0:
                    raise ValueError("Missing measured CPU latency")
                file = (path.parent / outcome["artifact"]).resolve()
                if (
                    not file.is_relative_to(path.parent.resolve())
                    or hashlib.sha256(file.read_bytes()).hexdigest() != outcome["artifact_sha256"]
                ):
                    raise ValueError("Changed perception artifact")
                with np.load(file, allow_pickle=False) as item:
                    x, labels, valid, pred = (item[k] for k in ("x", "labels", "valid", "prediction"))
                    if (
                        x.shape != (4, 200, 200)
                        or labels.shape != (200, 200)
                        or valid.shape != labels.shape
                        or valid.dtype != np.bool_
                        or pred.shape != labels.shape
                        or not valid.any()
                        or not np.isfinite(x).all()
                        or not np.isin(labels, [0, 1, 2]).all()
                        or not np.isin(pred, [0, 1, 2]).all()
                    ):
                        raise ValueError("Invalid observed perception arrays")
                    features = lidar_features(item["points"], item["intensity"])[:4]
                    features[3] *= data["adapter"]["gain"]
                    if not np.array_equal(x, features):
                        raise ValueError("Raw points do not reproduce adapted features")
                    obs = sensor_context(item["points"], item["intensity"])
                    if obs != outcome["observation"]:
                        raise ValueError("Actor context is not raw sensor-derived")
                    cm = np.bincount((labels[valid].astype(int) * 3 + pred[valid]).ravel(), minlength=9).reshape(3, 3)
                    ref = hashlib.sha256(
                        labels.tobytes() + valid.tobytes() + item["rotation"].tobytes() + item["translation"].tobytes()
                    ).hexdigest()
                    if (
                        cm.tolist() != outcome["confusion"]
                        or ref != step["reference_sha256"]
                        or (reference and ref != reference)
                    ):
                        raise ValueError("Unpaired native references or incorrect confusion")
                    reference = ref
                    if hashlib.sha256(x.tobytes()).hexdigest() != outcome["input_sha256"]:
                        raise ValueError("Input seal mismatch")
                    pose = tuple(np.round(np.r_[item["rotation"].ravel(), item["translation"].ravel()], 4))
                    if pose in poses and poses[pose] != split:
                        raise ValueError("Cross-split ego pose overlap")
                    poses[pose] = split
            object_support += int(np.asarray(step["outcomes"][0]["confusion"])[2].sum()) if index else 0
        if object_support <= 0:
            raise ValueError("No observed object reference in scored episode")
    if splits != {"train": 2, "validation": 1, "test": 1}:
        raise ValueError("Need preregistered disjoint 2/1/1 route splits")
    return data


class NativeOccupancyEnv(gym.Env):
    """Observe frame t under current profile, choose profile for t+1; bootstrap is not free."""

    def __init__(self, data, split="train"):
        self.episodes = [e for e in data["episodes"] if e["split"] == split]
        if not self.episodes:
            raise ValueError("Missing native replay split")
        self.action_space = gym.spaces.Discrete(12)
        self.observation_space = gym.spaces.Box(0, 1, shape=(19,), dtype=np.float32)
        self.deadline_ms = 500
        self.done = True

    def vector(self):
        current = self.episode["steps"][self.index]["outcomes"][self.previous]
        return np.asarray(
            current["observation"]
            + [min(self.previous_latency / self.deadline_ms, 1)]
            + [float(i == self.previous) for i in range(12)],
            dtype=np.float32,
        )

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        selected = options.get("episode", 0) if options else int(self.np_random.integers(len(self.episodes)))
        self.episode = self.episodes[selected]
        self.index, self.previous, self.done = 0, BASELINE, False
        self.previous_latency = self.episode["steps"][0]["outcomes"][BASELINE]["latency_ms"]
        return self.vector(), {"bootstrap_latency_ms": self.previous_latency, "bootstrap_action": BASELINE}

    def step(self, action):
        if self.done or not self.action_space.contains(action):
            raise ValueError("Reset completed episode or choose a valid action")
        action = int(action)
        self.index += 1
        result = self.episode["steps"][self.index]["outcomes"][action]
        scores = quality(result["confusion"])
        latency = result["latency_ms"]
        switched, late = action != self.previous, latency > self.deadline_ms
        reward = (
            scores["score"]
            - REWARD["latency_weight"] * latency / self.deadline_ms
            - REWARD["late_penalty"] * late
            - REWARD["switch_penalty"] * switched
        )
        self.previous, self.previous_latency = action, latency
        self.done = self.index == len(self.episode["steps"]) - 1
        return (
            np.zeros(19, np.float32) if self.done else self.vector(),
            reward,
            self.done,
            False,
            {
                **scores,
                "frame": self.index,
                "latency_ms": latency,
                "switched": switched,
                "late": late,
                "profile": PROFILES[action],
                "confusion": result["confusion"],
            },
        )
