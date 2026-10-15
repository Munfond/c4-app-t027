"""Resumable research capture matrix. One queued trial, shared worker, interactive jobs take priority."""

import argparse
import fcntl
import hashlib
import json
import signal
import time
from pathlib import Path

from src.inference.native_input import fingerprint
from src.models.experiments import ExperimentSpec
from src.services import experiment_store as store
from src.services.experiment_registry import verified_hash

PROFILES = [
    {"channels": channels, "points_per_second": rate}
    for channels in (16, 32, 64)
    for rate in (150000, 300000, 450000, 600000)
]
EPISODES = [
    {"id": "train-route05-seed105", "split": "train", "route": 5, "seed": 105},
    {"id": "train-route22-seed122", "split": "train", "route": 22, "seed": 122},
    {"id": "validation-route48-seed148", "split": "validation", "route": 48, "seed": 148},
    {"id": "test-route72-seed172", "split": "test", "route": 72, "seed": 172},
]


def sealed_plan():
    return {
        "kind": "native_occupancy_research_capture_plan_v1",
        "profiles": PROFILES,
        "episodes": EPISODES,
        "frames_per_profile": 20,
        "capture_interval": 0.5,
        "baseline_action": 7,
        "checkpoint_sha256": verified_hash("occupancy_lidar"),
        "adapter": fingerprint("intensity_mean_experimental"),
        "observation_policy": "Current profile raw sensor context + previous measured latency + previous action; no GT, route/seed IDs or counterfactual scores in actor",
        "decision_timing": "Bootstrap full-profile frame0, action affects next recorded frame; score frames1..19; report bootstrap separately",
        "label_policy": "Only semantic-LiDAR observed cells; static-height proxy + visible actor footprints",
        "required_audit": [
            "Exact reference across all12 profiles at every frame",
            "Raw points/intensity reproduce features",
            "All12 profiles completed for every split",
            "Independent frame/raw artifact hashes",
            "No pose/route/seed duplication across split",
            "Reference object coverage measured, not claimed from requested population",
        ],
        "research_training_admitted": False,
        "deployment_ready": False,
        "limits": [
            "Small four-route Town01 research demonstration; no real-world or other-map claim",
            "Only2 training episodes; no claim of broad generalization",
            "WeatherRGB is not physical LiDAR weather corruption",
            "No change to frozen nuScenes PPO report/policy; no training before independent matrix audit",
        ],
    }


def save(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--retry-failed", help="One explicit SIG11 retry for this matrix; exact failed job ID, no automatic retries"
    )
    args = parser.parse_args()
    plan = sealed_plan()
    args.output.mkdir(parents=True, exist_ok=True)
    lock = (args.output / "collector.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error("Another collector owns this matrix; do not run duplicate collectors")
    p = args.output / "capture-plan.json"
    if p.exists():
        if not args.resume:
            parser.error("Preserve earlier matrix; use --resume or a new output")
        if (
            hashlib.sha256(p.read_bytes()).hexdigest() != p.with_suffix(".sha256").read_text().strip()
            or json.loads(p.read_text()) != plan
        ):
            parser.error("Plan/model/adapter changed; do not mix capture protocols")
    else:
        save(p, plan)
        p.with_suffix(".sha256").write_text(hashlib.sha256(p.read_bytes()).hexdigest() + "\n")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    if args.plan_only:
        print(json.dumps({"plan_sha256": digest, "trials": 48, "frames": 960, "training_admitted": False}))
        return
    state_path = args.output / "capture-state.json"
    state = (
        json.loads(state_path.read_text())
        if state_path.exists()
        else {"status": "capturing", "plan_sha256": digest, "trials": [], "research_training_admitted": False}
    )
    if args.retry_failed and not (
        args.resume
        and state["status"] == "incomplete_failed"
        and any(row["job_id"] == args.retry_failed for row in state["trials"])
    ):
        parser.error("Explicit retry must name the failed trial in this matrix")
    current = None
    allow_cancelled_retry = args.resume and state["status"] == "incomplete_interrupted"

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    state["status"] = "capturing"
    state.pop("error", None)
    save(state_path, state)
    try:
        for episode in EPISODES:
            reference = None
            for action, profile in enumerate(PROFILES):
                key = f"native-matrix:{digest[:16]}:{episode['id']}:{action}"
                found = next((row for row in state["trials"] if row["key"] == key), None)
                if found:
                    current = store.get(found["job_id"])
                    failed_retry = (
                        args.resume
                        and args.retry_failed == current["id"]
                        and current["status"] == "failed"
                        and "exited during capture (-11)" in (current["error"] or "")
                    )
                    if failed_retry and any(row.get("failed_retry") for row in state["trials"]):
                        raise ValueError("Matrix already used its single explicit native-crash retry")
                    if failed_retry:
                        found["failed_retry"] = {
                            "job_id": current["id"],
                            "error": current["error"],
                            "reason": "Explicit same-protocol retry after native SIG11; failed artifacts retained, no metric-based selection",
                        }
                    if failed_retry or (current["status"] == "cancelled" and allow_cancelled_retry):
                        found.setdefault("previous_job_ids", []).append(current["id"])
                        attempt = len(found["previous_job_ids"])
                        while any(job["status"] in ("queued", "running") for job in store.recent()):
                            time.sleep(2)
                        current = store.create(
                            ExperimentSpec.model_validate(current["spec"]["request"]),
                            f"{key}:resume{attempt}",
                            purpose="native_rl_collection",
                        )
                        found["job_id"] = current["id"]
                        save(state_path, state)
                else:
                    # Never queue the entire matrix. A user-created trial gets the next worker turn.
                    while any(job["status"] in ("queued", "running") for job in store.recent()):
                        time.sleep(2)
                    spec = ExperimentSpec(
                        native_input_adapter="intensity_mean_experimental",
                        scenario={
                            "map": "Town01",
                            "weather": "clear",
                            "vehicles": 2,
                            "pedestrians": 0,
                            "frames": 20,
                            "seed": episode["seed"],
                            "route_spawn_index": episode["route"],
                            "traffic_placement": "nearest_spawn",
                            "lidar": profile,
                        },
                    )
                    current = store.create(spec, key, purpose="native_rl_collection")
                    state["trials"].append(
                        {
                            "key": key,
                            "job_id": current["id"],
                            "episode": episode["id"],
                            "split": episode["split"],
                            "action": action,
                            "profile": profile,
                        }
                    )
                    save(state_path, state)
                while current["status"] in ("queued", "running"):
                    time.sleep(2)
                    current = store.get(current["id"])
                    state.update(
                        active_job=current["id"],
                        completed=sum(store.get(row["job_id"])["status"] == "succeeded" for row in state["trials"]),
                        total=48,
                    )
                    save(state_path, state)
                if current["status"] != "succeeded":
                    raise RuntimeError(f"Incomplete trial {current['id']}: {current['status']} {current['error']}")
                realized = current["result"]["manifest"]["reference_sha256"]
                if reference is None:
                    reference = realized
                elif realized != reference:
                    raise RuntimeError(f"Reference mismatch in {episode['id']}; do not admit matrix")
                state.update(
                    completed=sum(store.get(row["job_id"])["status"] == "succeeded" for row in state["trials"]),
                    total=48,
                )
                save(state_path, state)
                print(
                    json.dumps(
                        {"episode": episode["id"], "action": action, "completed": state["completed"], "total": 48}
                    ),
                    flush=True,
                )
        state.update(status="capture_completed", active_job=None, completed=48, total=48)
        save(state_path, state)
    except KeyboardInterrupt:
        if current and current["status"] in ("queued", "running"):
            store.cancel(current["id"])
        state.update(status="incomplete_interrupted", active_job=current["id"] if current else None)
        save(state_path, state)
        raise
    except Exception as exc:
        state.update(status="incomplete_failed", error=str(exc))
        save(state_path, state)
        raise


if __name__ == "__main__":
    main()
