import numpy as np
import pytest

from src.active_sensing.detection_diagnostic import target_diagnostic


def box(x, actor_id=None, visible=True):
    result = {'center_ego': [x, 0, 1], 'size_lwh': [4, 2, 2],
              'rotation_ego': np.eye(3).tolist()}
    if actor_id is None:
        result.update(score=.8, class_name='truck')
    else:
        result.update(actor_id=actor_id, type_id='vehicle.test', semantic_lidar_visible=visible)
    return result


def test_maximum_cardinality_does_not_greedily_lose_a_target():
    # A can match both predictions, B only p0. Nearest-first greedy takes p0 for A.
    report = target_diagnostic([box(0, 1), box(2.1, 2)], [box(.2), box(-1.5)])
    assert report['matched_targets'] == 2
    assert {r['actor_id']: r['prediction_index'] for r in report['matches']} == {1: 1, 2: 0}
    assert report['false_positives'] is None
    assert report['precision'] is None
    assert not report['usable_for_rl_reward']


def test_invisible_outside_and_no_target_frames_are_not_perfect_recall():
    report = target_diagnostic([box(0, 1, visible=False), box(60, 2)], [box(2)])
    assert report['required_targets'] == 0
    assert report['positive_target_geometry_recall'] is None
    assert report['unmatched_predictions_unclassified'] == 1


def test_one_prediction_cannot_match_two_actors_or_invalid_geometry():
    report = target_diagnostic([box(0, 1), box(1, 2)], [box(.5)])
    assert report['matched_targets'] == 1
    assert report['positive_target_geometry_recall'] == .5
    with pytest.raises(ValueError, match='Duplicate'):
        target_diagnostic([box(0, 1), box(1, 1)], [])
    invalid = box(0)
    invalid['rotation_ego'][0][0] = -1
    with pytest.raises(ValueError, match='Invalid box geometry'):
        target_diagnostic([], [invalid])
