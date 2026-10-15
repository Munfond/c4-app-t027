"""Paired diagnostic of a sealed adapter; never fit on evaluation labels or run CARLA."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from src.evaluation.bev import BevEvaluator
from src.inference.current import CurrentCheckpoint
from src.inference.native_input import apply, fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="Completed capture directory containing manifest.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; preserve earlier evidence and use a new path")
    manifest = json.loads((args.capture / "manifest.json").read_text())
    if manifest.get("source") != "carla" or len(manifest["frames"]) != manifest["scenario"]["frames"]:
        parser.error("Only complete native CARLA captures are supported")
    frozen = fingerprint("intensity_mean_experimental")
    frames, hashes = [], {}
    for index, item in enumerate(manifest["frames"]):
        name = f"frame_{index:04d}"
        if item["id"] != name:
            parser.error("Invalid capture catalog")
        path = args.capture / f"{name}.npz"
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        with np.load(path, allow_pickle=False) as data:
            frame = {key: data[key] for key in ("x", "labels", "valid")}
        if (
            frame["x"].shape != (7, 200, 200)
            or not np.isfinite(frame["x"]).all()
            or frame["labels"].shape != (200, 200)
            or not np.isin(frame["labels"], [0, 1, 2]).all()
            or frame["valid"].shape != (200, 200)
            or frame["valid"].dtype != bool
        ):
            parser.error("Invalid native input/reference tensor")
        frame.update(flow=np.zeros((2, 200, 200), np.float32), flow_valid=np.zeros((200, 200), bool))
        frames.append(frame)
    results = {}
    for name, inputs in (("raw", frames), ("intensity_mean_experimental", apply(frames, frozen))):
        model = CurrentCheckpoint("occupancy_lidar")
        evaluator = BevEvaluator()
        for index, frame in enumerate(inputs):
            evaluator.add(frame, model.predict(inputs, index))
        results[name] = evaluator.report(model.timing)
    report = {
        "kind": "paired_native_input_adapter_diagnostic",
        "scenario": manifest["scenario"],
        "adapter": frozen,
        "raw_npz_sha256": hashes,
        "results": results,
        "native_rl_admitted": False,
        "limitations": [
            "Small same-map diagnostic only; no real-world safety claim",
            "RGB weather changes are not calibrated LiDAR weather corruption",
            "Reference uses observed semantic LiDAR and actor-footprint proxies",
            "No adapter fitting or parameter search on this evaluation",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".sha256").write_text(hashlib.sha256(args.output.read_bytes()).hexdigest() + "\n")
    print(
        json.dumps(
            {
                key: {"occupied_iou": val["occupied_iou"], "object_recall": val["object_recall"]}
                for key, val in results.items()
            }
        )
    )


if __name__ == "__main__":
    main()
