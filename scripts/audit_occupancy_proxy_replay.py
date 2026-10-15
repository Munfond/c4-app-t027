"""Read-back checks: split isolation, raw checksums, sampled inputs/labels/model outputs."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from legacy.streamlit_lab.tools.local.nuscenes_local import NuScenesMini  # noqa: E402
from src.active_sensing.occupancy_proxy import PROFILES, lidar_features, load_dataset  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.inference.current import CurrentCheckpoint  # noqa: E402


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    data = load_dataset(args.dataset)
    settings = get_settings()
    ds = NuScenesMini(str(settings.nusc_root))
    for name, expected in data["producer_sources"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or sha(path) != expected:
            raise ValueError("Producer source changed")
    for name, expected in data["raw_files"].items():
        path = (settings.nusc_root / name).resolve()
        if not path.is_relative_to(settings.nusc_root.resolve()) or sha(path) != expected:
            raise ValueError("Recorded raw input changed")
    # Global annotation tables are shared metadata; raw measurements must not cross policy splits.
    file_splits = {}
    for e in data["episodes"]:
        for step in e["steps"]:
            record = ds.key[(step["token"], "LIDAR_TOP")]
            records = [record]
            previous = record["prev"]
            for _ in range(10):
                if not previous:
                    break
                record = ds.sd[previous]
                records.append(record)
                previous = record["prev"]
            for name in [ds.key[(step["token"], "CAM_FRONT")]["filename"], *[r["filename"] for r in records]]:
                prior = file_splits.setdefault(name, e["split"])
                if prior != e["split"]:
                    raise ValueError("Raw/reference sweep shared across policy splits")
    model = CurrentCheckpoint("occupancy_lidar", "cpu")
    if model.digest != data["checkpoint_sha256"]:
        raise ValueError("Another checkpoint")
    sampled = 0
    for e in data["episodes"]:
        for step in [e["steps"][0], e["steps"][-1]]:
            token = step["token"]
            points, intensity = ds.keyframe_lidar(token)
            labels = ds.labels(token).astype(np.uint8)
            if hashlib.sha256(labels.tobytes()).hexdigest() != step["label_sha256"]:
                raise ValueError("Reconstructed proxy reference differs")
            seed = int(hashlib.sha256((token + ":27").encode()).hexdigest()[:8], 16)
            for action, keep in enumerate(PROFILES):
                features = lidar_features(points, intensity, keep, seed)
                if hashlib.sha256(features[:4].tobytes()).hexdigest() != step["outcomes"][action]["input_sha256"]:
                    raise ValueError("Reconstructed tensor differs")
                prediction = model.predict([{"x": features}], 0)["occupancy"]
                with np.load(
                    args.dataset.parent / step["outcomes"][action]["artifact"], allow_pickle=False
                ) as artifact:
                    if not np.array_equal(prediction, artifact["prediction"]):
                        raise ValueError("Reexecuted output differs")
                sampled += 1
    value = {
        "status": "passed_proxy_replay_audit",
        "dataset_sha256": sha(args.dataset),
        "raw_files_rehashed": len(data["raw_files"]),
        "frames": sum(len(e["steps"]) for e in data["episodes"]),
        "outcomes_recomputed": sampled,
        "no_raw_sweep_split_overlap": True,
        "scope": "occupancy proxy research only; not validated detection/real-driving safety",
    }
    path = args.dataset.parent / "audit.json"
    if path.exists():
        raise ValueError("Preserve prior audit")
    path.write_text(json.dumps(value, indent=2))
    path.with_suffix(".sha256").write_text(sha(path) + "\n")
    print(json.dumps(value), flush=True)


if __name__ == "__main__":
    main()
