"""Geometry tests use known coordinates; these do not certify detector accuracy."""
import numpy as np
import pytest

from src.active_sensing.lidar_adapter import (
    camera_to_lidar_calibration,
    detector_features,
    predicted_boxes_to_ego,
    single_sweep_points,
)
from src.simulation.carla_rig import FLIP, OPTICAL, camera_intrinsic


def test_measured_single_sweep_has_zero_lag_and_explicit_intensity_policy():
    raw = np.array([[3, 2, -1, .5]], np.float32)
    np.testing.assert_allclose(single_sweep_points(raw), [[3, -2, -1, .5, 0]])
    np.testing.assert_allclose(single_sweep_points(raw, 'scale_255_approximation'), [[3, -2, -1, 127.5, 0]])
    np.testing.assert_allclose(raw, [[3, 2, -1, .5]])
    with pytest.raises(ValueError, match='Expected finite'):
        single_sweep_points([[np.nan, 0, 0, 0]])


def test_prediction_center_is_transformed_from_sensor_origin_not_assumed_ground():
    extrinsic = FLIP.copy()
    extrinsic[2, 3] = 2
    result = predicted_boxes_to_ego([[10, 3, -.5]], [[4, 2, 1.5]], [.4],
                                    {'sensor_to_ego_lab': extrinsic})[0]
    np.testing.assert_allclose(result['center_ego'], [10, 3, 1.5])
    assert result['size_lwh'] == [4, 2, 1.5]
    np.testing.assert_allclose(np.linalg.det(result['rotation_ego']), 1)


def test_camera_projection_uses_measured_lidar_mount_and_optical_axes():
    lidar = FLIP.copy()
    lidar[2, 3] = 2
    camera_pose = np.eye(4)
    camera_pose[:3, 3] = [1.5, 0, 1.7]
    camera = FLIP @ camera_pose @ np.linalg.inv(OPTICAL)
    intrinsic = camera_intrinsic(640, 360, 100)
    calib = camera_to_lidar_calibration({'sensor_to_ego_lab': lidar},
                                        {'optical_to_ego_lab': camera, 'intrinsic': intrinsic})
    # Model-local point corresponds to camera-height straight ahead in raw CARLA.
    point = np.array([11.5, 0, -.3, 1])
    optical = np.asarray(calib['lidar2cam']) @ point
    pixel = intrinsic @ optical[:3]
    np.testing.assert_allclose(optical[:3], [0, 0, 10], atol=1e-6)
    np.testing.assert_allclose(pixel[:2] / pixel[2], [320, 180])
    np.testing.assert_allclose(np.linalg.det(np.asarray(calib['lidar2cam'])[:3, :3]), 1)


def test_pointpillars_uses_lag_not_intensity_in_fourth_channel():
    points = single_sweep_points([[2, 3, 4, .75]])
    np.testing.assert_allclose(detector_features(points, 'pointpillars'), [[2, -3, 4, 0]])
    np.testing.assert_allclose(detector_features(points, 'lidar'), [[2, -3, 4, .75, 0]])
    with pytest.raises(ValueError, match='feature contract'):
        detector_features(points, 'unknown')
