"""Linux-ready replay/diagnostic CLI; no ROS/CUDA dependency for the core."""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.active_sensing.core import default_profiles
from src.active_sensing.replay import Replay, summarize


def doctor():
    report = {
        "python": sys.version.split()[0],
        "modules": {name: importlib.util.find_spec(name) is not None for name in (
            "carla", "rclpy", "numpy", "torch", "gymnasium", "stable_baselines3", "sb3_contrib"
        )},
        "ros_installations": [str(p) for p in Path("/opt/ros").glob("*")],
        "nvidia_smi": shutil.which("nvidia-smi"),
    }
    if report["nvidia_smi"]:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        report["gpu"] = proc.stdout.strip() or proc.stderr.strip()
        report["driver_query_ok"] = proc.returncode == 0
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    sub.add_parser("profiles")
    fixture = sub.add_parser("fixture")
    fixture.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("evaluate")
    run.add_argument("replay", type=Path)
    run.add_argument("--split", choices=("train", "validation", "test"), default="test")
    run.add_argument("--allow-synthetic", action="store_true")
    run.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "doctor":
        print(json.dumps(doctor(), indent=2))
    elif args.command == "fixture":
        from src.active_sensing.fixtures import synthetic_replay
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(synthetic_replay(), indent=2) + "\n")
        print(f"SYNTHETIC software fixture written to {args.output}; not experimental evidence")
    elif args.command == "profiles":
        print(json.dumps([asdict(p) for p in default_profiles()], indent=2))
    else:
        replay = Replay.load(args.replay, allow_synthetic=args.allow_synthetic)
        episodes = [e for e in replay.episodes if e["split"] == args.split]
        if not episodes:
            parser.error(f"No {args.split} episodes")
        reports = {}
        for policy in ("full", "minimum", "rule"):
            logs = [row for e in episodes for row in replay.run(e["id"], policy)]
            reports[policy] = {"summary": summarize(logs), "timeline": logs}
        output = {
            "schema_version": 1, "provenance": replay.provenance,
            "split": args.split, "reports": reports,
            "disclaimer": "Synthetic fixtures test software only; no performance claim.",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
        print(json.dumps({p: r["summary"] for p, r in reports.items()}, indent=2))


if __name__ == "__main__":
    main()
