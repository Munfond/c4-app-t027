"""Explicit single-sweep detector geometry. Distribution shift is not calibration.

No dummy past sweeps. The keyframe's measured time lag is zero by definition.
Model-specific intensity approximation must be recorded with every prediction.
"""
import numpy as np

from src.simulation.carla_rig import FLIP


def single_sweep_points(raw, intensity_policy="raw"):
    raw = np.asarray(raw, dtype=np.float32)
    if raw.ndim != 2 or raw.shape[1] != 4 or not np.isfinite(raw).all():
        raise ValueError("Expected finite CARLA XYZI")
    if intensity_policy not in ("raw", "scale_255_approximation"):
        raise ValueError("Unknown intensity policy")
    points = np.zeros((len(raw), 5), np.float32)
    points[:, :4] = raw
    points[:, 1] *= -1  # LiDAR-local x-forward/y-left/z-up.
    if intensity_policy == "scale_255_approximation":
        points[:, 3] *= 255
    return points


def lidar_model_to_ego(sensor):
    # Recorded matrix maps CARLA-local axes; model input already flips y.
    return np.asarray(sensor["sensor_to_ego_lab"]) @ FLIP


def predicted_boxes_to_ego(centers, sizes, yaws, sensor):
    matrix = lidar_model_to_ego(sensor)
    centers = np.asarray(centers)
    locations = np.column_stack((centers, np.ones(len(centers)))) @ matrix.T
    boxes = []
    for center, size, yaw in zip(locations[:, :3], sizes, yaws):
        c, s = np.cos(yaw), np.sin(yaw)
        rotation = matrix[:3, :3] @ np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.]])
        boxes.append({"center_ego": center.tolist(), "size_lwh": np.asarray(size).tolist(),
                      "rotation_ego": rotation.tolist()})
    return boxes
