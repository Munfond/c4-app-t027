"""Optional local simulator lifecycle. Never terminate an externally started server."""

import importlib
import os
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path


def require_memory_headroom(minimum_gib, meminfo_path=Path("/proc/meminfo")):
    fields = dict(line.split(":", 1) for line in meminfo_path.read_text().splitlines())
    available = int(fields["MemAvailable"].split()[0]) / 1024**2
    if available < minimum_gib:
        raise RuntimeError(
            f"CARLA needs {minimum_gib:g} GiB available RAM before launch; "
            f"currently {available:.1f} GiB. Close applications before a fresh capture."
        )
    return available


def require_nvidia_health():
    # Managed server explicitly uses NVIDIA PRIME/Vulkan offload. Refuse a broken
    # driver before launching Unreal; never reset a GPU owned by the desktop.
    binary = shutil.which("nvidia-smi")
    if binary is None:
        raise RuntimeError("Managed NVIDIA CARLA requires nvidia-smi; check the installed driver")
    try:
        result = subprocess.run([binary, "-L"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("NVIDIA health check failed before CARLA launch") from exc
    if result.returncode != 0 or not any(line.startswith("GPU ") for line in result.stdout.splitlines()):
        raise RuntimeError("NVIDIA GPU unavailable; check nvidia-smi before retrying CARLA. No driver reset attempted.")


@contextmanager
def fresh_server(settings, root, pulse):
    binary = settings.carla_server_executable.resolve()
    if settings.carla_host not in ("127.0.0.1", "localhost"):
        raise ValueError("Managed CARLA requires a localhost server")
    if settings.carla_python_executable:
        raise ValueError("Managed CARLA requires the client in the worker's Python runtime")
    if sys.platform != "linux" or not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError("Managed CARLA requires an executable Linux server binary")
    require_nvidia_health()
    require_memory_headroom(settings.carla_min_available_memory_gib)
    # Refuse occupied ports; another person's simulator must remain untouched.
    for port in (settings.carla_port, settings.carla_port + 1, settings.carla_tm_port):
        with socket.socket() as probe:
            # Permit sockets in TIME_WAIT after our previous server stopped;
            # a live listener still prevents binding (no SO_REUSEPORT).
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", port))
    carla = importlib.import_module("carla")
    root.mkdir(parents=True, exist_ok=True)
    env = dict(
        os.environ,
        __NV_PRIME_RENDER_OFFLOAD="1",
        __GLX_VENDOR_LIBRARY_NAME="nvidia",
        __VK_LAYER_NV_optimus="NVIDIA_only",
    )
    command = [
        str(binary),
        "-RenderOffScreen",
        "-quality-level=Low",
        "-ResX=640",
        "-ResY=360",
        "-ExecCmds=t.MaxFPS 20",
        f"-carla-rpc-port={settings.carla_port}",
        "-nosound",
    ]
    with (root / "server.log").open("w") as log:
        process = subprocess.Popen(command, cwd=binary.parents[3], env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + max(60, settings.carla_timeout_seconds)
            while True:
                pulse()
                if process.poll() is not None:
                    raise RuntimeError(f"CARLA exited ({process.returncode}); inspect capture/server.log")
                try:
                    # Recreate clients whose first connection predates the RPC socket.
                    client = carla.Client(settings.carla_host, settings.carla_port)
                    client.set_timeout(2)
                    server_version = client.get_server_version()
                    client.get_world().get_map()
                    break
                except RuntimeError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Managed CARLA startup timed out; inspect capture/server.log") from None
                    time.sleep(1)
            if client.get_client_version() != server_version:
                raise RuntimeError("CARLA client/server version mismatch")
            del client  # No readiness RPC connection survives server termination.

            def managed_pulse():
                pulse()
                if process.poll() is not None:
                    raise RuntimeError(
                        f"Owned CARLA server exited during capture ({process.returncode}); inspect server.log"
                    )

            yield managed_pulse
        finally:
            # Only the process created above; cleanup also runs on cancellation/errors.
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
