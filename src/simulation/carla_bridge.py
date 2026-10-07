"""Local file bridge separating the CARLA client ABI from Torch and the API."""
import importlib.util
import json
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

from src.config import PROJECT_ROOT


def client_available(settings):
    if settings.carla_python_executable:
        return settings.carla_python_executable.is_file() and (
            settings.carla_client_path is None or settings.carla_client_path.exists()
        )
    return importlib.util.find_spec("carla") is not None


def run_client(request, work, pulse, settings):
    executable = settings.carla_python_executable
    if not executable or not executable.is_file():
        raise RuntimeError("CARLA_PYTHON_EXECUTABLE must point to the legacy client Python executable")
    request["settings"] = {key: getattr(settings, key) for key in (
        "carla_host", "carla_port", "carla_tm_port", "carla_timeout_seconds",
        "carla_follow_ego", "carla_realtime_capture"
    )}
    request["client_path"] = str(settings.carla_client_path.resolve()) if settings.carla_client_path else None
    request_file = work / "client-request.json"
    request_file.write_text(json.dumps(request), encoding="utf-8")
    with (work / "client.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [str(executable), "-u", "-X", "faulthandler", str(PROJECT_ROOT / "scripts/carla_legacy_client.py"),
             "--request", str(request_file)], stdout=log, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + settings.carla_bridge_timeout_seconds
        try:
            while process.poll() is None:
                pulse()
                if time.monotonic() >= deadline:
                    raise TimeoutError("Legacy CARLA client timed out; inspect/restart the dedicated simulator")
                time.sleep(0.2)
            pulse()
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    if process.returncode:
        detail = (work / "client.log").read_text(encoding="utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"Legacy CARLA client failed ({process.returncode}): {detail}")


def probe(settings):
    if settings.carla_python_executable:
        with tempfile.TemporaryDirectory(prefix="p027-carla-probe-") as directory:
            work = Path(directory)
            result = work / "result.json"
            run_client({"mode": "probe", "result": str(result)}, work, lambda: None, settings)
            return json.loads(result.read_text(encoding="utf-8"))
    import carla
    client = carla.Client(settings.carla_host, settings.carla_port)
    client.set_timeout(settings.carla_timeout_seconds)
    local, server = client.get_client_version(), client.get_server_version()
    if local != server:
        raise RuntimeError(f"CARLA client/server version mismatch: {local} != {server}")
    world = client.get_world()
    return {"client_version": local, "server_version": server, "map": world.get_map().name,
            "available_maps": client.get_available_maps(),
            "pedestrian_seed_supported": hasattr(world, "set_pedestrians_seed")}


def capture_external(scenario, root, pulse, settings):
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_client({"mode": "capture", "scenario": scenario.model_dump(), "root": str(root)},
               root, pulse, settings)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest["scenario"] != scenario.model_dump() or len(manifest["frames"]) != scenario.frames:
        raise ValueError("Legacy capture does not match requested scenario/frame count")
    frames = []
    for index in range(scenario.frames):
        pulse()
        name = f"frame_{index:04d}"
        with np.load(root / f"{name}.npz", allow_pickle=False) as data:
            frames.append({"id": name, **{key: data[key] for key in (
                "x", "labels", "valid", "rotation", "translation"
            )}, "flow": np.zeros((2, 200, 200), np.float32),
                "flow_valid": np.zeros((200, 200), bool)})
    manifest["client_runtime"] = "isolated"
    return frames, manifest
