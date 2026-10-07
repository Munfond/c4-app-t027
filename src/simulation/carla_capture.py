"""Dispatch capture to a local client or an isolated legacy Python client."""
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from src.config import get_settings
from src.simulation.carla_capture_core import matching_sensor  # noqa: F401


@contextmanager
def simulator_lock(settings, directory=None):
    """One capture per CARLA server; the OS drops the lock when its owner process dies."""
    name = re.sub(r"[^A-Za-z0-9.-]", "_", f"{settings.carla_host}-{settings.carla_port}")
    path = Path(directory or tempfile.gettempdir()) / f"p027-carla-{name}.lock"
    with path.open("a+b") as handle:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(
                f"CARLA {settings.carla_host}:{settings.carla_port} is busy with another capture; "
                "run only one worker per simulator"
            ) from exc
        yield


def capture(scenario, root, pulse):
    settings = get_settings()
    with simulator_lock(settings):
        if settings.carla_python_executable:
            from src.simulation.carla_bridge import capture_external
            return capture_external(scenario, root, pulse, settings)
        from src.simulation.carla_capture_core import capture as capture_local
        from src.simulation.carla_server import fresh_server

        if settings.carla_server_executable:
            from src.simulation.carla_bridge import capture_external

            # CARLA caches native Traffic Manager clients by port. Keep those
            # objects out of the long-lived worker when servers are restarted.
            isolated = settings.model_copy(update={"carla_python_executable": Path(sys.executable),
                                                   "carla_client_path": None})
            with fresh_server(settings, root, pulse):
                frames, manifest = capture_external(scenario, root, pulse, isolated)
            manifest["client_runtime"] = "isolated_matching_worker_python"
            manifest["server_lifecycle"] = "fresh_process_per_capture"
        else:
            frames, manifest = capture_local(scenario, root, pulse, settings)
            manifest["server_lifecycle"] = "external"
        return frames, manifest
