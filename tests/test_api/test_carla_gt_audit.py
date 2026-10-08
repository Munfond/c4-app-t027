import numpy as np
import pytest

from scripts.audit_carla_gt import box_return_counts


def test_oriented_box_returns_use_actual_input_points_not_reference_visibility():
    box = {'actor_id': 7, 'center_ego': [10, 3, 1], 'size_lwh': [4, 2, 2],
           'rotation_ego': [[0, -1, 0], [1, 0, 0], [0, 0, 1]]}
    points = [[10, 3, 1], [10, 4.5, 1], [11.5, 3, 1], [10, 3, 4]]
    assert box_return_counts(points, [box]) == {7: 2}
    assert box_return_counts(np.empty((0, 3)), [box]) == {7: 0}
    with pytest.raises(ValueError, match='finite'):
        box_return_counts([[np.nan, 0, 0]], [box])
