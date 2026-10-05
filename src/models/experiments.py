"""Validated, bounded experiment commands. No caller-supplied paths or code."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScenarioSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    map: Literal["Town01", "Town02", "Town03", "Town04", "Town05"] = "Town03"
    weather: Literal["clear", "rain", "fog"] = "clear"
    vehicles: int = Field(default=8, ge=0, le=40)
    pedestrians: int = Field(default=8, ge=0, le=40)
    seed: int = Field(default=42, ge=0, le=2147483647)
    frames: int = Field(default=4, ge=1, le=81)
    # Model temporal training cadence is 0.5 seconds, not the simulator tick rate.
    capture_interval: Literal[0.5] = 0.5
    timestep: Literal[0.05] = 0.05
    route_spawn_index: int = Field(default=0, ge=0, le=1000)


class ExperimentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["carla", "nuscenes"] = "carla"
    model_ids: list[str] = Field(default_factory=lambda: ["occupancy_lidar"], min_length=1, max_length=7)
    scenario: ScenarioSpec = Field(default_factory=ScenarioSpec)
    scene_id: str | None = Field(default=None, max_length=64, pattern=r"^scene-\d{4}$")
    capture_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    max_latency_ms: float | None = Field(default=None, gt=0, le=60000)

    @model_validator(mode="after")
    def unique_models(self):
        if len(set(self.model_ids)) != len(self.model_ids):
            raise ValueError("Duplicate model IDs")
        if self.source == "nuscenes" and self.scene_id is None:
            raise ValueError("scene_id is required for nuScenes")
        if self.source == "nuscenes" and self.capture_id is not None:
            raise ValueError("capture_id is only supported for CARLA replay")
        return self


class AgentPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
