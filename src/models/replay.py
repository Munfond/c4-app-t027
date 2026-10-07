"""Recorded-data experiments: reductions/corruptions, never new hardware simulation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CAMERAS = ["CAM_FRONT", "CAM_FRONT_LEFT", "CAM_FRONT_RIGHT", "CAM_BACK", "CAM_BACK_LEFT", "CAM_BACK_RIGHT"]
RADARS = ["RADAR_FRONT", "RADAR_FRONT_LEFT", "RADAR_FRONT_RIGHT", "RADAR_BACK_LEFT", "RADAR_BACK_RIGHT"]
OCCUPANCY_MODELS = ["occupancy_lidar", "occupancy_radar", "occupancy_lidar_radar"]


class PointReduction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keep_fraction: float = Field(default=1, gt=0, le=1)
    range_m: float = Field(default=100, ge=5, le=100)
    horizontal_fov: float = Field(default=360, ge=10, le=360)
    noise_std_m: float = Field(default=0, ge=0, le=0.5)


class CameraReduction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scale: float = Field(default=1, ge=0.25, le=1)
    jpeg_quality: int = Field(default=95, ge=20, le=95)
    blur_radius: float = Field(default=0, ge=0, le=4)


class ReplayProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    lidar: PointReduction = Field(default_factory=PointReduction)
    radar: PointReduction = Field(default_factory=PointReduction)
    camera: CameraReduction = Field(default_factory=CameraReduction)


class ReplayScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_id: str = Field(pattern=r"^scene-\d{4}$")
    frames: int = Field(default=4, ge=1, le=20)
    seed: int = Field(default=42, ge=0, le=2147483647)
    weather: Literal["original", "rain", "fog"] = "original"
    weather_strength: float = Field(default=0.3, ge=0, le=0.8)
    traffic: Literal["all", "sparse", "crowded"] = "all"


class ReplayTrialSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: ReplayScenario
    profile: ReplayProfile
    cameras: list[str] = Field(default_factory=lambda: ["CAM_FRONT"], min_length=1, max_length=6)
    radars: list[str] = Field(default_factory=lambda: list(RADARS), min_length=1, max_length=5)

    @model_validator(mode="after")
    def sensors(self):
        if len(set(self.cameras)) != len(self.cameras) or not set(self.cameras) <= set(CAMERAS):
            raise ValueError("Unknown or duplicate camera channels")
        if len(set(self.radars)) != len(self.radars) or not set(self.radars) <= set(RADARS):
            raise ValueError("Unknown or duplicate radar channels")
        return self


class ReplayStudySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["dataset_replay"] = "dataset_replay"
    scenarios: list[ReplayScenario] = Field(min_length=1, max_length=3)
    profiles: list[ReplayProfile] = Field(
        min_length=1, max_length=3,
        description="Candidate profiles only, with unique names. Do not include baseline: it is added automatically.",
    )
    model_ids: list[Literal["occupancy_lidar", "occupancy_radar", "occupancy_lidar_radar"]] = Field(
        default_factory=lambda: list(OCCUPANCY_MODELS), min_length=1, max_length=3,
    )
    cameras: list[str] = Field(default_factory=lambda: ["CAM_FRONT"], min_length=1, max_length=6)
    radars: list[str] = Field(default_factory=lambda: list(RADARS), min_length=1, max_length=5)
    max_iou_drop: float = Field(default=0.02, ge=0, le=0.2)
    min_occupied_iou: float = Field(default=0.3, ge=0, le=1)
    min_camera_psnr_db: float = Field(default=25, ge=10, le=60)
    min_detection_retention: float = Field(default=0.9, ge=0, le=1)

    @model_validator(mode="after")
    def bounded(self):
        names = [p.name for p in self.profiles]
        if len(set(names)) != len(names) or "baseline" in names:
            raise ValueError("Profile names must be unique; baseline is reserved")
        if len(set(self.model_ids)) != len(self.model_ids) or not set(self.model_ids) <= set(OCCUPANCY_MODELS):
            raise ValueError("Replay supports the three verified occupancy models only")
        ReplayTrialSpec(scenario=self.scenarios[0], profile=self.profiles[0], cameras=self.cameras, radars=self.radars)
        return self
