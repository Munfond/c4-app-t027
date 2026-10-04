"""Export real Radar, BEV occupancy and temporal flow for the web timeline.

Run offline with the existing lab torch runtime; deploy cache/perception with lab data.
Does not generate Seg3D labels or retrain any model.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nusc-root", type=Path, required=True)
    parser.add_argument("--lab-root", type=Path, default=REPO / "data/lab")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--tasks", nargs="+", choices=["radar", "occupancy", "flow"], default=["radar", "occupancy", "flow"]
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    os.environ["NUSC_ROOT"] = str(args.nusc_root.resolve())
    os.environ["LAB_DATA_ROOT"] = str(args.lab_root.resolve())
    sys.path.insert(0, str(REPO / "legacy/streamlit_lab/tools/local"))
    from nuscenes_local import NuScenesMini, qR, read_pcd

    from src.services.lab import COORDINATES, frames

    ds = NuScenesMini()
    target = args.lab_root / "cache/perception"
    all_frames = frames()
    selected = all_frames[: args.limit] if args.limit else all_frames
    models, checkpoints = {}, {}
    if {"occupancy", "flow"} & set(args.tasks):
        import torch

        from models import load_flow, load_occupancy, warp_history

        torch.set_num_threads(4)
        for task, rel, loader in [
            ("occupancy", "models/occupancy/our_occupancy.pth", load_occupancy),
            ("flow", "models/temporal_flow/our_flow.pth", load_flow),
        ]:
            if task in args.tasks:
                path = args.lab_root / rel
                models[task], checkpoints[task] = loader(str(path))
                checkpoints[task]["provenance"] = f"{rel} · sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    inputs = {}

    def bev(token):
        if token not in inputs:
            inputs[token] = torch.from_numpy(ds.bev_inputs(token))
        return inputs[token]

    for index, frame in enumerate(selected):
        token = frame["sample_token"]
        for task in args.tasks:
            path = target / task / f"{token}.json"
            if path.is_file() and not args.overwrite:
                continue
            payload = {"schema_version": "1.0", "sample_token": token, "task": task, "coordinates": COORDINATES}
            if task == "radar":
                # Radar sensors have their own acquisition ego poses. Align through world
                # coordinates into this frame's LiDAR ego pose, rather than mixing timestamps.
                ref_rotation, ref_t = ds.pose(token)
                rows = []
                for channel in (
                    "RADAR_FRONT",
                    "RADAR_FRONT_LEFT",
                    "RADAR_FRONT_RIGHT",
                    "RADAR_BACK_LEFT",
                    "RADAR_BACK_RIGHT",
                ):
                    record = ds.key[(token, channel)]
                    a = read_pcd(os.path.join(ds.root, record["filename"]))
                    a = a[(a["invalid_state"] == 0) & (a["ambig_state"] == 3)]
                    calibration, pose = ds.cs[record["calibrated_sensor_token"]], ds.ego[record["ego_pose_token"]]
                    sensor_rotation, acquisition_rotation = qR(calibration["rotation"]), qR(pose["rotation"])
                    xyz = np.stack([a["x"], a["y"], a["z"]], axis=1)
                    world = (xyz @ sensor_rotation.T + calibration["translation"]) @ acquisition_rotation.T + pose[
                        "translation"
                    ]
                    ego = (world - ref_t) @ ref_rotation
                    velocity = (
                        np.stack([a["vx_comp"], a["vy_comp"], np.zeros(len(a))], axis=1)
                        @ sensor_rotation.T
                        @ acquisition_rotation.T
                        @ ref_rotation
                    )
                    points = np.column_stack([ego, velocity[:, :2]])
                    points = points[np.isfinite(points).all(axis=1) & (np.linalg.norm(ego[:, :2], axis=1) <= 65)]
                    rows.extend(np.round(points, 3).tolist())
                payload.update(
                    points=rows,
                    source="nuScenes · 5 radar keyframes · ego-aligned",
                    sensors=["radar"],
                    model="Measured radar",
                )
            elif task == "occupancy":
                ck = checkpoints[task]
                with torch.inference_mode():
                    cells = models[task](bev(token)[ck["channels"]][None])[0].argmax(0).numpy()
                payload.update(
                    cells=cells.reshape(-1).tolist(),
                    shape=[200, 200],
                    resolution_m=0.5,
                    extent_m=50,
                    model="BEV Occupancy U-Net",
                    sensors=["lidar", "radar"],
                    source=ck["provenance"],
                    limitations=[
                        "BEV 2D; not dense 3D occupancy",
                        "Static training labels use pseudo-GT",
                        "Class free includes unobserved cells",
                    ],
                )
            else:
                ck = checkpoints[task]
                history = [bev(token)]
                for prev, warp_matrix, warp_offset in ds.history(token, ck["T"] - 1):
                    history.append(warp_history(bev(prev), warp_matrix, warp_offset) if ck["warp"] else bev(prev))
                with torch.inference_mode():
                    output = models[task](torch.cat(history[::-1], 0)[None])[0].numpy()
                occupancy = output[:3].argmax(0)
                output[3:5] *= 10
                row, col = np.where(occupancy == 2)
                take = (row % 2 == 0) & (col % 2 == 0)
                row, col = row[take], col[take]
                vectors = np.column_stack(
                    [-50 + (row + 0.5) * 0.5, -50 + (col + 0.5) * 0.5, output[3, row, col], output[4, row, col]]
                )
                payload.update(
                    vectors=np.round(vectors, 3).tolist(),
                    model=f"Temporal U-Net · T{ck['T']}",
                    sensors=["lidar", "radar"],
                    source=ck["provenance"],
                    limitations=[
                        "Experimental learned flow; quality insufficient",
                        "Vectors sampled every 1m at predicted object cells",
                    ],
                    velocity_unit="m/s",
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8")
            temporary.replace(path)
        print(f"{index + 1}/{len(selected)} {frame['scene']} #{frame['sample_idx']}", flush=True)
        if len(inputs) > 12:
            inputs.clear()


if __name__ == "__main__":
    main()
