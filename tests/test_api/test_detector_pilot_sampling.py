import pytest

from scripts.smoke_carla_detector import pilot_frame_indices


def test_sparse_diagnostic_covers_the_requested_capture_without_changing_sample_count():
    indices = pilot_frame_indices(1200, 20, 60)
    assert len(indices) == 20 and indices[0] == 0 and indices[-1] == 1140
    assert pilot_frame_indices(20, 20) == list(range(20))


@pytest.mark.parametrize('stride', [0, -1, True, 1.5])
def test_invalid_stride_cannot_be_silently_coerced(stride):
    with pytest.raises(ValueError, match='positive integer'):
        pilot_frame_indices(1200, 20, stride)


def test_out_of_range_sample_is_rejected_instead_of_silently_truncated():
    with pytest.raises(ValueError, match='no truncated sample'):
        pilot_frame_indices(20, 20, 2)
