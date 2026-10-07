"""Watch the ego car while collecting model inputs and running occupancy inference."""
import argparse
import json
import sys
import uuid
from pathlib import Path

from src.config import get_settings
from src.models.experiments import ExperimentSpec
from src.services import experiment_store as store
from src.services.experiment_runner import run_once


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=81)
    parser.add_argument("--vehicles", type=int, default=4)
    parser.add_argument("--highway", action="store_true", help="Town04 multilane highway")
    parser.add_argument("--lane-change-seconds", type=float)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    settings = get_settings()
    settings.carla_follow_ego = True
    settings.carla_realtime_capture = True
    settings.experiment_device = "cpu"
    settings.experiment_root = (args.root or settings.experiment_root / "watch" / uuid.uuid4().hex).resolve()
    spec = ExperimentSpec(scenario={"map": "Town04" if args.highway else "Town01",
                                    "route_kind": "highway" if args.highway else "spawn",
                                    "lane_change_interval_seconds": args.lane_change_seconds,
                                    "vehicles": args.vehicles, "pedestrians": 0, "frames": args.frames})
    if store.recent():
        raise RuntimeError("Use a fresh --root for this visible capture")
    job = store.create(spec)
    print("Watching ego:", spec.scenario.map, "camera follows the car, capture in real time.", flush=True)
    print("Artifacts:", settings.experiment_root, flush=True)
    print("Job:", job["id"], flush=True)
    result = run_once()
    (settings.experiment_root / "watch-result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("Status:", result["status"], flush=True)
    if result["status"] != "succeeded":
        raise RuntimeError(result["error"])
    print("Saved capture, model predictions and metrics.", flush=True)


if __name__ == "__main__":
    main()
