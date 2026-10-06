"""Read-only preflight for a fresh checkout; no actors, weather changes or world ticks."""

import importlib.util
import json
import platform
import sys

from src.config import get_settings
from src.services.experiment_registry import verified_hash


def check():
    import carla

    settings = get_settings()
    checkpoint = verified_hash("occupancy_lidar")
    client = carla.Client(settings.carla_host, settings.carla_port)
    client.set_timeout(settings.carla_timeout_seconds)
    local, server = client.get_client_version(), client.get_server_version()
    if local != server:
        raise RuntimeError(f"Client/server version mismatch: {local} != {server}; install wheel bundled with server")
    world = client.get_world()
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "server_version": server,
        "client_version": local,
        "map": world.get_map().name,
        "available_maps": client.get_available_maps(),
        "checkpoint_sha256": checkpoint,
        "torch_installed": importlib.util.find_spec("torch") is not None,
        "agent_enabled": settings.experiment_agent_enabled,
        "api_key_configured": bool(settings.openai_api_key),
        "device": settings.experiment_device,
    }


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
