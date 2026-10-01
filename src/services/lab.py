"""Read-only adapters for the versioned lab exports. No CUDA or MATLAB imports."""

import csv
import json
from functools import lru_cache
from pathlib import Path

from src.config import get_settings

DETECTORS = {
    "official_lidar": ("exports/L3E/pred_lidar_only_ego.csv", ["lidar"], "official"),
    "official_cl": ("exports/L3E/pred_lidar_camera_ego.csv", ["camera", "lidar"], "official"),
    "our_lidar": ("exports/L3E/pred_our_lidar_ego.csv", ["lidar"], "own"),
    "our_cl": ("exports/L3E/pred_our_bevfusion_ego.csv", ["camera", "lidar"], "own"),
    "crn": ("exports/L3E/pred_camera_radar_ego.csv", ["camera", "radar"], "official"),
    "fused": ("fusion/unified/unified_pretrained_ego.csv", ["camera", "lidar", "radar"], "official"),
    "fused_ours": ("fusion/unified/unified_ours_ego.csv", ["camera", "lidar", "radar"], "mixed"),
}
COORDINATES = {
    "frame": "ego",
    "x": "forward",
    "y": "left",
    "z": "up",
    "length_unit": "m",
    "yaw_unit": "rad",
    "yaw_direction": "CCW",
}
CAMERAS = ("CAM_FRONT", "CAM_FRONT_LEFT", "CAM_FRONT_RIGHT", "CAM_BACK", "CAM_BACK_LEFT", "CAM_BACK_RIGHT")


@lru_cache(maxsize=32)
def read_csv(path: Path, modified: int):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def csv_rows(path: Path):
    return read_csv(path, path.stat().st_mtime_ns)


@lru_cache(maxsize=16)
def read_json(path: Path, modified: int):
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream)


def json_data(path: Path):
    return read_json(path, path.stat().st_mtime_ns)


def frames():
    rows = csv_rows(get_settings().lab_data_root / "exports/L3E/samples.csv")
    return [
        {
            "sample_token": r["sample_token"],
            "sample_idx": int(r["sample_idx"]),
            "scene": r["scene"],
            "timestamp_s": float(r["timestamp_s"]),
            "split": "mini_val",
        }
        for r in rows
    ]


def frame(token: str):
    return next((item for item in frames() if item["sample_token"] == token), None)


def models():
    root = get_settings().lab_data_root
    return [
        {
            "id": name,
            "sensors": sensors,
            "origin": origin,
            "mode": "precomputed",
            "available": (root / rel).is_file(),
            "split": "mini_val",
            "contaminated": origin in {"official", "mixed"},
            "fusion_type": "object_level_late_fusion" if name.startswith("fused") else None,
        }
        for name, (rel, sensors, origin) in DETECTORS.items()
    ]


def detections(token: str, model: str, threshold: float):
    item = frame(token)
    if item is None:
        raise KeyError(token)
    rel = DETECTORS[model][0]
    rows = csv_rows(get_settings().lab_data_root / rel)
    boxes = []
    for row in rows:
        if int(row["sample_idx"]) != item["sample_idx"] or float(row["score"]) < threshold:
            continue
        boxes.append(
            {
                "class_name": row["class"],
                **{key: float(row[key]) for key in ("x", "y", "z", "w", "l", "h", "yaw", "vx", "vy", "score")},
            }
        )
    return {"frame": item, "model": model, "mode": "precomputed", "coordinates": COORDINATES, "boxes": boxes}


def camera_path(token: str, channel: str):
    root = get_settings().nusc_root.resolve()
    table = json_data(root / "v1.0-mini/sample_data.json")
    record = next(
        (
            r
            for r in table
            if r["sample_token"] == token and r["is_key_frame"] and Path(r["filename"]).parts[-2] == channel
        ),
        None,
    )
    if record is None:
        raise KeyError(token)
    path = (root / record["filename"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Unsafe dataset path")
    return path


def camera_cache_path(token: str, channel: str) -> Path:
    cache_root = get_settings().resolved_camera_cache_dir.resolve()
    return cache_root / f"{token}_{channel}.jpg"


def get_cached_camera(token: str, channel: str) -> bytes | None:
    path = camera_cache_path(token, channel)
    if path.is_file():
        return path.read_bytes()
    return None


def save_cached_camera(token: str, channel: str, data: bytes) -> None:
    try:
        path = camera_cache_path(token, channel)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(f".tmp.{path.suffix}")
        temp_path.write_bytes(data)
        temp_path.replace(path)
    except OSError:
        pass

