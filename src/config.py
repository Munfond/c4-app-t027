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
    llm_provider: Literal["openai", "openrouter"] = "openai"
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    @property
    def llm_api_key(self) -> str:
        # Explicit provider selection prevents sending a key to the wrong host.
        return self.openrouter_api_key if self.llm_provider == "openrouter" else self.openai_api_key

    @property
    def llm_base_url(self) -> str:
        return "https://openrouter.ai/api/v1" if self.llm_provider == "openrouter" else "https://api.openai.com/v1"

    experiment_root: Path = PROJECT_ROOT / "data/experiments"
    native_input_adapter_manifest: Path = PROJECT_ROOT / "eval/recovery-mvp-2026-10-13/native-input-adapter.json"
    native_profile_pilot_report: Path = PROJECT_ROOT / "eval/recovery-mvp-2026-10-13/native-12-profile-audit.json"
    occupancy_rl_root: Path = PROJECT_ROOT / "data/rl-occupancy-ppo-20261013"
    native_rl_matrix_root: Path = PROJECT_ROOT / "data/native-rl-matrix-v1-20261013"
    native_rl_replay_root: Path = PROJECT_ROOT / "data/native-rl-measured-v1-20261013"
    native_rl_root: Path = PROJECT_ROOT / "data/native-rl-ppo-v1-20261013"
    native_online_root: Path = PROJECT_ROOT / "data"
    experiment_device: Literal["cpu", "cuda"] = "cpu"
    experiment_cpu_threads: int = Field(default=2, ge=1, le=32)
    experiment_lease_seconds: int = Field(default=600, ge=60)
    carla_host: str = "127.0.0.1"
    carla_port: int = Field(default=2000, ge=1, le=65535)
    carla_tm_port: int = Field(default=8001, ge=1, le=65535)
    carla_min_available_memory_gib: float = Field(default=10, ge=2, le=128)
    carla_timeout_seconds: float = Field(default=30, ge=1, le=120)
    # Optional trusted local binary: a fresh simulator per capture, owned by worker.
    carla_server_executable: Path | None = None
    # Optional isolated client (e.g. Python 3.7 + CARLA 0.9.11); backend stays on Python >=3.11.
    carla_python_executable: Path | None = None
    carla_client_path: Path | None = None
    carla_bridge_timeout_seconds: float = Field(default=600, ge=60, le=7200)
    carla_follow_ego: bool = False
    carla_realtime_capture: bool = False
    experiment_agent_enabled: bool = False
    experiment_agent_model: str = "gpt-4o-mini"
    experiment_api_enabled_in_production: bool = False
    experiment_execution_mode: Literal["local", "remote"] = "local"
    experiment_access_token: str = ""
    remote_worker_tokens: str = "{}"  # JSON {worker_id: token}; backend only.
    remote_database_url: str = ""
    remote_storage_endpoint: str = ""
    remote_storage_region: str = "auto"
    remote_storage_bucket: str = ""
    remote_storage_access_key: str = ""
    remote_storage_secret_key: str = ""
    remote_storage_prefix: str = "p027-jobs"
    remote_artifact_max_bytes: int = Field(default=32 * 1024 * 1024, ge=1024, le=128 * 1024 * 1024)
    remote_job_max_bytes: int = Field(default=512 * 1024 * 1024, ge=1024, le=2 * 1024**3)
    remote_lease_seconds: int = Field(default=120, ge=30, le=900)
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
