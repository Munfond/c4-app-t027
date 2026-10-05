"""Exact Stage-F LiDAR features and geometry for the current 200x200 checkpoints."""

import numpy as np

GRID = 200
RESOLUTION = 0.5
EXTENT = 50
AXIS = -EXTENT + (np.arange(GRID) + 0.5) * RESOLUTION
XX, YY = np.meshgrid(AXIS, AXIS, indexing="ij")


def cells(points):
    rc = np.floor((points[:, :2] + EXTENT) / RESOLUTION).astype(int)
    keep = (rc >= 0).all(axis=1) & (rc < GRID).all(axis=1)
    return rc[keep, 0], rc[keep, 1], keep


def lidar_features(points, intensity):
    points = np.asarray(points, dtype=float)
    intensity = np.asarray(intensity, dtype=float)
    keep = np.isfinite(points).all(axis=1) & np.isfinite(intensity)
    keep &= ~((points[:, 0] > -1) & (points[:, 0] < 3.7) & (np.abs(points[:, 1]) < 1.1))
    points, intensity = points[keep], intensity[keep]
    obstacle = (points[:, 2] > 0.3) & (points[:, 2] < 3)
    r, c, ok = cells(points[obstacle])
    count = np.zeros((GRID, GRID))
    np.add.at(count, (r, c), 1)
    height = np.full((GRID, GRID), -np.inf)
    np.maximum.at(height, (r, c), points[obstacle, 2][ok])
    ra, ca, valid = cells(points)
    all_count = np.zeros((GRID, GRID))
    total = np.zeros((GRID, GRID))
    np.add.at(all_count, (ra, ca), 1)
    np.add.at(total, (ra, ca), intensity[valid])
    features = np.zeros((7, GRID, GRID), dtype=np.float32)
    features[0] = np.log1p(count) / 3
    features[1] = np.where(np.isfinite(height), (height + 1) / 5, 0)
    features[2] = np.log1p(all_count) / 3
    features[3] = total / np.maximum(all_count, 1) / 255
    return features


def footprint(box):
    dx, dy = XX - box["x"], YY - box["y"]
    co, si = np.cos(box["yaw"]), np.sin(box["yaw"])
    return (np.abs(co * dx + si * dy) <= box["l"] / 2) & (np.abs(-si * dx + co * dy) <= box["w"] / 2)


def carla_to_ego(points, sensor_matrix, ego_matrix):
    """CARLA local -> world -> ego local -> right-handed x-forward/y-left/z-up."""
    points = np.asarray(points)
    homogeneous = np.column_stack((points[:, :3], np.ones(len(points))))
    local = homogeneous @ (np.linalg.inv(ego_matrix) @ sensor_matrix).T
    local[:, 1] *= -1
    return local[:, :3]
