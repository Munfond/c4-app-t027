"""Audit positive target geometry; deliberately refuse full detection-quality claims."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.active_sensing.detection_diagnostic import target_diagnostic  # noqa: E402
from src.active_sensing.episode_inputs import RawEpisode  # noqa: E402
from src.simulation.carla_rig import sha256_file  # noqa: E402


def audit(episode_root, prediction_root, radius=54.):
    episode = RawEpisode(episode_root)
    report = json.loads((prediction_root / 'report.json').read_text())
    if report['capture_manifest_sha256'] != episode.verification['manifest_sha256']:
        raise ValueError('Prediction references another capture')
    rows = []
    indices = set()
    for timing in report['frames']:
        index = timing['index']
        if index in indices or not 0 <= index < len(episode.manifest['frames']):
            raise ValueError('Invalid or duplicate prediction frame index')
        indices.add(index)
        ref = episode.manifest['frames'][index]
        prediction_path = prediction_root / f'frame_{index:05d}.json'
        prediction = json.loads(prediction_path.read_text())
        meta = json.loads(episode._artifact(ref['metadata'], '').read_text())
        gt_path = episode._artifact(meta['actor_ground_truth'], 'ground_truth')
        gt = json.loads(gt_path.read_text())
        for record in (gt, timing, prediction):
            if record['frame_id'] != ref['frame_id'] or abs(record['timestamp'] - ref['timestamp']) > 1e-5:
                raise ValueError('Prediction/reference frame or timestamp mismatch')
        if prediction['input_sha256'] != timing['input_sha256']:
            raise ValueError('Prediction input hash differs from run report')
        rows.append(dict(target_diagnostic(gt['boxes'], prediction['boxes'], radius_m=radius,
                                           threshold=report['score_threshold']),
                         index=index, frame_id=ref['frame_id'], timestamp=ref['timestamp'],
                         prediction_sha256=sha256_file(prediction_path),
                         actor_gt_sha256=sha256_file(gt_path)))
    total = sum(row['required_targets'] for row in rows)
    found = sum(row['matched_targets'] for row in rows)
    return {'kind': 'CARLA_partial_GT_positive_geometry_diagnostic',
            'capture_manifest_sha256': report['capture_manifest_sha256'],
            'detector_report_sha256': sha256_file(prediction_root / 'report.json'),
            'frames': rows, 'target_frame_instances': total, 'matched_target_frame_instances': found,
            'positive_target_geometry_recall': found / total if total else None,
            'independent_scenes': 1, 'validated_detection_quality': False,
            'usable_for_rl_reward': False,
            'limitations': ['Partial spawned-actor GT cannot establish scene precision/false positives',
                            'Class-agnostic geometry, not official class-aware detection quality',
                            'Semantic visibility from separate 64-channel reference is not 32-channel observability',
                            'Target/frame instances are correlated; no confidence interval or population generalization',
                            'Reference actor geometry is engine GT; ontology and coverage still need engineer review']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episode', type=Path)
    parser.add_argument('predictions', type=Path)
    parser.add_argument('--radius', type=float, default=54.)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; choose a new file')
    result = audit(args.episode, args.predictions, args.radius)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps({key: value for key, value in result.items() if key != 'frames'}, indent=2))
