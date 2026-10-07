"""Local agent acceptance CLI, bounded study with dedicated queue and simulator.

python -m scripts.test_sensor_agent --message "Thử LiDAR ở Town01, ít xe"
python -m scripts.test_sensor_agent --deterministic  # CARLA + inference, no LLM/key
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from src.agents import sensor_agent
from src.config import get_settings
from src.models.experiments import SensorStudySpec
from src.services import sensor_studies as studies


def save_dataset_index(study, root):
    """Map the original prompt and sensor settings to each checkpoint input/output."""
    records = []
    for job in study["jobs"]:
        if job["status"] != "succeeded":
            continue
        manifest = job["result"]["manifest"]
        for index, frame in enumerate(manifest["frames"]):
            name = frame["id"]
            prefix = f"{job['id']}/capture/{name}"
            prediction = f"{job['id']}/predictions/occupancy_lidar/{index:04d}.json"
            for path in (prefix + ".npz", prefix + ".png", prefix + ".json", prediction):
                if not (root / path).is_file():
                    raise RuntimeError(f"Dataset artifact missing: {path}")
            records.append({
                "job_id": job["id"], "environment": job["environment"], "profile": job["profile"],
                "frame": frame, "lidar": manifest["scenario"]["lidar"],
                "input_npz": prefix + ".npz", "camera_png": prefix + ".png",
                "geometry_json": prefix + ".json", "prediction_json": prediction,
            })
    (root / "dataset-index.json").write_text(json.dumps({
        "study_id": study["id"], "prompt": study["metadata"].get("request"),
        "artifact_root": str(root.resolve()),
        "trials": [{"job_id": job["id"], "profile": job["profile"], "status": job["status"]}
                   for job in study["jobs"]],
        "checkpoint_id": "occupancy_lidar", "checkpoint_sha256": study["checkpoint_sha256"],
        "input": "NPZ x has 7 BEV channels; occupancy_lidar consumes channels 0,1,2,3",
        "output": "200x200 occupancy classes: free, static, object",
        "records": records,
    }, indent=2, ensure_ascii=False), encoding="utf-8")


async def run(args):
    settings = get_settings()
    if args.watch:
        settings.carla_follow_ego = True
        settings.carla_realtime_capture = True
        os.environ["CARLA_FOLLOW_EGO"] = "true"
        os.environ["CARLA_REALTIME_CAPTURE"] = "true"
    # A fresh queue avoids executing other user's experiments during an acceptance test.
    root = args.root or settings.experiment_root / "sensor-agent-tests" / uuid.uuid4().hex
    settings.experiment_root = root.resolve()
    os.environ["EXPERIMENT_ROOT"] = str(settings.experiment_root)
    root = settings.experiment_root
    root.mkdir(parents=True, exist_ok=True)
    print("Artifacts:", root, flush=True)
    from scripts.check_carla import check

    existing = studies.get(args.study_id) if args.study_id else None
    if existing is None or existing["status"] == "running":
        print(json.dumps(check(), indent=2), flush=True)
    if not args.study_id:
        with studies.connection() as db:
            if db.execute("SELECT 1 FROM experiments WHERE status IN ('queued','running')").fetchone():
                raise RuntimeError("Queue not empty; use a fresh --root")
    if args.study_id:
        study = existing
    elif args.deterministic:
        study = studies.create(
            SensorStudySpec(
                scenarios=[{"map": "Town01", "vehicles": 2, "pedestrians": 0, "frames": 2}],
                profiles=[{"name": "half_points", "lidar": {"points_per_second": 300000}}],
            )
        )
    else:
        study = await sensor_agent.start(args.message)
    ident = study["id"]
    print("Study:", ident, "Trials:", study["total_trials"], flush=True)
    (root / "study-start.json").write_text(json.dumps(study, indent=2, ensure_ascii=False), encoding="utf-8")
    deadline = time.monotonic() + args.timeout
    try:
        while study["status"] == "running":
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Study timeout; inspect simulator before retry")
            subprocess.run(
                [sys.executable, "-m", "scripts.experiment_worker", "--once"],
                env=os.environ.copy(),
                timeout=min(600, remaining),
                check=False,
            )
            study = studies.advance(ident)
            print([(j["profile"], j["status"]) for j in study["jobs"]], flush=True)
            if study.get("waiting_for_queue"):
                raise RuntimeError("Unexpected other jobs; use a dedicated test queue")
        result = studies.comparison(ident)
        (root / "comparison.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
        save_dataset_index(study, root)
        if not args.deterministic:
            summary = await sensor_agent.summarize(ident)
            (root / "agent-summary.json").write_text(
                json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(summary["explanation"], flush=True)
        if any(j["status"] != "succeeded" for j in study["jobs"]):
            raise RuntimeError("At least one trial failed; inspect study errors, no success acceptance")
    except (KeyboardInterrupt, TimeoutError, subprocess.TimeoutExpired):
        studies.cancel(ident)
        print("Cancelled study. If worker was killed, inspect/restart dedicated CARLA world before retry.", flush=True)
        raise


def main():
    # Windows redirected stdout may default to cp1252; agent summaries are Vietnamese.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--message", default="Thử cấu hình LiDAR tiết kiệm dữ liệu ở Town01 ít xe, 2 frames")
    parser.add_argument("--deterministic", action="store_true", help="Test simulator/tools without LLM calls")
    parser.add_argument("--watch", action="store_true", help="Follow ego in the CARLA window and pace capture in real time")
    parser.add_argument("--root", type=Path, help="Dedicated artifacts directory; required when resuming a study")
    parser.add_argument("--study-id", help="Resume existing study in --root; never repeat LLM planning")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    if args.study_id and not args.root:
        parser.error("--study-id requires --root")
    if not 60 <= args.timeout <= 7200:
        parser.error("--timeout must be 60..7200 seconds")
    if not 1 <= len(args.message) <= 2000:
        parser.error("--message must be 1..2000 characters")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
