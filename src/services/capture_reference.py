"""Validated reference cells and optional calibrated geometry shared by capture viewers."""

import json
import math
from zipfile import BadZipFile

import numpy as np


def read_reference(path):
    actors = []
    try:
        metadata = json.loads(path.with_suffix(".json").read_text())
        geometry = metadata["boxes"]
        if not isinstance(geometry, list) or len(geometry) > 80:
            raise ValueError("Invalid actor catalog")
        for actor in geometry:
            item = {key: actor[key] for key in ("id", "x", "y", "l", "w", "h", "yaw")}
            if (
                type(item["id"]) is not int
                or item["id"] < 0
                or any(
                    type(item[key]) not in (int, float) or not math.isfinite(item[key])
                    for key in ("x", "y", "l", "w", "h", "yaw")
                )
                or any(not 0 < item[key] <= 100 for key in ("l", "w", "h"))
                or any(abs(item[key]) > 1000 for key in ("x", "y"))
            ):
                raise ValueError("Invalid actor geometry")
            projection = actor.get("camera_box_uv")
            if projection is not None:
                if (
                    not isinstance(projection, list)
                    or len(projection) != 4
                    or any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in projection)
                    or projection[2] <= projection[0]
                    or projection[3] <= projection[1]
                ):
                    raise ValueError("Invalid actor camera projection")
            recorded = actor.get("camera_projection_status") == "geometry_recorded"
            if recorded:
                from src.simulation.camera_projection import camera_box

                if metadata["camera_frame_id"] != metadata["simulation_frame_id"]:
                    raise ValueError("Camera/reference frame mismatch")
                local = np.linalg.inv(np.asarray(metadata["ego_matrix"], dtype=float)) @ np.asarray(
                    actor["world_box_matrix"], dtype=float
                )
                if not np.allclose([item["x"], item["y"]], [local[0, 3], -local[1, 3]], rtol=0, atol=1e-6):
                    raise ValueError("Camera/BEV actor pose mismatch")
                expected = camera_box(
                    actor["world_box_matrix"],
                    (item["l"] / 2, item["w"] / 2, item["h"] / 2),
                    metadata["camera_matrix"],
                    tuple(metadata["camera_size"]),
                    metadata["camera_fov"],
                )
                if (expected is None) != (projection is None) or (
                    expected is not None and not np.allclose(expected, projection, rtol=0, atol=1e-9)
                ):
                    raise ValueError("Camera projection differs from recorded geometry")
            item["camera_box_uv"] = projection
            item["camera_projection_status"] = "geometry_recorded" if recorded else "unavailable"
            actors.append(item)
        if len({item["id"] for item in actors}) != len(actors):
            raise ValueError("Duplicate actor IDs")
    except (OSError, ValueError, KeyError, TypeError):
        actors = []  # Optional geometry must not replace or invent reference cells.
    try:
        with np.load(path, allow_pickle=False) as data:
            labels, valid = data["labels"], data["valid"]
            if (
                labels.shape != (200, 200)
                or valid.shape != (200, 200)
                or valid.dtype != np.bool_
                or not np.isin(labels, [0, 1, 2]).all()
            ):
                raise ValueError("Invalid reference grid")
            return {
                "actors": actors,
                "cells": labels.reshape(-1).tolist(),
                "valid": valid.reshape(-1).tolist(),
                "kind": "reference",
                "label_policy": "semantic-LiDAR observed cells; static-height proxy + visible actor footprints",
            }
    except FileNotFoundError as exc:
        raise FileNotFoundError("Reference was not preserved for this capture") from exc
    except (OSError, ValueError, KeyError, EOFError, BadZipFile) as exc:
        raise ValueError("Native reference failed integrity validation") from exc
