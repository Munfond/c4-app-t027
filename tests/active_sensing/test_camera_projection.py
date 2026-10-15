import numpy as np
import pytest

from src.simulation.camera_projection import camera_box


def pose(x=0, y=0, z=0):
    matrix = np.eye(4)
    matrix[:3, 3] = [x, y, z]
    return matrix


def test_front_box_pinhole_bounds_and_camera_axes():
    rect = camera_box(pose(10), (1, 1, 1), np.eye(4), (640, 360), 90)
    assert rect == pytest.approx([0.5 - 1 / 18, 0.5 - 8 / 81, 0.5 + 1 / 18, 0.5 + 8 / 81])
    right_up = camera_box(pose(10, 2, 2), (1, 1, 1), np.eye(4), (640, 360), 90)
    assert (right_up[0] + right_up[2]) / 2 > 0.5
    assert (right_up[1] + right_up[3]) / 2 < 0.5


def test_common_world_transform_and_fov_preserve_correspondence():
    world = pose(100, 200, 10)
    expected = camera_box(pose(10), (1, 1, 1), np.eye(4), (640, 360), 90)
    assert camera_box(world @ pose(10), (1, 1, 1), world, (640, 360), 90) == pytest.approx(expected)
    narrow = camera_box(pose(10), (1, 1, 1), np.eye(4), (640, 360), 60)
    wide = camera_box(pose(10), (1, 1, 1), np.eye(4), (640, 360), 110)
    assert narrow[2] - narrow[0] > wide[2] - wide[0]


@pytest.mark.parametrize("box", [pose(-10), pose(0.5), pose(10, 100)])
def test_no_projection_is_invented_behind_near_plane_or_outside_image(box):
    assert camera_box(box, (1, 1, 1), np.eye(4), (640, 360), 90) is None
