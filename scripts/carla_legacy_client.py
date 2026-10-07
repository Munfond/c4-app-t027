"""Isolated matching/legacy CARLA client; no Pydantic, Torch or LLM imports."""
import argparse
import importlib
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace


class Scenario(SimpleNamespace):
    def model_dump(self):
        return dict(vars(self), lidar=vars(self.lidar))


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    if request.get("client_path"):
        sys.path.insert(0, request["client_path"])
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    carla = importlib.import_module("carla")
    settings = SimpleNamespace(**request["settings"])
    client = carla.Client(settings.carla_host, settings.carla_port)
    client.set_timeout(settings.carla_timeout_seconds)
    local, server = client.get_client_version(), client.get_server_version()
    if local != server:
        raise RuntimeError(f"CARLA client/server version mismatch: {local} != {server}")
    if request["mode"] == "probe":
        world = client.get_world()
        result = {"client_version": local, "server_version": server,
                  "map": world.get_map().name, "available_maps": client.get_available_maps(),
                  "client_python": sys.version,
                  "pedestrian_seed_supported": hasattr(world, "set_pedestrians_seed")}
        Path(request["result"]).write_text(json.dumps(result), encoding="utf-8")
    elif request["mode"] == "capture":
        from src.simulation.carla_capture_core import capture
        data = dict(request["scenario"])
        data["lidar"] = SimpleNamespace(**data["lidar"])
        capture(Scenario(**data), Path(request["root"]), lambda: None, settings)
    else:
        raise ValueError("Unknown client operation")


if __name__ == "__main__":
    main()
