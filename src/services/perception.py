"""Frame-aligned, precomputed perception outputs. No inference in HTTP requests."""

import math
import re

from src.services import lab

TASKS = ("seg3d", "occupancy", "flow")


def artifact_path(token: str, task: str):
    if lab.frame(token) is None:
        raise KeyError(token)
    if task not in (*TASKS, "radar"):
        raise ValueError("Unknown perception task")
    return lab.get_settings().lab_data_root / "cache/perception" / task / f"{token}.json"


def task_catalog():
    frames = lab.frames()
    root = lab.get_settings().lab_data_root / "cache/perception"
    return {
        "items": [
            {
                "id": task,
                "frame_count": sum((root / task / f"{f['sample_token']}.json").is_file() for f in frames),
                "total_frames": len(frames),
            }
            for task in (*TASKS, "radar")
        ]
    }


def frame_output(token: str, task: str):
    payload = lab.json_data(artifact_path(token, task))
    if payload.get("sample_token") != token or payload.get("task") != task:
        raise ValueError("Artifact does not match the selected frame/task")
    axes = {"frame": "ego", "x": "forward", "y": "left", "z": "up", "length_unit": "m"}
    if any(payload.get("coordinates", {}).get(key) != value for key, value in axes.items()):
        raise ValueError("Artifact must use ego coordinates")
    if not isinstance(payload.get("source"), str) or not payload["source"]:
        raise ValueError("Artifact provenance missing")
    if not isinstance(payload.get("model"), str) or not payload["model"]:
        raise ValueError("Artifact model missing")
    if (
        not isinstance(payload.get("sensors"), list)
        or not payload["sensors"]
        or any(s not in {"camera", "lidar", "radar"} for s in payload["sensors"])
    ):
        raise ValueError("Artifact input sensors missing")
    if task == "seg3d":
        classes = payload.get("classes", [])
        if any(
            not isinstance(c.get("id"), int)
            or not isinstance(c.get("name"), str)
            or not re.fullmatch(r"#[0-9a-fA-F]{6}", c.get("color", ""))
            for c in classes
        ):
            raise ValueError("Invalid semantic classes")
        labels = {c["id"] for c in classes}
        if len(labels) != len(classes):
            raise ValueError("Duplicate semantic classes")
        if not labels or payload.get("kind") not in {"prediction", "ground_truth"}:
            raise ValueError("Seg3D needs classes and an explicit prediction/ground_truth kind")
        rows = payload.get("points", [])
        if not rows or any(len(p) != 4 or p[3] not in labels or not all(math.isfinite(x) for x in p) for p in rows):
            raise ValueError("Invalid segmented points")
    elif task == "radar":
        rows = payload.get("points", [])
        if any(len(p) != 5 or not all(math.isfinite(x) for x in p) for p in rows):
            raise ValueError("Invalid radar positions/velocities")
    elif task == "occupancy":
        shape = payload.get("shape", [])
        cells = payload.get("cells", [])
        if shape != [200, 200] or len(cells) != 40000 or any(c not in (0, 1, 2) for c in cells):
            raise ValueError("Invalid occupancy grid")
        if payload.get("resolution_m") != 0.5 or payload.get("extent_m") != 50:
            raise ValueError("Unsupported occupancy geometry")
    elif task == "flow":
        rows = payload.get("vectors", [])
        if any(len(v) != 4 or not all(math.isfinite(x) for x in v) for v in rows):
            raise ValueError("Invalid flow vectors")
    return payload
