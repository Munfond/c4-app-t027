"""Read-only measured pilot archive, separate from executable occupancy studies."""
import json
from pathlib import Path

from src.services.agent_evidence import archived_reviews, digest, save_snapshot_review
from src.simulation.carla_rig import sha256_file

ROOT = Path(__file__).resolve().parents[2] / 'eval/detector-pilot-2026-10-08'
SPARSE_ROOT = Path(__file__).resolve().parents[2] / 'eval/detector-pilot-sparse-60s-2026-10-08'
ARCHIVE_ID = 'detector-pilot:2026-10-08'
BASE = '/api/v1/experiments/detector-pilot'


def archive(pilot):
    if pilot == 'short':
        return ROOT, ARCHIVE_ID
    if pilot == 'sparse60':
        return SPARSE_ROOT, ARCHIVE_ID + ':sparse60'
    raise ValueError('Unknown fixed pilot archive')


def artifact(name, pilot='short'):
    selected, _ = archive(pilot)
    manifest = json.loads((selected / 'bundle-manifest.json').read_text())
    members = manifest['files']
    if name not in members or not 1 <= len(members) <= 256:
        raise KeyError('Artifact not in evidence bundle')
    path = (selected / name).resolve()
    root = selected.resolve()
    expected = members[name]
    if (not path.is_relative_to(root) or path.stat().st_size != expected['bytes']
            or expected['bytes'] > 2 * 1024 ** 2 or sha256_file(path) != expected['sha256']):
        raise ValueError('Evidence bundle artifact checksum/boundary mismatch')
    return path


def snapshot(pilot='short'):
    selected, archive_id = archive(pilot)
    suffix = '?pilot=' + pilot
    manifest = json.loads((selected / 'bundle-manifest.json').read_text())
    for name in manifest['files']:
        artifact(name, pilot)
    summary = json.loads(artifact('summary.json', pilot).read_text())
    if (summary['status'] != 'completed_diagnostic_only' or summary['selection'] is not None
            or summary['measured_perception_replay_ready'] is not False):
        raise ValueError('Pilot must remain explicitly diagnostic, without a validated selection')
    for row in summary['variants']:
        directory = row['evidence_directory']
        report_path = artifact(directory + '/report.json', pilot)
        geometry_path = artifact(directory + '/geometry.json', pilot)
        report, geometry = json.loads(report_path.read_text()), json.loads(geometry_path.read_text())
        if (geometry.get('validated_detection_quality') is not False
                or geometry.get('usable_for_rl_reward') is not False
                or report.get('measured_perception_replay_ready') is not False):
            raise ValueError('Incomplete pilot cannot declare validated quality or RL readiness')
        if (sha256_file(report_path) != row['report_sha256'] or sha256_file(geometry_path) != row['geometry_sha256']
                or geometry['detector_report_sha256'] != row['report_sha256']
                or report['capture_manifest_sha256'] != row['capture_manifest_sha256']
                or geometry['capture_manifest_sha256'] != row['capture_manifest_sha256']):
            raise ValueError('Pilot summary does not match its reference evidence')
        row['report_url'] = BASE + '/artifacts/' + directory + '/report.json' + suffix
        row['geometry_url'] = BASE + '/artifacts/' + directory + '/geometry.json' + suffix
    if len({row['capture_manifest_sha256'] for row in summary['variants']}) != 1:
        raise ValueError('Variants reference different captures')
    if pilot == 'sparse60' and len({tuple(row['frame_selection']['indices']) for row in summary['variants']}) != 1:
        raise ValueError('Sparse variants must use the same selected frames')
    coverage = json.loads(artifact('gt-coverage-audit.json', pilot).read_text())
    if (coverage['capture_manifest_sha256'] != summary['variants'][0]['capture_manifest_sha256']
            or coverage['scene_precision_ready'] is not False or coverage['usable_for_rl_reward'] is not False):
        raise ValueError('GT audit must reference this capture and preserve incomplete-quality scope')
    value = dict(summary, available=True, archive_id=archive_id,
                 bundle_manifest_sha256=sha256_file(selected / 'bundle-manifest.json'),
                 gt_coverage_url=BASE + '/artifacts/gt-coverage-audit.json' + suffix,
                 gt_detail_url=BASE + '/artifacts/full-gt-audit.zip' + suffix if pilot == 'sparse60' else None,
                 sampling_notice=('20 mẫu cách 60 index, trải 57 giây từ capture 1.200 frame. Không phải cadence model hoặc replay policy.'
                                  if pilot == 'sparse60' else '20 frame liên tiếp trong một capture khoảng 1 giây.'),
                 gt_scope_notice=('GT world vehicle/walker; static/parked mesh mapping chưa được kiểm định.'
                                  if pilot == 'sparse60' else 'GT chỉ phủ actor được spawn; không phủ toàn cảnh.'),
                 gt_audit_frames=coverage['frames'] if pilot == 'sparse60' else len(coverage['frames']),
                 gt_coverage=dict(reference_visible_instances_without_32_box_returns=coverage['reference_visible_instances_without_32_box_returns'],
                                  reference_visible_instances_without_64_box_returns=coverage['reference_visible_instances_without_64_box_returns']),
                 notice='20 frames in one short CARLA scene. Partial class-agnostic target geometry; not mAP, precision, validated profiles or a trained policy.',
                 conclusion='PointPillars AMP là ứng viên kiểm định tiếp: nhanh hơn và ghép được nhiều mục tiêu hơn BEVFusion LiDAR trong capture này. Chưa có cấu hình đạt 20 Hz; chưa chọn profile tối ưu. Giảm 50% điểm làm giảm số mục tiêu ghép được ở cả hai model.')
    if pilot == 'sparse60':
        value['notice'] = '20 sparse samples from one 60-second capture; incomplete geometry diagnostic, not validated profiles or RL evidence.'
        value['conclusion'] = 'AMP 32 kênh giảm wall mean từ 76,72 xuống 53,42 ms, giữ 30/62 lượt ghép. Half points còn 26/62. AMP 64 kênh chậm hơn và chỉ 29/62: nhiều điểm hơn chưa chứng minh tốt hơn. Chưa nghiệm thu profile; 19/20 mẫu AMP32 vẫn vượt 50 ms.'
    return value | {'evidence_sha256': digest(value)}


def reviews(pilot='short'):
    snapshot(pilot)
    return archived_reviews(archive(pilot)[1])


def save_review(request, pilot='short'):
    return save_snapshot_review(archive(pilot)[1], request, snapshot(pilot))
