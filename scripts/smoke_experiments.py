"""Run actual registered checkpoints on a bounded real mini-val scene, no LLM calls.

python -m scripts.smoke_experiments --frames 2
"""

import argparse
import json

from src.models.experiments import ExperimentSpec
from src.services import experiment_store as store
from src.services.experiment_registry import MODELS
from src.services.experiment_runner import run_once


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=2)
    parser.add_argument("--scene", choices=["scene-0103", "scene-0916"], default="scene-0103")
    parser.add_argument("--models", nargs="+", choices=list(MODELS), default=list(MODELS))
    args = parser.parse_args()
    spec = ExperimentSpec(
        source="nuscenes", scene_id=args.scene, model_ids=args.models, scenario={"frames": args.frames}
    )
    job = store.create(spec)
    print(f"Created {job['id']}", flush=True)
    result = run_once()
    if result is None or result["id"] != job["id"]:
        raise RuntimeError("Another experiment is running/queued; run the normal worker and poll this experiment")
    print(
        json.dumps(
            {
                "id": result["id"],
                "status": result["status"],
                "error": result["error"],
                "models": result["result"]["models"] if result["result"] else None,
            },
            indent=2,
        )
    )
    if result["status"] != "succeeded":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
