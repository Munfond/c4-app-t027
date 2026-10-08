"""Read-only measured pilot archive, separate from executable occupancy studies."""
import json
from pathlib import Path

from src.services.agent_evidence import archived_reviews, digest, save_snapshot_review
from src.simulation.carla_rig import sha256_file

ROOT = Path(__file__).resolve().parents[2] / 'eval/detector-pilot-2026-10-08'
ARCHIVE_ID = 'detector-pilot:2026-10-08'
BASE = '/api/v1/experiments/detector-pilot'


def artifact(name):
    manifest = json.loads((ROOT / 'bundle-manifest.json').read_text())
    members = manifest['files']
    if name not in members or not 1 <= len(members) <= 256:
        raise KeyError('Artifact not in evidence bundle')
    path = (ROOT / name).resolve()
    root = ROOT.resolve()
    expected = members[name]
    if (not path.is_relative_to(root) or path.stat().st_size != expected['bytes']
            or expected['bytes'] > 2 * 1024 ** 2 or sha256_file(path) != expected['sha256']):
        raise ValueError('Evidence bundle artifact checksum/boundary mismatch')
    return path


def snapshot():
    manifest = json.loads((ROOT / 'bundle-manifest.json').read_text())
    for name in manifest['files']:
        artifact(name)
    summary = json.loads(artifact('summary.json').read_text())
    if (summary['status'] != 'completed_diagnostic_only' or summary['selection'] is not None
            or summary['measured_perception_replay_ready'] is not False):
        raise ValueError('Pilot must remain explicitly diagnostic, without a validated selection')
    for row in summary['variants']:
        directory = row['evidence_directory']
        report_path = artifact(directory + '/report.json')
        geometry_path = artifact(directory + '/geometry.json')
        report, geometry = json.loads(report_path.read_text()), json.loads(geometry_path.read_text())
        if (sha256_file(report_path) != row['report_sha256'] or sha256_file(geometry_path) != row['geometry_sha256']
                or geometry['detector_report_sha256'] != row['report_sha256']
                or report['capture_manifest_sha256'] != row['capture_manifest_sha256']
                or geometry['capture_manifest_sha256'] != row['capture_manifest_sha256']):
            raise ValueError('Pilot summary does not match its reference evidence')
        row['report_url'] = BASE + '/artifacts/' + directory + '/report.json'
        row['geometry_url'] = BASE + '/artifacts/' + directory + '/geometry.json'
    if len({row['capture_manifest_sha256'] for row in summary['variants']}) != 1:
        raise ValueError('Variants reference different captures')
    coverage = json.loads(artifact('gt-coverage-audit.json').read_text())
    if (coverage['capture_manifest_sha256'] != summary['variants'][0]['capture_manifest_sha256']
            or coverage['scene_precision_ready'] is not False or coverage['usable_for_rl_reward'] is not False):
        raise ValueError('GT audit must reference this capture and preserve incomplete-quality scope')
    value = dict(summary, available=True, archive_id=ARCHIVE_ID,
                 bundle_manifest_sha256=sha256_file(ROOT / 'bundle-manifest.json'),
                 gt_coverage_url=BASE + '/artifacts/gt-coverage-audit.json',
                 gt_coverage=dict(reference_visible_instances_without_32_box_returns=coverage['reference_visible_instances_without_32_box_returns'],
                                  reference_visible_instances_without_64_box_returns=coverage['reference_visible_instances_without_64_box_returns']),
                 notice='20 frames in one short CARLA scene. Partial class-agnostic target geometry; not mAP, precision, validated profiles or a trained policy.',
                 conclusion='PointPillars AMP là ứng viên kiểm định tiếp: nhanh hơn và ghép được nhiều mục tiêu hơn BEVFusion LiDAR trong capture này. Chưa có cấu hình đạt 20 Hz; chưa chọn profile tối ưu. Giảm 50% điểm làm giảm số mục tiêu ghép được ở cả hai model.')
    return value | {'evidence_sha256': digest(value)}


def reviews():
    snapshot()
    return archived_reviews(ARCHIVE_ID)


def save_review(request):
    return save_snapshot_review(ARCHIVE_ID, request, snapshot())
