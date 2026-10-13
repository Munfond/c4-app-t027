"""Validated, bounded experiment commands. No caller-supplied paths or code."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.replay import ReplayTrialSpec


class EngineerReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer: str = Field(min_length=1, max_length=80)
    verdict: Literal["accept", "reject", "needs_evidence"]
    notes: str = Field(min_length=10, max_length=2000)


class LidarSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channels: int = Field(default=32, ge=8, le=64)
    points_per_second: int = Field(default=600000, ge=20000, le=600000)
    range_m: float = Field(default=100, ge=10, le=100)
    upper_fov: float = Field(default=10, ge=-10, le=30)
    lower_fov: float = Field(default=-30, ge=-45, le=0)
    mount_z: float = Field(default=2, ge=0.5, le=3)
    pitch: float = Field(default=0, ge=-15, le=15)

    @model_validator(mode="after")
    def valid_fov(self):
        if self.lower_fov >= self.upper_fov:
            raise ValueError("lower_fov must be smaller than upper_fov")
        return self


class CameraSpec(BaseModel):
    """Bounded capture presets; FOV is not a detector quality recommendation."""

    model_config = ConfigDict(extra="forbid")
    fov: Literal[60, 90, 110] = 90


class ScenarioSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    map: Literal["Town01", "Town02", "Town03", "Town04", "Town05"] = "Town01"
    weather: Literal["clear", "rain", "fog"] = "clear"
    vehicles: int = Field(default=2, ge=0, le=40)
    pedestrians: int = Field(default=0, ge=0, le=40)
    seed: int = Field(default=42, ge=0, le=2147483647)
    frames: int = Field(default=4, ge=1, le=81)
    # Model temporal training cadence is 0.5 seconds, not the simulator tick rate.
    capture_interval: Literal[0.5] = 0.5
    timestep: Literal[0.05] = 0.05
    traffic_placement: Literal["random_spawn", "nearest_spawn"] = "random_spawn"
    route_spawn_index: int = Field(default=0, ge=0, le=1000)
    route_kind: Literal["spawn", "highway"] = "spawn"
    lane_change_interval_seconds: float | None = Field(default=None, ge=2, le=15)
    lidar: LidarSpec = Field(default_factory=LidarSpec)
    camera: CameraSpec = Field(default_factory=CameraSpec)

    @model_validator(mode="after")
    def supported_route(self):
        if self.route_kind == "highway" and self.traffic_placement != "random_spawn":
            raise ValueError("Highway route uses its own verified traffic placement")
        if self.route_kind == "highway" and self.map != "Town04":
            raise ValueError("Verified highway capture currently requires Town04")
        return self


class ExperimentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["carla", "nuscenes", "dataset_replay"] = "carla"
    replay: ReplayTrialSpec | None = None
    model_ids: list[str] = Field(default_factory=lambda: ["occupancy_lidar"], min_length=1, max_length=7)
    native_input_adapter: Literal["raw", "intensity_mean_experimental"] = "raw"
    scenario: ScenarioSpec = Field(default_factory=ScenarioSpec)
    scene_id: str | None = Field(default=None, max_length=64, pattern=r"^scene-\d{4}$")
    capture_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    max_latency_ms: float | None = Field(default=None, gt=0, le=60000)

    @model_validator(mode="after")
    def unique_models(self):
        if self.native_input_adapter != "raw" and self.source != "carla":
            raise ValueError("Native adapter cannot change stored nuScenes/dataset replay inputs")
        if len(set(self.model_ids)) != len(self.model_ids):
            raise ValueError("Duplicate model IDs")
        if self.source == "nuscenes" and self.scene_id is None:
            raise ValueError("scene_id is required for nuScenes")
        if self.source == "nuscenes" and self.capture_id is not None:
            raise ValueError("capture_id is only supported for CARLA replay")
        if self.source == "dataset_replay" and (self.replay is None or self.capture_id is not None):
            raise ValueError("dataset_replay requires replay spec and forbids capture_id")
        if self.source != "dataset_replay" and self.replay is not None:
            raise ValueError("replay spec is only supported for dataset_replay")
        return self


class AgentPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)


class SensorAgentRequest(AgentPlanRequest):
    max_iou_drop: float | None = Field(default=None, ge=0, le=0.2)
    frames: int | None = Field(default=None, ge=2, le=20)


class SensorProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(
        min_length=1,
        max_length=40,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Candidate profile name. Never use baseline; baseline runs automatically.",
    )
    lidar: LidarSpec


class SensorStudySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenarios: list[ScenarioSpec] = Field(min_length=1, max_length=3)
    profiles: list[SensorProfile] = Field(min_length=1, max_length=3)
    native_input_adapter: Literal["raw", "intensity_mean_experimental"] = "raw"
    max_iou_drop: float = Field(default=0.02, ge=0, le=0.2)
    min_occupied_iou: float = Field(default=0.3, ge=0, le=1)
    min_object_iou: float | None = Field(default=None, ge=0, le=1)
    min_object_recall: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def bounded_study(self):
        if len({profile.name for profile in self.profiles}) != len(self.profiles):
            raise ValueError("Profile names must be unique")
        if any(profile.name == "baseline" for profile in self.profiles):
            raise ValueError("baseline is reserved")
        if any(
            scenario.frames > 20 or scenario.vehicles > 15 or scenario.pedestrians > 15 for scenario in self.scenarios
        ):
            raise ValueError("Sensor study is limited to 20 frames, 15 vehicles and 15 pedestrians per scene")
        return self
