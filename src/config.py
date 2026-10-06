from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "P-027 Perception Lab"
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:3000"
    nusc_root: Path = PROJECT_ROOT / "data/nuscenes"
    lab_data_root: Path = PROJECT_ROOT / "data/lab"
    sim_data_root: Path = PROJECT_ROOT / "data/sim"
    camera_cache_dir: Path | None = None
    plate_weights: Path = PROJECT_ROOT / "weights/plate_yolov8.pt"
    anonymizer_enabled: bool = False
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    max_image_pixels: int = Field(default=12_000_000, ge=1)

    @property
    def resolved_camera_cache_dir(self) -> Path:
        return self.camera_cache_dir or (self.lab_data_root / "cache/cameras")

    # LLM
    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    experiment_root: Path = PROJECT_ROOT / "data/experiments"
    experiment_device: Literal["cpu", "cuda"] = "cpu"
    experiment_cpu_threads: int = Field(default=2, ge=1, le=32)
    experiment_lease_seconds: int = Field(default=600, ge=60)
    carla_host: str = "127.0.0.1"
    carla_port: int = Field(default=2000, ge=1, le=65535)
    carla_tm_port: int = Field(default=8001, ge=1, le=65535)
    carla_timeout_seconds: float = Field(default=30, ge=1, le=120)
    experiment_agent_enabled: bool = False
    experiment_agent_model: str = "gpt-4o-mini"
    experiment_api_enabled_in_production: bool = False
    experiment_max_pending: int = Field(default=5, ge=1, le=50)
    # Optional local post-NMS camera detector; never supplied by API/LLM.
    replay_camera_onnx: Path | None = None
    replay_camera_input_size: int = Field(default=640, ge=64, le=2048)
    replay_camera_score_threshold: float = Field(default=0.25, ge=0, le=1)

    # Database
    database_url: str = "sqlite:///./data/app.db"

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"


@lru_cache
def get_settings() -> Settings:
    return Settings()
