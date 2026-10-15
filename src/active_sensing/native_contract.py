"""Pure NumPy native sensor/evidence contract; web readers do not import Gym or Torch."""

import hashlib
import json
from pathlib import Path

import numpy as np

ABI = "native-current-profile-next-frame-v1"
PROFILES = [{"channels": c, "points_per_second": r} for c in (16, 32, 64) for r in (150000, 300000, 450000, 600000)]
BASELINE = 7


def sensor_context(points, intensity):
    points, intensity = np.asarray(points), np.asarray(intensity)
    if points.ndim != 2 or points.shape[1] != 3 or intensity.shape != (len(points),):
        raise ValueError("Invalid raw sensor context")
    if not len(points) or not np.isfinite(points).all() or not np.isfinite(intensity).all():
        raise ValueError("Missing or nonfinite raw sensor context")
    if (intensity < 0).any() or (intensity > 255).any() or (np.abs(points) > 2000).any():
        raise ValueError("Raw sensor values outside recorded domain")
    radius = np.linalg.norm(points[:, :2], axis=1)
    near = (points[:, 0] > 3.7) & (points[:, 0] < 20) & (np.abs(points[:, 1]) < 5)
    obstacle = (points[:, 2] > 0.3) & (points[:, 2] < 3)
    return [
        min(float(np.log1p(len(points)) / np.log1p(100000)), 1),
        float((near & obstacle).mean()),
        min(float(radius.mean() / 100), 1),
        min(float(radius.std() / 50), 1),
        float(obstacle.mean()),
        float(np.clip(intensity.mean() / 255, 0, 1)),
    ]


def quality(confusion, *, max_cells=40000):
    cm = np.asarray(confusion)
    if cm.shape != (3, 3) or not np.issubdtype(cm.dtype, np.integer) or (cm < 0).any() or not 0 < cm.sum() <= max_cells:
        raise ValueError("Require observed-cell 200x200 confusion")
    tp = int(cm[1:, 1:].sum())
    occupied_union = int(cm[1:, :].sum() + cm[:, 1:].sum() - tp)
    object_union = int(cm[2].sum() + cm[:, 2].sum() - cm[2, 2])
    occupied = tp / occupied_union if occupied_union else None
    objects = int(cm[2, 2]) / object_union if object_union else None
    values = [v for v in (occupied, objects) if v is not None]
    return {"occupied_iou": occupied, "object_iou": objects, "score": float(np.mean(values)) if values else 0.0}


def read_sealed(path):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != path.with_suffix(".sha256").read_text().strip():
        raise ValueError("Changed sealed research evidence")
    return json.loads(path.read_text()), digest
