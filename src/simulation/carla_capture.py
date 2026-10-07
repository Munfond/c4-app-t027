"""Dispatch capture to a local client or an isolated legacy Python client."""
from src.config import get_settings
from src.simulation.carla_capture_core import matching_sensor  # noqa: F401


def capture(scenario, root, pulse):
    settings = get_settings()
    if settings.carla_python_executable:
        from src.simulation.carla_bridge import capture_external
        return capture_external(scenario, root, pulse, settings)
    from src.simulation.carla_capture_core import capture as capture_local
    return capture_local(scenario, root, pulse, settings)
