"""Full CPU replay acceptance CLI, optional real LLM, no CARLA."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from src.agents import replay_agent, sensor_agent
from src.config import get_settings
from src.models.replay import ReplayStudySpec
from src.services import sensor_studies as studies
from src.services.dataset_replay import catalog


async def run(args):
    settings = get_settings()
    root = (args.root or settings.experiment_root / "replay-tests" / uuid.uuid4().hex).resolve()
    settings.experiment_root = root
    os.environ["EXPERIMENT_ROOT"] = str(root)
    root.mkdir(parents=True, exist_ok=True)
    print("Artifacts:", root, flush=True)
    if args.study_id:
        study = studies.get(args.study_id)
        if study["source"] != "dataset_replay":
            raise ValueError("This CLI only supports dataset_replay studies")
    else:
        available = catalog()
        print(json.dumps(available, ensure_ascii=False, indent=2), flush=True)
        if not available["ready"]:
            raise FileNotFoundError(available["error"] or "Replay dataset unavailable")
        with studies.connection() as db:
            if db.execute("SELECT 1 FROM experiments WHERE status IN ('queued','running')").fetchone():
                raise ValueError("Use a fresh --root; queue is not empty")
        if args.spec:
            study = studies.create(ReplayStudySpec.model_validate_json(args.spec.read_text(encoding="utf-8")))
        elif args.deterministic:
            study = studies.create(ReplayStudySpec(
                scenarios=[{"scene_id": args.scene, "frames": args.frames}],
                profiles=[{"name": "half", "lidar": {"keep_fraction": 0.5}, "radar": {"keep_fraction": 0.5},
                           "camera": {"scale": 0.5, "jpeg_quality": 80}}]))
        else:
            study = await replay_agent.start(args.message, diagnostics_path=root / "agent-plan.json")
    ident = study["id"]
    print("Study:", ident, flush=True)
    (root / "study-start.json").write_text(json.dumps(study, ensure_ascii=False, indent=2), encoding="utf-8")
    deadline = time.monotonic() + args.timeout
    try:
        while study["status"] == "running":
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Replay study timeout")
            subprocess.run([sys.executable, "-m", "scripts.experiment_worker", "--once"],
                           timeout=min(600, remaining), env=os.environ.copy(), check=False)
            study = studies.advance(ident)
            if study.get("waiting_for_queue"):
                raise RuntimeError("Unexpected other jobs; use a dedicated --root")
            print([(j["profile"], j["status"]) for j in study["jobs"]], flush=True)
        report = studies.comparison(ident)
        (root / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if not args.deterministic:
            summary = await sensor_agent.summarize(ident)
            (root / "agent-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            print(summary["explanation"], flush=True)
        if any(j["status"] != "succeeded" for j in study["jobs"]):
            raise RuntimeError("At least one trial failed; inspect comparison.json and study errors")
        print("Completed; comparison.json saved", flush=True)
    except (KeyboardInterrupt, TimeoutError, subprocess.TimeoutExpired):
        studies.cancel(ident)
        raise


def main():
    # Windows redirected terminals may default to cp1252; reports contain Vietnamese.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--deterministic", action="store_true", help="Skip all LLM calls")
    parser.add_argument("--message", default="So sánh half LiDAR/radar và camera nửa độ phân giải ở scene-0103, 2 frames")
    parser.add_argument("--scene", default="scene-0103")
    parser.add_argument("--frames", type=int, default=2)
    parser.add_argument("--spec", type=Path, help="Local ReplayStudySpec JSON; skips planning")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--study-id")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    if args.study_id and not args.root:
        parser.error("--study-id requires --root")
    if not 1 <= args.frames <= 20 or not 60 <= args.timeout <= 7200 or not 1 <= len(args.message) <= 2000:
        parser.error("frames 1..20, timeout 60..7200, message 1..2000 characters")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
