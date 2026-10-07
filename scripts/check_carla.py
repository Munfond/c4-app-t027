"""Read-only preflight for a fresh checkout; no actors, weather changes or world ticks."""

import importlib.util
import json
import platform
import sys

from src.config import get_settings
from src.services.experiment_registry import verified_hash
from src.simulation.carla_bridge import probe


def check():
    settings = get_settings()
    checkpoint = verified_hash("occupancy_lidar")
    if settings.carla_server_executable:
        from importlib.metadata import version

        connection = {
            "mode": "worker_managed", "client_version": version("carla"),
            "server_binary_exists": settings.carla_server_executable.is_file(),
            "notice": "Live server/client match is checked by the worker on each fresh capture",
        }
    else:
        connection = probe(settings)
    return {
        "python": sys.version,
        "platform": platform.platform(),
        **connection,
        "checkpoint_sha256": checkpoint,
        "torch_installed": importlib.util.find_spec("torch") is not None,
        "agent_enabled": settings.experiment_agent_enabled,
        "api_key_configured": bool(settings.openai_api_key),
        "device": settings.experiment_device,
    }


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
