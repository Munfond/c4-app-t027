"""GPU-free objective must retain quality gates and measured-data honesty."""
import pytest

from src.active_sensing.fixtures import synthetic_replay
from src.active_sensing.replay import Replay, summarize


def fixture():
    payload = synthetic_replay()
    payload['constraints']['objective'] = 'quality_latency'
    for episode in payload['episodes']:
        for step in episode['steps']:
            for result in step['profile_results'].values():
                result.pop('gpu_ms')
    return payload


def test_gpu_free_replay_has_no_fabricated_gpu_metrics():
    replay = Replay(fixture(), allow_synthetic=True)
    replay.reset(replay.episodes[0]['id'])
    _, reward, _, info = replay.advance(replay.reference)
    assert reward is not None
    assert info['metrics']['gpu_ms'] is None
    assert info['metrics']['gpu_ratio'] is None
    assert info['metrics']['objective'] == 'quality_latency'
    assert summarize([info])['gpu_ms'] is None


def test_measured_admission_not_bypassed_when_gpu_is_removed():
    payload = fixture()
    payload['provenance']['kind'] = 'measured_perception'
    with pytest.raises(ValueError):
        Replay(payload)


def test_latency_penalty_prefers_faster_equal_quality_outputs():
    fast = Replay(fixture(), allow_synthetic=True)
    payload = fixture()
    for episode in payload['episodes']:
        for step in episode['steps']:
            for result in step['profile_results'].values():
                result['end_to_end_ms'] = 100
    slow = Replay(payload, allow_synthetic=True)
    scores = []
    for replay in (fast, slow):
        replay.reset(replay.episodes[0]['id'])
        scores.append(replay.advance(replay.reference)[1])
    assert scores[0] > scores[1]
