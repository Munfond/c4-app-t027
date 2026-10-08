"""Bounded same-capture detector pilot. Not validated profile selection or RL training."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from scripts.audit_carla_detection import audit  # noqa: E402
from src.simulation.carla_rig import sha256_file  # noqa: E402


def bench(episode, output, frames, include_camera):
    if not 1 <= frames <= 20:
        raise ValueError('Pilot must contain 1..20 frames')
    if output.exists():
        raise ValueError('Output exists; use a fresh directory')
    output.mkdir(parents=True)
    variants = [('lidar-full-fp32', 'lidar', 1., False),
                ('lidar-half-fp32', 'lidar', .5, False),
                ('lidar-full-amp', 'lidar', 1., True)]
    if include_camera:
        variants.extend([('cl-full-fp32', 'camera_lidar', 1., False),
                         ('cl-full-amp', 'camera_lidar', 1., True)])
    results = []
    for name, model, keep, amp in variants:
        target = output / name
        command = [sys.executable, str(PROJECT / 'scripts/smoke_carla_detector.py'),
                   str(episode), '--output', str(target), '--frames', str(frames),
                   '--model', model, '--keep-fraction', str(keep), '--measure-kernels']
        if amp:
            command.append('--amp')
        started = time.monotonic()
        with (output / (name + '.log')).open('w') as log:
            # Separate processes release each model's VRAM before the next one.
            subprocess.run(command, cwd=PROJECT, check=True, timeout=240, stdout=log, stderr=subprocess.STDOUT)
        elapsed = time.monotonic() - started
        report = json.loads((target / 'report.json').read_text())
        diagnostic = audit(episode, target)
        (target / 'geometry.json').write_text(json.dumps(diagnostic, indent=2, allow_nan=False))
        wall = [frame['wall_inference_ms'] for frame in report['frames']]
        gpu = [frame['cuda_work']['cuda_activity_sum_ms'] for frame in report['frames']]
        row = {'variant': name, 'configuration': {'model': model, 'keep_fraction': keep, 'amp': amp},
               'capture_manifest_sha256': report['capture_manifest_sha256'],
               'checkpoint_sha256': report['checkpoint_sha256'],
               'resolved_config_sha256': report['resolved_config_sha256'],
               'report_sha256': sha256_file(target / 'report.json'),
               'geometry_sha256': sha256_file(target / 'geometry.json'),
               'frames': len(wall), 'cli_wall_s': elapsed,
               'wall_mean_ms': float(np.mean(wall)), 'wall_p95_ms': float(np.percentile(wall, 95)),
               'cuda_activity_mean_ms': float(np.mean(gpu)),
               'period_exceedance_fraction': {str(hz): sum(ms > 1000 / hz for ms in wall) / len(wall)
                                              for hz in (5, 10, 20)},
               'positive_target_geometry_recall': diagnostic['positive_target_geometry_recall'],
               'matched_target_frame_instances': diagnostic['matched_target_frame_instances'],
               'target_frame_instances': diagnostic['target_frame_instances'],
               'peak_allocated_bytes': report['peak_allocated_bytes'],
               'peak_reserved_bytes': report['peak_reserved_bytes'],
               'evidence_directory': name}
        results.append(row)
        print(json.dumps(row), flush=True)
    if len({row['capture_manifest_sha256'] for row in results}) != 1:
        raise ValueError('Pilot capture changed between variants')
    summary = {'kind': 'same_capture_detector_pilot', 'status': 'completed_diagnostic_only',
               'variants': results, 'selection': None, 'measured_perception_replay_ready': False,
               'cost_scope': 'detector invocation CUDA activity only, profiled pass separate from wall pass',
               'limitations': ['No monitoring/switching/segmentation GPU work per decision window',
                               'Positive-target class-agnostic diagnostic uses partial spawned-actor GT',
                               'One short correlated scene, no validation/test split or weather robustness',
                               'Period exceedance is inference-only arithmetic, not online scheduling measurement',
                               'CLI time includes initialization/verification/profiling, not online latency',
                               'CARLA is stopped during inference; not full simulator + model throughput']}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episode', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--frames', type=int, default=2)
    parser.add_argument('--include-camera', action='store_true')
    args = parser.parse_args()
    os.environ.setdefault('CUDA_HOME', str(PROJECT / 'data/runtime/cuda-12.1'))
    os.environ.setdefault('MPLCONFIGDIR', '/tmp/p027-detector-matplotlib')
    bench(args.episode.resolve(), args.output.resolve(), args.frames, args.include_camera)
