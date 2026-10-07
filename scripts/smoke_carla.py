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
    args = parser.parse_args()
    # External servers are checked now; managed servers are checked on startup.
    settings = store.get_settings()
    connection = {"mode": "worker_managed"} if settings.carla_server_executable else probe(settings)
    with store.scope(args.output.resolve()):
        if any(job["status"] in ("queued", "running") for job in store.recent()):
            parser.error("Smoke output has pending jobs; inspect them or choose another --output")
        job = store.create(ExperimentSpec(scenario={
            "map": "Town01", "weather": "clear", "vehicles": 2,
            "pedestrians": 0, "frames": 2, "seed": 42,
        }))
        result = run_once()
        if result is None or result["id"] != job["id"]:
            raise RuntimeError("Another worker claimed the smoke job; inspect its status")
        report = {
            "connection": connection, "job_id": job["id"],
            "status": result["status"], "error": result["error"],
            "result": result["result"], "llm_called": False,
            "notice": "CARLA/occupancy smoke only; not held-out evaluation or real-world safety evidence.",
        }
        (args.output / "smoke-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({key: value for key, value in report.items() if key != "result"}, indent=2))
        if result["status"] != "succeeded":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
