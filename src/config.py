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

    # Database
    database_url: str = "sqlite:///./data/app.db"

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"


@lru_cache
def get_settings() -> Settings:
    return Settings()
