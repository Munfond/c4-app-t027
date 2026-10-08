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
    sparse = tmp_path / 'sparse'
    shutil.copytree(pilot.SPARSE_ROOT, sparse)
    monkeypatch.setattr(pilot, 'SPARSE_ROOT', sparse)
    monkeypatch.setattr(store, 'get_settings', lambda: Settings(_env_file=None, experiment_root=tmp_path / 'reviews'))
    return root


@pytest.mark.asyncio
async def test_sparse_archive_preserves_input_lineage_and_full_capture_scope(client, archive):
    value = (await client.get(pilot.BASE + '?pilot=sparse60')).json()
    assert value['available'] and len(value['variants']) == 4
    assert value['gt_audit_frames'] == 1200
    assert value['selection'] is None and value['measured_perception_replay_ready'] is False
    assert {tuple(r['frame_selection']['indices']) for r in value['variants']} == {tuple(range(0, 1200, 60))}
    row = value['variants'][-1]
    report = (await client.get(row['report_url'])).json()
    assert report['input_lidar_channels'] == 64
    assert all(f['input_lidar_sensor'] == 'LIDAR_TOP_64' for f in report['frames'])
    assert row['matched_target_frame_instances'] == 29 and row['target_frame_instances'] == 62
    detailed = await client.get(value['gt_detail_url'])
    assert detailed.status_code == 200 and detailed.content.startswith(b'PK')


@pytest.mark.asyncio
async def test_review_cannot_cross_pilot_snapshot_namespace(client, archive):
    short = (await client.get(pilot.BASE)).json()
    sparse = (await client.get(pilot.BASE + '?pilot=sparse60')).json()
    payload = {'reviewer': 'Software fixture', 'verdict': 'needs_evidence',
               'notes': 'Need actual held-out scenes and complete GT', 'evidence_sha256': short['evidence_sha256']}
    assert (await client.post(pilot.BASE + '/reviews?pilot=sparse60', json=payload)).status_code == 409
    response = await client.post(pilot.BASE + '/reviews?pilot=sparse60', json=payload | {'evidence_sha256': sparse['evidence_sha256']})
    assert response.status_code == 201 and response.json()['used_for_training'] is False
    assert (await client.get(pilot.BASE + '/reviews')).json()['items'] == []
    assert len((await client.get(pilot.BASE + '/reviews?pilot=sparse60')).json()['items']) == 1


@pytest.mark.asyncio
async def test_sparse_tamper_is_not_silently_replaced_by_old_pilot(client, archive):
    with (pilot.SPARSE_ROOT / 'pp-64-full-amp/report.json').open('a') as file:
        file.write(' ')
    assert (await client.get(pilot.BASE + '?pilot=sparse60')).status_code == 409
    assert (await client.get(pilot.BASE)).status_code == 200
    assert (await client.get(pilot.BASE + '?pilot=../../.env')).status_code == 422


@pytest.mark.asyncio
async def test_missing_declared_bundle_member_is_integrity_failure_not_optional_absence(client, archive):
    (pilot.SPARSE_ROOT / 'full-gt-audit.zip').unlink()
    assert (await client.get(pilot.BASE + '?pilot=sparse60')).status_code == 409


@pytest.mark.asyncio
async def test_actual_bundle_has_traceable_diagnostic_scope(client, archive):
    response = await client.get(pilot.BASE)
    assert response.status_code == 200
    value = response.json()
    assert value['available']
    assert len(value['variants']) == 8
    assert all(row['frames'] == 20 for row in value['variants'])
    assert value['selection'] is None
    assert not value['measured_perception_replay_ready']
    assert value['evidence_sha256'] == pilot.snapshot()['evidence_sha256']
    geometry = (await client.get(value['variants'][0]['geometry_url'])).json()
    assert not geometry['validated_detection_quality']
    assert not geometry['usable_for_rl_reward']
    coverage = (await client.get(value['gt_coverage_url'])).json()
    assert coverage['reference_visible_instances_without_32_box_returns'] == 12
    assert coverage['scene_precision_ready'] is False


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
