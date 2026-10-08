"""Geometry tests use known coordinates; these do not certify detector accuracy."""
import numpy as np
import pytest

from src.active_sensing.lidar_adapter import predicted_boxes_to_ego, single_sweep_points
from src.simulation.carla_rig import FLIP


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
