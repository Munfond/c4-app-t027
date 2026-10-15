"""Isolated local runner for one frozen remote assignment; never accepts shell code."""

import argparse
import hashlib
import json
import signal
import time
from pathlib import Path

from src.models.experiments import ExperimentSpec
from src.services import experiment_store as store
from src.services.experiment_registry import validate_spec
from src.services.experiment_runner import run_once


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assignment", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    if store.get_settings().experiment_execution_mode != "local":
        raise ValueError("Trial subprocess must use a local isolated queue")
    assignment = json.loads(args.assignment.read_text())
    frozen = assignment["spec"]
    spec = ExperimentSpec.model_validate(frozen["request"])
    if spec.source != "carla" or spec.capture_id or spec.model_ids != ["occupancy_lidar"]:
        raise ValueError("Unsupported remote assignment")
    validate_spec(spec)

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, interrupt)
    with store.scope(args.directory):
        with store.connection() as db:
            if db.execute("SELECT 1 FROM experiments").fetchone():
                raise ValueError("Trial queue already exists; do not recapture on resume")
            db.execute("INSERT INTO experiments(id,fingerprint,spec,status,stage,created) VALUES(?,?,?,?,?,?)",
                       (assignment["id"], hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest(),
                        json.dumps(frozen), "queued", "queued", time.time()))
        job = run_once()
        if not job or job["status"] != "succeeded":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
