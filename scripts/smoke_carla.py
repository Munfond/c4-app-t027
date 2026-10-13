"""Two synchronized CARLA frames + verified occupancy checkpoint; no LLM calls."""

import argparse
import json
from pathlib import Path

from src.models.experiments import ExperimentSpec
from src.services import experiment_store as store
from src.services.experiment_runner import run_once
from src.simulation.carla_bridge import probe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/runtime/carla-smoke"))
    parser.add_argument("--fov", type=int, choices=(60, 90, 110), default=90)
    parser.add_argument("--plan", action="store_true", help="Print bounded spec without queueing or launching")
    args = parser.parse_args()
    spec = ExperimentSpec(
        scenario={
            "map": "Town01",
            "weather": "clear",
            "vehicles": 2,
            "pedestrians": 0,
            "frames": 2,
            "seed": 42,
            "camera": {"fov": args.fov},
        }
    )
    if args.plan:
        print(spec.model_dump_json(indent=2))
        return
    if args.output.exists():
        parser.error("Use a new output directory; preserve earlier smoke evidence")
    # External servers are checked now; managed servers are checked on startup.
    settings = store.get_settings()
    if settings.carla_server_executable:
        from src.simulation.carla_server import require_memory_headroom

        require_memory_headroom(settings.carla_min_available_memory_gib)
    connection = {"mode": "worker_managed"} if settings.carla_server_executable else probe(settings)
    with store.scope(args.output.resolve()):
        if any(job["status"] in ("queued", "running") for job in store.recent()):
            parser.error("Smoke output has pending jobs; inspect them or choose another --output")
        job = store.create(spec)
        result = run_once()
        if result is None or result["id"] != job["id"]:
            raise RuntimeError("Another worker claimed the smoke job; inspect its status")
        validation = {"passed": False, "notice": "No successful native capture to verify"}
        if result["status"] == "succeeded":
            manifest = result["result"]["manifest"]
            realized = manifest.get("sensor_specs", {}).get("camera")
            # sensor_specs uses a (blueprint, attributes) tuple serialized as a list.
            fov = realized[1].get("fov") if isinstance(realized, (list, tuple)) and len(realized) == 2 else None
            files = [args.output / job["id"] / "capture" / (f["id"] + ".png") for f in manifest["frames"]]
            from PIL import Image

            dimensions = []
            for path in files:
                with Image.open(path) as image:
                    image.load()
                    dimensions.append(list(image.size))
            validation = {
                "passed": fov == str(args.fov) and len(files) == 2 and all(size == [640, 360] for size in dimensions),
                "requested_fov": args.fov,
                "recorded_fov": fov,
                "frames": len(files),
                "image_dimensions": dimensions,
            }
        report = {
            "connection": connection,
            "job_id": job["id"],
            "status": result["status"],
            "error": result["error"],
            "result": result["result"],
            "llm_called": False,
            "native_validation": validation,
            "notice": "CARLA/occupancy smoke only; not held-out evaluation or real-world safety evidence.",
        }
        (args.output / "smoke-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({key: value for key, value in report.items() if key != "result"}, indent=2))
        if result["status"] != "succeeded" or not validation["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
