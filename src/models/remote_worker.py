"""Bounded v1 protocol: fresh CARLA LiDAR occupancy, no executable commands."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkerHello(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol: Literal[1] = 1
    checkpoint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    adapter: dict | None = None
    ready: bool = False
    notice: str = Field(default="", max_length=300)


class Lease(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lease: str = Field(pattern=r"^[a-f0-9]{32}$")


class JobHeartbeat(Lease):
    stage: str = Field(default="running", max_length=100)
    completed_frames: int | None = Field(default=None, ge=0, le=81)


class ArtifactSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=160)
    bytes: int = Field(gt=0, le=128 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class UploadRequest(Lease):
    artifacts: list[ArtifactSpec] = Field(min_length=1, max_length=500)


class JobComplete(Lease):
    result: dict


class JobFailure(Lease):
    status: Literal["failed", "cancelled"] = "failed"
    error: str = Field(min_length=1, max_length=1500)
