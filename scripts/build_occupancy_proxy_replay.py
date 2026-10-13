"""Measure point-thinning profiles on nuScenes; proxy research labels, no GPU cost."""

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from legacy.streamlit_lab.tools.local.nuscenes_local import MINI_TRAIN, MINI_VAL, NuScenesMini  # noqa: E402
from src.active_sensing.occupancy_proxy import OBSERVATION_ABI, PROFILES, lidar_features  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.inference.current import CurrentCheckpoint  # noqa: E402


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit-per-scene", type=int, default=0, help="0=all; pilot must report sampling limit")
    args = parser.parse_args()
    if args.output.exists() or args.limit_per_scene < 0:
        raise ValueError("Use new output, nonnegative sample limit")
    args.output.mkdir(parents=True)
    (args.output / "artifacts").mkdir()
    settings = get_settings()
    ds = NuScenesMini(str(settings.nusc_root))
    checkpoint = CurrentCheckpoint("occupancy_lidar", "cpu")
    sources = [
        "scripts/build_occupancy_proxy_replay.py",
        "src/active_sensing/occupancy_proxy.py",
        "legacy/streamlit_lab/tools/local/nuscenes_local.py",
        "src/inference/current.py",
        "legacy/streamlit_lab/tools/local/models.py",
    ]
    source_hashes = {name: sha(ROOT / name) for name in sources}
    data = {
        "kind": "measured_occupancy_proxy_replay",
        "status": "incomplete",
        "profiles": list(PROFILES),
        "observation_abi": OBSERVATION_ABI,
        "label_policy": "lidar-persistence-static-proxy+annotated-object-footprints",
        "timing_scope": "cpu_wall_point_preprocessing_and_inference",
        "deadline_ms": 500,
        "checkpoint_sha256": checkpoint.digest,
        "producer_sources": source_hashes,
        "hardware": platform.platform(),
        "torch": checkpoint.torch.__version__,
        "device": "cpu",
        "cpu_threads": checkpoint.torch.get_num_threads(),
        "limit_per_scene": args.limit_per_scene,
        "raw_files": {},
        "episodes": [],
        "limitations": [
            "Static labels use LiDAR persistence proxy; free includes unobserved cells",
            "Object footprint labels are annotations, not full 3D occupancy ground truth",
            "500ms deadline follows recorded keyframe cadence; not an ADAS safety deadline",
            "Recorded full LiDAR is acquired before thinning; no physical sensor power/capture savings",
            "Fixed-grid U-Net compute may not decrease with fewer points; no improvement is a valid result",
            "Quality labels and counterfactual outcomes excluded from PPO observations",
            "Policy scenes isolated; checkpoint pretraining overlap not independently audited",
            "Not online CARLA, no weather robustness or failed-sensor test",
        ],
    }
    # Freeze metadata used by pose, calibration, reference and scene membership.
    for path in sorted((settings.nusc_root / "v1.0-mini").glob("*.json")):
        data["raw_files"][str(path.relative_to(settings.nusc_root))] = sha(path)
    progress = args.output / "progress.json"

    def save_progress():
        progress.write_text(
            json.dumps(
                {
                    "scenes": len(data["episodes"]),
                    "frames": sum(len(e["steps"]) for e in data["episodes"]),
                    "status": data["status"],
                }
            )
        )

    # No selection based on test results: deterministic first6 train / remaining2 validation / official mini-val test.
    for scene in [*MINI_TRAIN, *MINI_VAL]:
        split = "test" if scene in MINI_VAL else ("train" if scene in MINI_TRAIN[:6] else "validation")
        tokens = [t for t, _, name in ds.order if name == scene]
        if args.limit_per_scene:
            tokens = tokens[: args.limit_per_scene]
        episode = {"scene": scene, "split": split, "steps": []}
        data["episodes"].append(episode)
        previous_pose, previous_time = None, None
        for token in tokens:
            sample = ds.sample[token]
            timestamp = sample["timestamp"] / 1e6
            points, intensity = ds.keyframe_lidar(token)
            if not np.isfinite(points).all() or not np.isfinite(intensity).all() or (np.abs(points) > 2000).any():
                raise ValueError("Invalid sensor measurements")
            _, pose = ds.pose(token)
            speed_known = previous_pose is not None and timestamp > previous_time
            speed = float(np.linalg.norm(pose - previous_pose) / (timestamp - previous_time)) if speed_known else 0.0
            previous_pose, previous_time = pose, timestamp
            camera = Path(ds.image_path(token, "CAM_FRONT"))
            with Image.open(camera) as img:
                grey = np.asarray(img.convert("L").resize((64, 36)), dtype=np.float32) / 255
            nearby = (
                (points[:, 0] > 3.7)
                & (points[:, 0] < 20)
                & (np.abs(points[:, 1]) < 5)
                & (points[:, 2] > 0.3)
                & (points[:, 2] < 3)
            )
            observation = [
                min(float(np.log1p(len(points)) / np.log1p(100000)), 1),
                float(nearby.mean()) if len(points) else 0.0,
                min(speed / 40, 1),
                float(speed_known),
                float(grey.mean()),
                min(float(grey.std() * 2), 1),
            ]
            labels = ds.labels(token).astype(np.uint8)
            assert labels.shape == (200, 200) and np.isin(labels, [0, 1, 2]).all()
            step = {
                "token": token,
                "timestamp": timestamp,
                "observation": observation,
                "label_sha256": hashlib.sha256(labels.tobytes()).hexdigest(),
                "outcomes": [None] * 3,
            }
            seed = int(hashlib.sha256((token + ":27").encode()).hexdigest()[:8], 16)
            # Warm independently of timing. Fixed-grid shape is identical for all profiles.
            full = lidar_features(points, intensity)
            if not checkpoint.warmed:
                checkpoint.predict([{"x": full}], 0)
            for action in np.roll(np.arange(3), len(episode["steps"]) % 3):
                action = int(action)
                start = time.perf_counter()
                x = lidar_features(points, intensity, PROFILES[action], seed)
                prediction = checkpoint.predict([{"x": x}], 0)["occupancy"]
                elapsed = (time.perf_counter() - start) * 1000
                cm = np.bincount((labels.astype(int) * 3 + prediction).ravel(), minlength=9).reshape(3, 3)
                artifact = f"artifacts/{token}-{action}.npz"
                np.savez_compressed(args.output / artifact, x=x[:4], labels=labels, prediction=prediction)
                step["outcomes"][action] = {
                    "confusion": cm.tolist(),
                    "latency_ms": elapsed,
                    "artifact": artifact,
                    "artifact_sha256": sha(args.output / artifact),
                    "input_sha256": hashlib.sha256(x[:4].tobytes()).hexdigest(),
                }
            episode["steps"].append(step)
            # Trace raw keyframe and all sweeps used by the reference labels, plus context camera.
            record = ds.key[(token, "LIDAR_TOP")]
            records = [record]
            previous = record["prev"]
            for _ in range(10):
                if not previous:
                    break
                record = ds.sd[previous]
                records.append(record)
                previous = record["prev"]
            for path in [camera, *[settings.nusc_root / r["filename"] for r in records]]:
                relative = str(path.relative_to(settings.nusc_root))
                if relative not in data["raw_files"]:
                    data["raw_files"][relative] = sha(path)
            save_progress()
        print(json.dumps({"scene": scene, "split": split, "frames": len(episode["steps"])}), flush=True)
    if source_hashes != {name: sha(ROOT / name) for name in sources}:
        raise ValueError("Producer source changed during collection")
    data["status"] = "completed"
    save_progress()
    path = args.output / "replay.json"
    path.write_text(json.dumps(data, indent=2))
    path.with_suffix(".seal.json").write_text(json.dumps({"dataset_sha256": sha(path)}, indent=2))
    print("Completed measured proxy matrix", path, flush=True)


if __name__ == "__main__":
    main()
