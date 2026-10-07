"""Contracts, observation-only decisions and GT-only evaluation.

The shield enforces configuration constraints. It does not certify safety.
Only checkpoint-compatible full camera/radar rigs are enabled initially.
"""
from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, fields
from typing import Any

MODEL_INPUTS = {
    "official_lidar": frozenset({"lidar"}),
    "official_cl": frozenset({"camera", "lidar"}),
    "crn": frozenset({"camera", "radar"}),
    "fused": frozenset({"camera", "lidar", "radar"}),
}
MODEL_RANGES = {"official_lidar": 54.0, "official_cl": 54.0, "crn": 51.0, "fused": 51.0}
TASKS = frozenset({"detection", "camera_seg", "lidar_seg"})


def finite(value: float, name: str, minimum: float | None = None) -> float:
    value = float(value)
    if not math.isfinite(value) or (minimum is not None and value < minimum):
        raise ValueError(f"{name} must be finite and >= {minimum}")
    return value


@dataclass(frozen=True)
class Profile:
    id: str
    model: str
    model_hz: int
    cameras: int = 0
    lidar_channels: int = 0
    lidar_keep: float = 1.0
    lidar_sweeps: int = 1
    radars: int = 0
    tasks: tuple[str, ...] = ("detection",)

    def __post_init__(self):
        if not self.id or self.model not in MODEL_INPUTS:
            raise ValueError("Profile needs a known model and nonempty id")
        if self.model_hz not in (5, 10, 20):
            raise ValueError("model_hz must be 5, 10 or 20")
        if self.cameras not in (0, 6) or self.radars not in (0, 5):
            raise ValueError("Partial rigs require a separately validated checkpoint adapter")
        if self.lidar_channels not in (0, 32, 64):
            raise ValueError("Invalid LiDAR variant")
        if not 0 < finite(self.lidar_keep, "lidar_keep") <= 1:
            raise ValueError("lidar_keep must be in (0, 1]")
        if self.lidar_sweeps not in (1, 3, 9):
            raise ValueError("Invalid sweep count")
        if not self.tasks or not set(self.tasks) <= TASKS or len(set(self.tasks)) != len(self.tasks):
            raise ValueError("Invalid or duplicate tasks")
        if not MODEL_INPUTS[self.model] <= self.sensors:
            raise ValueError("Detector sensor requirements are not met")
        if "camera_seg" in self.tasks and not self.cameras:
            raise ValueError("Camera segmentation needs camera input")
        if "lidar_seg" in self.tasks and not self.lidar_channels:
            raise ValueError("LiDAR segmentation needs LiDAR input")
        if "detection" not in self.tasks:
            raise ValueError("Initial experiments require detection")

    @property
    def sensors(self) -> frozenset[str]:
        return frozenset(
            name for name, enabled in (
                ("camera", self.cameras), ("lidar", self.lidar_channels), ("radar", self.radars)
            ) if enabled
        )

    @property
    def declared_range_m(self) -> float:
        # Capacity declared by model configuration, NOT a validated detection guarantee.
        return MODEL_RANGES[self.model]


def default_profiles() -> tuple[Profile, ...]:
    profiles = []
    for model, sensors in MODEL_INPUTS.items():
        optional = tuple(
            task for sensor, task in (("camera", "camera_seg"), ("lidar", "lidar_seg"))
            if sensor in sensors
        )
        for hz in (5, 10, 20):
            for segmentation in (False, True):
                profiles.append(Profile(
                    id=f"{model}-{hz}hz" + ("-seg" if segmentation else ""),
                    model=model, model_hz=hz,
                    cameras=6 if "camera" in sensors else 0,
                    lidar_channels=32 if "lidar" in sensors else 0,
                    radars=5 if "radar" in sensors else 0,
                    tasks=("detection",) + (optional if segmentation else ()),
                ))
    return tuple(profiles)


@dataclass(frozen=True)
class Observation:
    timestamp_s: float
    speed_mps: float
    camera_brightness: float = 0.5
    camera_contrast: float = 0.5
    lidar_return_ratio: float = 1.0
    radar_targets: int = 0
    camera_health: str = "unknown"
    lidar_health: str = "unknown"
    radar_health: str = "unknown"
    nearest_detection_m: float | None = None
    min_ttc_s: float | None = None
    new_near_target: bool = False
    age_ms: float = 0.0
    valid: bool = True

    def __post_init__(self):
        for name in ("timestamp_s", "speed_mps", "age_ms"):
            finite(getattr(self, name), name, 0)
        for name in ("camera_brightness", "camera_contrast", "lidar_return_ratio"):
            if not 0 <= finite(getattr(self, name), name) <= 1:
                raise ValueError(f"{name} must be in [0,1]")
        if isinstance(self.radar_targets, bool) or not isinstance(self.radar_targets, int) or self.radar_targets < 0:
            raise ValueError("radar_targets must be a nonnegative integer")
        for name in ("nearest_detection_m", "min_ttc_s"):
            if getattr(self, name) is not None:
                finite(getattr(self, name), name, 0)
        if type(self.valid) is not bool or type(self.new_near_target) is not bool:
            raise ValueError("Observation flags must be bool")
        for sensor in ("camera", "lidar", "radar"):
            if getattr(self, f"{sensor}_health") not in ("ok", "degraded", "failed", "unknown"):
                raise ValueError("Unknown health value")

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> Observation:
        # Reject accidental GT/weather/other privileged fields at the actor boundary.
        allowed = {field.name for field in fields(cls)}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"Privileged or unknown actor fields: {sorted(unknown)}")
        return cls(**payload)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Constraints:
    required_tasks: tuple[str, ...] = ("detection",)
    max_observation_age_ms: float = 500.0
    miss_rate_limit: float = 0.01
    perception_deadline_ms: float = 150.0
    min_segmentation_iou: float = 0.5
    minimum_region_m: float = 5.0
    reaction_time_s: float = 0.5
    conservative_deceleration_mps2: float = 4.0
    quality_weight: float = 1.0
    gpu_weight: float = 0.5
    switch_weight: float = 0.05
    shield_weight: float = 0.05
    false_positive_weight: float = 0.05

    def __post_init__(self):
        if not self.required_tasks or not set(self.required_tasks) <= TASKS:
            raise ValueError("Invalid required tasks")
        for field in fields(self):
            if field.name != "required_tasks":
                finite(getattr(self, field.name), field.name, 0)
        if self.conservative_deceleration_mps2 <= 0 or self.perception_deadline_ms <= 0:
            raise ValueError("Deceleration and deadline must be positive")
        if not 0 <= self.min_segmentation_iou <= 1:
            raise ValueError("min_segmentation_iou must be in [0,1]")
        if not 0 <= self.miss_rate_limit <= 1:
            raise ValueError("miss_rate_limit must be in [0,1]")

    def stopping_region_m(self, speed_mps: float) -> float:
        # Experiment ROI only. Not a certified braking-distance calculation.
        speed = finite(speed_mps, "speed_mps", 0)
        return max(self.minimum_region_m, speed * self.reaction_time_s + speed * speed / (2 * self.conservative_deceleration_mps2))


@dataclass(frozen=True)
class Decision:
    requested: str
    executed: str | None
    intervened: bool
    reasons: tuple[str, ...]


def strongest(profiles: list[Profile]) -> Profile:
    return max(profiles, key=lambda p: (len(p.sensors), p.model_hz, len(p.tasks), p.id))


class Shield:
    def __init__(self, profiles: tuple[Profile, ...], constraints: Constraints):
        if not profiles or len({p.id for p in profiles}) != len(profiles):
            raise ValueError("Profiles must have unique ids")
        self.profiles = profiles
        self.constraints = constraints

    def eligible(self, observation: Observation) -> list[Profile]:
        # Unavailable/unknown sensors are NEVER re-enabled by fallback.
        failed = {
            s for s in ("camera", "lidar", "radar")
            if getattr(observation, f"{s}_health") in ("failed", "unknown")
        }
        floor_hz = 20 if observation.speed_mps >= 80 / 3.6 else (
            10 if observation.speed_mps >= 5 else 5
        )
        hazard = observation.new_near_target or (
            observation.min_ttc_s is not None and observation.min_ttc_s < 3
        ) or (
            observation.nearest_detection_m is not None
            and observation.nearest_detection_m < self.constraints.stopping_region_m(observation.speed_mps)
        )
        if hazard:
            floor_hz = 20
        return [
            p for p in self.profiles
            if not p.sensors & failed
            and set(self.constraints.required_tasks) <= set(p.tasks)
            and p.model_hz >= floor_hz
            and p.declared_range_m >= self.constraints.stopping_region_m(observation.speed_mps)
        ]

    def apply(self, requested_id: str, observation: Observation) -> Decision:
        if requested_id not in {p.id for p in self.profiles}:
            raise ValueError(f"Unknown profile: {requested_id}")
        candidates = self.eligible(observation)
        if not candidates:
            return Decision(requested_id, None, True, ("no_feasible_profile",))
        stale = not observation.valid or observation.age_ms > self.constraints.max_observation_age_ms
        if stale:
            fallback = strongest(candidates)
            return Decision(requested_id, fallback.id, True, ("missing_or_stale_observation",))
        if requested_id not in {p.id for p in candidates}:
            fallback = strongest(candidates)
            return Decision(requested_id, fallback.id, True, ("profile_constraints",))
        return Decision(requested_id, requested_id, False, ())

    def mask(self, observation: Observation) -> list[bool]:
        ids = {p.id for p in self.eligible(observation)}
        if ids and (not observation.valid or observation.age_ms > self.constraints.max_observation_age_ms):
            ids = {strongest(self.eligible(observation)).id}
        return [p.id in ids for p in self.profiles]


class RulePolicy:
    """Conservative baseline using observable health/quality, never GT labels."""
    def __init__(self, shield: Shield):
        self.shield = shield

    def select(self, observation: Observation) -> str:
        candidates = self.shield.eligible(observation)
        if not candidates:
            return self.shield.profiles[0].id  # shield records infeasibility
        camera_degraded = observation.camera_contrast < 0.2 or observation.camera_brightness < 0.1
        lidar_degraded = observation.lidar_health == "degraded" or observation.lidar_return_ratio < 0.4
        preferred = "crn" if lidar_degraded else ("official_lidar" if camera_degraded else "official_cl")
        branch = [p for p in candidates if p.model == preferred]
        return min(branch or candidates, key=lambda p: (p.model_hz, len(p.tasks), len(p.sensors), p.id)).id


@dataclass(frozen=True)
class Box:
    id: str
    label: str
    x: float
    y: float
    score: float = 1.0

    def __post_init__(self):
        if not self.id or not self.label:
            raise ValueError("Box requires id and label")
        finite(self.x, "x")
        finite(self.y, "y")
        if not 0 <= finite(self.score, "score") <= 1:
            raise ValueError("score must be in [0,1]")


def evaluate(
    ground_truth: list[Box], predictions: list[Box], observation: Observation,
    constraints: Constraints, gpu_ms: float, reference_gpu_ms: float,
    end_to_end_ms: float, switched: bool, intervened: bool,
) -> dict[str, Any]:
    """GT is consumed only here. Matching is one-to-one with a 2m class-aware gate."""
    gpu_ms = finite(gpu_ms, "gpu_ms", 0)
    reference_gpu_ms = finite(reference_gpu_ms, "reference_gpu_ms", 0)
    end_to_end_ms = finite(end_to_end_ms, "end_to_end_ms", 0)
    if reference_gpu_ms <= 0:
        raise ValueError("Reference GPU work must be positive")
    if len({b.id for b in ground_truth}) != len(ground_truth):
        raise ValueError("Duplicate GT ids")
    if len({b.id for b in predictions}) != len(predictions):
        raise ValueError("Duplicate prediction ids")
    radius = constraints.stopping_region_m(observation.speed_mps)
    truth = [b for b in ground_truth if math.hypot(b.x, b.y) <= radius]
    pred = [b for b in predictions if b.score >= 0.3 and math.hypot(b.x, b.y) <= radius + 2]
    edges = sorted(
        (math.hypot(g.x - p.x, g.y - p.y), i, j)
        for i, g in enumerate(truth) for j, p in enumerate(pred)
        if g.label == p.label and math.hypot(g.x - p.x, g.y - p.y) <= 2
    )
    matched_gt, matched_pred = set(), set()
    for _, i, j in edges:
        if i not in matched_gt and j not in matched_pred:
            matched_gt.add(i)
            matched_pred.add(j)
    weights = {"pedestrian": 3, "bicycle": 3, "motorcycle": 2}
    total = sum(weights.get(g.label, 1) for g in truth)
    found = sum(weights.get(truth[i].label, 1) for i in matched_gt)
    recall = found / total if total else None
    late = end_to_end_ms > constraints.perception_deadline_ms
    effective_recall = (recall or 0.0) if not late else 0.0
    false_positives = len(pred) - len(matched_pred)
    cost = float(bool(truth) and (len(matched_gt) < len(truth) or late))
    # Ratio may exceed 1; never clamp away work above the measured reference.
    ratio = gpu_ms / reference_gpu_ms
    base_reward = (
        constraints.quality_weight * effective_recall - constraints.gpu_weight * ratio
        - constraints.switch_weight * int(switched) - constraints.shield_weight * int(intervened)
        - constraints.false_positive_weight * false_positives
    )
    return {
        "weighted_recall": recall, "effective_recall": effective_recall,
        "required_targets": len(truth), "matched_targets": len(matched_gt),
        "false_positives": false_positives, "constraint_cost": cost,
        "late": late, "gpu_ms": gpu_ms, "gpu_ratio": ratio,
        "base_reward": base_reward,
    }


def gate_points(points: list[tuple[float, ...]], keep: float, seed: int) -> list[tuple[float, ...]]:
    """Deterministic sampling. It does NOT simulate weather or implement sweep compensation."""
    if not 0 < finite(keep, "keep") <= 1:
        raise ValueError("keep must be in (0,1]")
    for point in points:
        if len(point) < 3:
            raise ValueError("Points require XYZ")
        for value in point:
            finite(value, "point")
    count = max(1, math.ceil(len(points) * keep)) if points else 0
    indices = sorted(random.Random(seed).sample(range(len(points)), count))
    return [points[i] for i in indices]


def carla_xyz_to_ego(point: tuple[float, float, float]) -> tuple[float, float, float]:
    """CARLA sensor-local XYZ -> matching local convention; full rig extrinsics remain required."""
    x, y, z = (finite(v, "coordinate") for v in point)
    return x, -y, z
