from typing import Literal

from pydantic import BaseModel


class Frame(BaseModel):
    sample_token: str
    sample_idx: int
    scene: str
    timestamp_s: float
    split: Literal["mini_val"]


class FrameList(BaseModel):
    items: list[Frame]


class Scene(BaseModel):
    id: str
    split: Literal["mini_val"]
    frame_count: int


class SceneList(BaseModel):
    items: list[Scene]


class ModelInfo(BaseModel):
    id: str
    sensors: list[str]
    origin: Literal["official", "own", "mixed"]
    mode: Literal["precomputed"]
    available: bool
    split: Literal["mini_val"]
    contaminated: bool
    fusion_type: str | None


class ModelList(BaseModel):
    items: list[ModelInfo]
    limitations: list[str]


class DetectionBox(BaseModel):
    class_name: str
    x: float
    y: float
    z: float
    w: float
    l: float  # noqa: E741 - length column in the versioned detection export
    h: float
    yaw: float
    vx: float
    vy: float
    score: float


class DetectionFrame(BaseModel):
    frame: Frame
    model: str
    mode: Literal["precomputed"]
    coordinates: dict[str, str]
    boxes: list[DetectionBox]
