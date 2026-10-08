import shutil

import pytest

from src.config import Settings
from src.services import detector_pilot_evidence as pilot
from src.services import experiment_store as store


@pytest.fixture
def archive(tmp_path, monkeypatch):
    root = tmp_path / 'bundle'
    shutil.copytree(pilot.ROOT, root)
    monkeypatch.setattr(pilot, 'ROOT', root)
    monkeypatch.setattr(store, 'get_settings', lambda: Settings(_env_file=None, experiment_root=tmp_path / 'reviews'))
    return root


@pytest.mark.asyncio
async def test_actual_bundle_has_traceable_diagnostic_scope(client, archive):
    response = await client.get(pilot.BASE)
    assert response.status_code == 200
    value = response.json()
    assert value['available']
    assert len(value['variants']) == 5
    assert all(row['frames'] == 20 for row in value['variants'])
    assert value['selection'] is None
    assert not value['measured_perception_replay_ready']
    assert value['evidence_sha256'] == pilot.snapshot()['evidence_sha256']
    geometry = (await client.get(value['variants'][0]['geometry_url'])).json()
    assert not geometry['validated_detection_quality']
    assert not geometry['usable_for_rl_reward']


@pytest.mark.asyncio
async def test_modified_artifacts_fail_integrity_not_quality_fallback(client, archive):
    with (archive / 'lidar-full-fp32/report.json').open('a') as file:
        file.write(' ')
    assert (await client.get(pilot.BASE)).status_code == 409
    assert (await client.get(pilot.BASE + '/artifacts/lidar-full-fp32/report.json')).status_code == 409


def test_artifact_paths_are_allowlisted_not_server_file_reads(archive):
    for path in ('../.env', '/etc/passwd', 'not-listed.json'):
        with pytest.raises(KeyError):
            pilot.artifact(path)


@pytest.mark.asyncio
async def test_engineer_review_pins_snapshot_and_does_not_train(client, archive):
    snapshot = (await client.get(pilot.BASE)).json()
    payload = {'reviewer': 'Software test fixture', 'verdict': 'needs_evidence',
               'notes': 'Need separate scene coverage and quality validation',
               'evidence_sha256': snapshot['evidence_sha256']}
    response = await client.post(pilot.BASE + '/reviews', json=payload)
    assert response.status_code == 201
    assert response.json()['used_for_training'] is False
    assert response.json()['reviewer_identity_verified'] is False
    assert (await client.get(pilot.BASE)).json() == snapshot
    assert len((await client.get(pilot.BASE + '/reviews')).json()['items']) == 1
    assert (await client.post(pilot.BASE + '/reviews', json=payload | {'evidence_sha256': '0' * 64})).status_code == 409


@pytest.mark.asyncio
async def test_deployment_without_optional_bundle_remains_explicit(client, tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, 'ROOT', tmp_path / 'absent')
    response = await client.get(pilot.BASE)
    assert response.status_code == 200
    assert response.json()['available'] is False
