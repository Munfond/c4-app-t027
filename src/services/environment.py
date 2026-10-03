"""Measured LiDAR surfaces in the same keyframe ego coordinates as detections.

These points are observations, not a complete map or a free-space prediction.
"""

import json

import numpy as np

from src.database import SessionLocal
from src.models.db_models import EnvironmentDB
from src.services import lab


def environment(token: str) -> dict:
    if lab.frame(token) is None:
        raise KeyError(token)

    # 1. Try DB first
    try:
        with SessionLocal() as session:
            record = session.query(EnvironmentDB).filter(EnvironmentDB.sample_token == token).first()
            if record and record.payload_json:
                return json.loads(record.payload_json)
    except Exception:
        pass

    # 2. Try file cache
    settings = lab.get_settings()
    cached = settings.lab_data_root / "cache/environment" / f"{token}.json"
    if cached.is_file():
        return lab.json_data(cached)
    return build_environment(token)


def build_environment(token: str) -> dict:
    root = lab.get_settings().nusc_root.resolve()
    records = lab.json_data(root / "v1.0-mini/sample_data.json")
    record = next(
        (
            r
            for r in records
            if r["sample_token"] == token and r["is_key_frame"] and "/LIDAR_TOP/" in r["filename"].replace("\\", "/")
        ),
        None,
    )
    if record is None:
        raise FileNotFoundError("LiDAR keyframe missing")
    path = (root / record["filename"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Unsafe dataset path")
    calibrations = lab.json_data(root / "v1.0-mini/calibrated_sensor.json")
    calibration = next(c for c in calibrations if c["token"] == record["calibrated_sensor_token"])
    rotation = np.asarray(calibration["rotation"], dtype=float)
    if rotation.shape != (4,) or not np.isfinite(rotation).all() or np.linalg.norm(rotation) < 1e-6:
        raise ValueError("Invalid calibration")
    w, x, y, z = rotation / np.linalg.norm(rotation)
    matrix = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )
    raw = np.fromfile(path, dtype="<f4").reshape(-1, 5)[:, :3]
    points = raw @ matrix.T + np.asarray(calibration["translation"])
    # Keep road as well as elevated surfaces; height colouring separates them.
    keep = np.isfinite(points).all(axis=1) & (np.linalg.norm(points[:, :2], axis=1) <= 65)
    keep &= (points[:, 2] >= -2) & (points[:, 2] <= 12)
    points = points[keep]
    _, indexes = np.unique(np.floor(points / 0.25), axis=0, return_index=True)
    points = points[np.sort(indexes)]
    if len(points) > 24000:
        points = points[np.linspace(0, len(points) - 1, 24000, dtype=int)]
    return {
        "sample_token": token,
        "coordinates": lab.COORDINATES,
        "source": "LIDAR_TOP keyframe",
        "radius_m": 65,
        "voxel_m": 0.25,
        "points": np.round(points, 2).tolist(),
    }
