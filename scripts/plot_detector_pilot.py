"""Render measured pilot results. No interpolated quality/safety claims."""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def plot(summary, output):
    rows = summary['variants']
    names = {'lidar-full-fp32': 'BEVFusion L · FP32', 'lidar-half-fp32': 'BEVFusion L · half points',
             'lidar-full-amp': 'BEVFusion L · AMP', 'cl-full-fp32': 'BEVFusion C+L · FP32',
             'cl-full-amp': 'BEVFusion C+L · AMP', 'pp-full-fp32': 'PointPillars · FP32',
             'pp-half-fp32': 'PointPillars · half points', 'pp-full-amp': 'PointPillars · AMP',
             'pp-64-full-amp': 'PointPillars · 64 ch AMP'}
    y = np.arange(len(rows))
    colors = ['#a16a27' if r['variant'].startswith('cl-') else
              '#3368a0' if r['variant'].startswith('pp-') else '#287b78' for r in rows]
    fig, axes = plt.subplots(1, 3, figsize=(14, 6), gridspec_kw={'width_ratios': [1.7, 1.35, 1.3]})
    values = [[r['wall_mean_ms'] for r in rows], [r['cuda_activity_mean_ms'] for r in rows],
              [r['matched_target_frame_instances'] for r in rows]]
    titles = ['Detector wall latency · ms', 'CUDA activity per call · ms', 'Positive target/frame matches']
    for i, ax in enumerate(axes):
        ax.barh(y, values[i], color=colors, height=.58)
        ax.invert_yaxis()
        ax.set_title(titles[i], fontsize=11, loc='left', pad=15)
        ax.set_yticks(y)
        ax.set_yticklabels([names[r['variant']] for r in rows] if i == 0 else [])
        ax.spines[['top', 'right', 'left']].set_visible(False)
        ax.tick_params(axis='y', length=0)
        ax.grid(axis='x', alpha=.15)
        ax.set_axisbelow(True)
        upper = max(values[i] + ([r['wall_p95_ms'] for r in rows] if i == 0 else []))
        ax.set_xlim(0, max(1, upper) * 1.25)
        for row, value in enumerate(values[i]):
            label = f'{value:.1f}' if i != 2 else f'{int(value)}/{rows[row]["target_frame_instances"]}'
            if i == 0:
                ax.text(value - ax.get_xlim()[1] * .02, row, label,
                        ha='right', va='center', fontsize=9, color='white')
            else:
                ax.text(value + ax.get_xlim()[1] * .015, row, label, va='center', fontsize=9)
    axes[0].scatter([r['wall_p95_ms'] for r in rows], y, s=45, facecolors='white', edgecolors='#182b35',
                    label='p95 wall', zorder=3)
    axes[0].legend(loc='lower right', frameon=False, fontsize=9)
    frame_count = rows[0]['frames']
    fig.suptitle(f'Measured detector pilot · same {frame_count} sampled CARLA frames · RTX 2050 4 GB',
                 x=.02, ha='left', fontsize=15, weight='bold')
    fig.text(.02, .04, 'Warmup excluded. CUDA profiled separately; CARLA stopped during inference. Separate sequential sessions.\n'
             'Engine actor GT; static/parked coverage unvalidated. Class-agnostic 2 m match; not mAP, complete precision, online FPS or validated profiles.',
             fontsize=9, color='#4c5862')
    fig.tight_layout(rect=(0, .12, 1, .92), w_pad=2)
    fig.savefig(output, dpi=150, facecolor='white')
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; choose a new file')
    plot(json.loads(args.summary.read_text()), args.output)
