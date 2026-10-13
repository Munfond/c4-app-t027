"""CARLA geometry reference projection, not a pixel detector or occlusion test.

UE camera coordinates are x-forward/y-right/z-up. CARLA's documented pinhole
projection uses image coordinates (y, -z, x). Store normalized image bounds.
"""

from itertools import product

import numpy as np


def camera_box(world_box, extent, camera_world, size, fov):
    box, camera = np.asarray(world_box, dtype=float), np.asarray(camera_world, dtype=float)
    extent = np.asarray(extent, dtype=float)
    if (
        box.shape != (4, 4)
        or camera.shape != (4, 4)
        or extent.shape != (3,)
        or not np.isfinite(box).all()
        or not np.isfinite(camera).all()
        or not np.isfinite(extent).all()
        or (extent <= 0).any()
        or len(size) != 2
        or any(type(v) is not int or v <= 0 for v in size)
        or not np.isfinite(fov)
        or not 0 < fov < 180
    ):
        raise ValueError("Invalid reference projection geometry")
    vertices = np.column_stack((np.asarray(list(product((-1, 1), repeat=3))) * extent, np.ones(8)))
    local = vertices @ (np.linalg.inv(camera) @ box).T
    # Avoid inventing an envelope for vertices crossing the camera near plane.
    if (local[:, 0] <= 0.1).any():
        return None
    width, height = size
    focal = width / (2 * np.tan(np.radians(fov) / 2))
    u = 0.5 + focal * local[:, 1] / local[:, 0] / width
    v = 0.5 - focal * local[:, 2] / local[:, 0] / height
    if u.max() <= 0 or u.min() >= 1 or v.max() <= 0 or v.min() >= 1:
        return None
    result = np.clip([u.min(), v.min(), u.max(), v.max()], 0, 1).tolist()
    return result if result[2] > result[0] and result[3] > result[1] else None
