"""Verify all physical captures, then measure a separate observed-cell native RL matrix."""

import argparse
import hashlib
import json
import platform
import signal
import time
from pathlib import Path

import numpy as np

from scripts.collect_native_rl_matrix import sealed_plan
from src.active_sensing.native_occupancy import ABI, BASELINE, PROFILES, REWARD, load_dataset, sensor_context
from src.evaluation.bev import BevEvaluator
from src.inference.bev import lidar_features
from src.inference.current import CurrentCheckpoint
from src.inference.native_input import apply
from src.models.experiments import ExperimentSpec
from src.services import experiment_store as store


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_sealed(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")
    path.with_suffix(".sha256").write_text(sha(path) + "\n")


def audit_captures(matrix):
    plan_path = matrix / "capture-plan.json"
    plan = json.loads(plan_path.read_text())
    if sha(plan_path) != plan_path.with_suffix(".sha256").read_text().strip() or plan != sealed_plan():
        raise ValueError("Capture plan/model/adapter changed")
    state = json.loads((matrix / "capture-state.json").read_text())
    if state["status"] != "capture_completed" or len(state["trials"]) != 48 or state["plan_sha256"] != sha(plan_path):
        raise ValueError("All48 successful physical trials required before measurement")
    audited, seen = [], set()
    for episode in plan["episodes"]:
        common = None
        for action, profile in enumerate(PROFILES):
            entries = [r for r in state["trials"] if r["episode"] == episode["id"] and r["action"] == action]
            if len(entries) != 1:
                raise ValueError("Missing or duplicate profile")
            row = entries[0]
            job = store.get(row["job_id"])
            if (
                job["id"] in seen
                or job["status"] != "succeeded"
                or row["split"] != episode["split"]
                or row["profile"] != profile
            ):
                raise ValueError("Repeated/incomplete/misclassified trial")
            seen.add(job["id"])
            request, manifest = job["spec"]["request"], job["result"]["manifest"]
            expected = ExperimentSpec(
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
            ).model_dump(mode="json")
            if (
                request != expected
                or manifest.get("native_input_adapter") != plan["adapter"]
                or job["spec"]["checkpoints"]["occupancy_lidar"] != plan["checkpoint_sha256"]
                or len(manifest["frames"]) != 20
            ):
                raise ValueError("Actual trial differs from frozen protocol")
            attrs = manifest["sensor_specs"]["lidar"][1]
            if any(float(attrs[k]) != v for k, v in profile.items()):
                raise ValueError("Actual physical sensor attributes differ")
            input_digest, reference_digest = hashlib.sha256(), hashlib.sha256()
            evaluator, raw_hashes = BevEvaluator(), []
            for index, entry in enumerate(manifest["frames"]):
                name = f"frame_{index:04d}"
                if entry["id"] != name:
                    raise ValueError("Frame ordering changed")
                file = store.root() / job["id"] / "capture" / f"{name}.npz"
                raw_hashes.append(sha(file))
                with np.load(file, allow_pickle=False) as item:
                    x = lidar_features(item["feature_points"], item["feature_intensity"])
                    if not np.array_equal(x, item["x"]):
                        raise ValueError("Raw points do not reproduce features")
                    frame = {k: item[k] for k in ("x", "labels", "valid", "rotation", "translation")}
                frame.update(flow=np.zeros((2, 200, 200), np.float32), flow_valid=np.zeros((200, 200), bool))
                adjusted = apply([frame], plan["adapter"])[0]
                for key in ("x", "labels", "valid", "flow", "flow_valid", "rotation", "translation"):
                    input_digest.update(np.ascontiguousarray(adjusted[key]).tobytes())
                for key in ("labels", "valid", "rotation", "translation"):
                    reference_digest.update(np.ascontiguousarray(frame[key]).tobytes())
                pred = np.asarray(
                    json.loads(
                        (store.root() / job["id"] / f"predictions/occupancy_lidar/{index:04d}.json").read_text()
                    )["cells"]
                )
                if pred.size != 40000 or not np.isin(pred, [0, 1, 2]).all():
                    raise ValueError("Invalid original prediction")
                evaluator.add(frame, {"occupancy": pred.reshape(200, 200).astype(np.uint8), "flow": None})
            if (
                input_digest.hexdigest() != manifest["input_sha256"]
                or reference_digest.hexdigest() != manifest["reference_sha256"]
                or evaluator.report([])["confusion"]
                != job["result"]["models"]["occupancy_lidar"]["metrics"]["confusion"]
            ):
                raise ValueError("Original artifact/seal/metric mismatch")
            if common is not None and common != reference_digest.hexdigest():
                raise ValueError("Profiles have different reference/pose sequences")
            common = reference_digest.hexdigest()
            audited.append({**row, "raw_sha256": raw_hashes, "reference_sha256": common})
    return plan, audited


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preserve previous measurements; choose a new output")
    plan, captures = audit_captures(args.matrix)
    checkpoint = CurrentCheckpoint("occupancy_lidar", "cpu")
    if checkpoint.digest != plan["checkpoint_sha256"]:
        raise ValueError("Changed checkpoint")
    sources = [
        "scripts/build_native_occupancy_replay.py",
        "src/active_sensing/native_occupancy.py",
        "src/inference/bev.py",
        "src/inference/current.py",
        "src/inference/native_input.py",
        "legacy/streamlit_lab/tools/local/models.py",
        "src/evaluation/bev.py",
        "src/models/experiments.py",
    ]
    source_hashes = {p: sha(p) for p in sources}
    args.output.mkdir(parents=True)
    (args.output / "artifacts").mkdir()
    data = {
        "kind": "native_occupancy_measured_replay_v1",
        "status": "incomplete",
        "observation_abi": ABI,
        "profiles": PROFILES,
        "baseline_action": BASELINE,
        "reward": REWARD,
        "deadline_ms": 500,
        "timing_scope": "cpu_wall_feature_preprocessing_and_inference",
        "checkpoint_sha256": checkpoint.digest,
        "adapter": plan["adapter"],
        "capture_plan_sha256": sha(args.matrix / "capture-plan.json"),
        "producer_sources": source_hashes,
        "hardware": platform.platform(),
        "torch": checkpoint.torch.__version__,
        "cpu_threads": checkpoint.torch.get_num_threads(),
        "deployment_ready": False,
        "episodes": [],
        "limits": plan["limits"]
        + [
            "Native reference covers observed semantic LiDAR cells only; no full 3D semantic GT",
            "Offline recorded action matrix, no online switching dynamics or sensor power measurement",
            "500ms research cadence is not an ADAS safety deadline",
            "CPU timing includes features/model, excludes file IO, simulator and agent decision",
        ],
    }

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    try:
        for episode in plan["episodes"]:
            output = {**episode, "steps": []}
            trials = sorted([r for r in captures if r["episode"] == episode["id"]], key=lambda r: r["action"])
            for index in range(20):
                step = {"frame": index, "outcomes": [None] * 12}
                for action in np.roll(np.arange(12), index % 12):
                    action = int(action)
                    trial = trials[action]
                    raw = store.root() / trial["job_id"] / "capture" / f"frame_{index:04d}.npz"
                    if sha(raw) != trial["raw_sha256"][index]:
                        raise ValueError("Raw capture changed after audit")
                    with np.load(raw, allow_pickle=False) as item:
                        points, intensity = item["feature_points"], item["feature_intensity"]
                        reference = {k: item[k] for k in ("labels", "valid", "rotation", "translation")}
                    if not checkpoint.warmed:
                        checkpoint.predict([{"x": lidar_features(points, intensity)}], 0)
                    start = time.perf_counter()
                    x = lidar_features(points, intensity)
                    x[3] *= plan["adapter"]["gain"]
                    pred = checkpoint.predict([{"x": x}], 0)["occupancy"]
                    elapsed = (time.perf_counter() - start) * 1000
                    labels, valid = reference["labels"], reference["valid"]
                    cm = np.bincount((labels[valid].astype(int) * 3 + pred[valid]).ravel(), minlength=9).reshape(3, 3)
                    ref_hash = hashlib.sha256(
                        b"".join(reference[k].tobytes() for k in ("labels", "valid", "rotation", "translation"))
                    ).hexdigest()
                    if "reference_sha256" in step and step["reference_sha256"] != ref_hash:
                        raise ValueError("Unpaired per-frame reference")
                    step["reference_sha256"] = ref_hash
                    artifact = f"artifacts/{episode['id']}-{index:02d}-{action:02d}.npz"
                    np.savez_compressed(
                        args.output / artifact,
                        x=x[:4],
                        points=points,
                        intensity=intensity,
                        prediction=pred,
                        **reference,
                    )
                    step["outcomes"][action] = {
                        "observation": sensor_context(points, intensity),
                        "confusion": cm.tolist(),
                        "latency_ms": elapsed,
                        "artifact": artifact,
                        "artifact_sha256": sha(args.output / artifact),
                        "input_sha256": hashlib.sha256(x[:4].tobytes()).hexdigest(),
                        "job_id": trial["job_id"],
                        "capture_sha256": trial["raw_sha256"][index],
                    }
                output["steps"].append(step)
                write_sealed(
                    args.output / "measurement-progress.json",
                    {
                        "status": "measuring",
                        "completed_outcomes": (len(data["episodes"]) * 20 + index + 1) * 12,
                        "total": 960,
                        "research_training_admitted": False,
                    },
                )
                print(json.dumps({"episode": episode["id"], "frame": index, "actions": 12}), flush=True)
            data["episodes"].append(output)
        if source_hashes != {p: sha(p) for p in sources}:
            raise ValueError("Producer source changed during measurement")
        data["status"] = "measured"
        path = args.output / "replay.json"
        write_sealed(path, data)
        load_dataset(path)  # Separate contract verification, including all saved arrays and split pose overlap.
        write_sealed(
            args.output / "audit.json",
            {
                "kind": "native_observed_replay_audit_v1",
                "status": "passed_research_audit",
                "dataset_sha256": sha(path),
                "captures": captures,
                "capture_plan_sha256": data["capture_plan_sha256"],
                "profiles": 12,
                "frames": 80,
                "outcomes": 960,
                "research_training_admitted": True,
                "deployment_ready": False,
                "limits": data["limits"],
            },
        )
        print(json.dumps({"research_training_admitted": True, "deployment_ready": False, "outcomes": 960}))
    except BaseException as exc:
        write_sealed(
            args.output / "measurement-progress.json",
            {"status": "incomplete", "error_type": type(exc).__name__, "research_training_admitted": False},
        )
        raise


if __name__ == "__main__":
    main()
