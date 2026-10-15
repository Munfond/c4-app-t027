import numpy as np
import pytest

from src.active_sensing.core import Profile
from src.active_sensing.gate import gate_capture
from src.active_sensing.sampling import subset_indices


def test_runtime_gate_matches_detector_replay_subset_without_reordering():
    points = [(float(i), 2., 3., .5) for i in range(31)]
    profile = Profile('half', 'official_lidar', 5, lidar_channels=32, lidar_keep=.5)
    gated = gate_capture({'frame_id': 64, 'streams': {'lidar': {'32': {
        'frame_id': 64, 'points': points}}}}, profile, seed=7)['streams']['lidar']
    expected = np.sort(np.random.default_rng(71).choice(31, size=16, replace=False))
    assert gated['points'] == [points[i] for i in expected]
    assert gated['sampling_seed'] == 71
    assert subset_indices(0, .5, 0).size == 0
    assert subset_indices(3, 1., 0).tolist() == [0, 1, 2]


@pytest.mark.parametrize('length,keep,seed', [(1, float('nan'), 0), (1, .5, -1), (-1, .5, 0)])
def test_invalid_sampling_request_fails_closed(length, keep, seed):
    with pytest.raises(ValueError):
        subset_indices(length, keep, seed)
