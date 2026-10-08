import copy

import pytest

from src.active_sensing.fixtures import synthetic_replay
from src.active_sensing.replay import Replay


@pytest.mark.parametrize('flag', ['validated_detection_quality', 'usable_for_rl_reward', 'validated_profile_catalog'])
def test_detector_diagnostic_cannot_be_admitted_by_renaming_provenance(flag):
    payload = {'schema_version': 1, 'provenance': {
        'kind': 'measured_perception', 'history_mode': 'stateless_independent_windows',
        'capture_id': 'fixture', 'model_manifest_sha256': 'a' * 64, 'hardware': 'contract fixture',
        'timing_scope': 'total_gpu_work_per_window', 'monitoring_cost_included': True,
        'validated_detection_quality': True, 'usable_for_rl_reward': True, 'validated_profile_catalog': True,
        'evaluation_protocol_sha256': 'b' * 64}}
    payload = copy.deepcopy(payload)
    payload['provenance'][flag] = False
    with pytest.raises(ValueError, match=flag):
        Replay(payload)


def test_string_false_does_not_count_as_measured_monitoring_cost():
    payload = {'schema_version': 1, 'provenance': {
        'kind': 'measured_perception', 'history_mode': 'stateless_independent_windows',
        'capture_id': 'fixture', 'model_manifest_sha256': 'a' * 64, 'hardware': 'contract fixture',
        'timing_scope': 'total_gpu_work_per_window', 'monitoring_cost_included': 'false'}}
    with pytest.raises(ValueError, match='truthy string'):
        Replay(payload)


def test_partial_per_profile_geometry_stays_ineligible_even_with_top_level_flags():
    # This is an in-memory contract test, not a measured dataset or validation.
    payload = synthetic_replay()
    payload['provenance'].update(kind='measured_perception', monitoring_cost_included=True,
                                 timing_scope='total_gpu_work_per_window', hardware='software fixture',
                                 capture_id='fixture', model_manifest_sha256='a' * 64,
                                 validated_detection_quality=True, usable_for_rl_reward=True,
                                 validated_profile_catalog=True, evaluation_protocol_sha256='b' * 64)
    for episode in payload['episodes']:
        for step in episode['steps']:
            for result in step['profile_results'].values():
                result.update(validated_detection_quality=True, usable_for_rl_reward=True)
    first = next(iter(payload['episodes'][0]['steps'][0]['profile_results'].values()))
    first['usable_for_rl_reward'] = False
    with pytest.raises(ValueError, match='Partial/unvalidated'):
        Replay(payload)


@pytest.mark.parametrize('protocol_hash', [None, 123, 'not-a-hash'])
def test_invalid_protocol_hash_rejected_as_contract_error(protocol_hash):
    payload = {'schema_version': 1, 'provenance': {
        'kind': 'measured_perception', 'history_mode': 'stateless_independent_windows',
        'capture_id': 'fixture', 'model_manifest_sha256': 'a' * 64, 'hardware': 'contract fixture',
        'timing_scope': 'total_gpu_work_per_window', 'monitoring_cost_included': True,
        'validated_detection_quality': True, 'usable_for_rl_reward': True, 'validated_profile_catalog': True,
        'evaluation_protocol_sha256': protocol_hash}}
    with pytest.raises(ValueError, match='protocol SHA256'):
        Replay(payload)
