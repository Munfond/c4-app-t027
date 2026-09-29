"""View the saved 3D-box predictions of any model on the REAL images / point cloud of any of the 81 VAL frames, read from `data/`.
The detectors themselves (BEVFusion, CRN) need CUDA + mmdet3d and are run on Kaggle; their outputs are the CSVs in exports/L3E and fusion/unified (see GUIDE_RUN_PYTHON_LOCAL.md).

  python tools/local/view_detections.py --idx 40 --models official_cl,our_cl,crn,fused
  python tools/local/view_detections.py --idx 5 --models our_lidar --thr 0.3
models: official_lidar, official_cl, our_lidar, our_cl, crn, fused.  GT boxes are green, predictions are coloured per model."""
import argparse, csv, os, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from nuscenes_local import NuScenesMini, WS, qR, CAMS

SRC = {'official_lidar': 'exports/L3E/pred_lidar_only_ego.csv', 'official_cl': 'exports/L3E/pred_lidar_camera_ego.csv', 'our_lidar': 'exports/L3E/pred_our_lidar_ego.csv',
       'our_cl': 'exports/L3E/pred_our_bevfusion_ego.csv', 'crn': 'exports/L3E/pred_camera_radar_ego.csv', 'fused': 'fusion/unified/unified_pretrained_ego.csv'}
COL = {'official_lidar': '#1f77b4', 'official_cl': '#d62728', 'our_lidar': '#ff7f0e', 'our_cl': '#9467bd', 'crn': '#17becf', 'fused': '#e377c2'}
EDGES = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
ap = argparse.ArgumentParser(); ap.add_argument('--idx', type=int, default=40); ap.add_argument('--models', default='official_cl,our_cl,crn'); ap.add_argument('--thr', type=float, default=0.3)
ap.add_argument('--out', default=os.path.join(WS, 'reports', 'local_runs')); a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
ds = NuScenesMini(); tok = ds.token('val', a.idx); models = [m.strip() for m in a.models.split(',')]


def rows(path, idx, thr=0.0):
    out = []
    for r in csv.DictReader(open(os.path.join(WS, *path.split('/')))):
        if int(r['sample_idx']) == idx and float(r['score']) >= thr:
            out.append([float(r[k]) for k in ('x', 'y', 'z', 'w', 'l', 'h', 'yaw')] + [float(r['score']), r['class']])
    return out


def corners(b):
    x, y, z, w, l, h, yaw = b[:7]; c, s = np.cos(yaw), np.sin(yaw)
    xc = np.array([1, 1, 1, 1, -1, -1, -1, -1]) * l / 2; yc = np.array([1, -1, -1, 1, 1, -1, -1, 1]) * w / 2; zc = np.array([1, 1, -1, -1, 1, 1, -1, -1]) * h / 2
    return np.stack([x + c * xc - s * yc, y + s * xc + c * yc, z + zc], 1)


gt = rows('exports/L3E/gt_ego.csv', a.idx)
Rl, tl = ds.pose(tok); fig = plt.figure(figsize=(26, 9.5)); gs = fig.add_gridspec(2, 4, width_ratios=[1, 1, 1, 1.15])
for k, cam in enumerate(CAMS):
    ax = fig.add_subplot(gs[k // 3, k % 3]); img = Image.open(ds.image_path(tok, cam)).convert('RGB'); W_, H_ = img.size; ax.imshow(img)
    d = ds.key[(tok, cam)]; c = ds.cs[d['calibrated_sensor_token']]; e = ds.ego[d['ego_pose_token']]; K = np.array(c['camera_intrinsic']); Rc, tc = qR(e['rotation']), np.array(e['translation'])
    Rk = qR(c['rotation']); tk = np.array(c['translation'])

    def project(P_ego):                       # ego(lidar time) -> global -> ego(camera time) -> camera
        Pg = (Rl @ P_ego.T).T + tl; Pe = (Rc.T @ (Pg - tc).T).T; Pc = (Rk.T @ (Pe - tk).T).T; uv = (K @ Pc.T).T
        return Pc, uv[:, :2] / np.maximum(uv[:, 2:3], 1e-3)

    for name, boxes, col, lw in [('GT', gt, '#39ff14', 0.8)] + [(m, rows(SRC[m], a.idx, a.thr), COL[m], 1.4) for m in models]:
        for b in boxes:
            Pc, uv = project(corners(b))
            for i, j in EDGES:
                if Pc[i, 2] > 0.1 and Pc[j, 2] > 0.1:
                    ax.plot([uv[i, 0], uv[j, 0]], [uv[i, 1], uv[j, 1]], color=col, lw=lw)
    ax.set_xlim(0, W_); ax.set_ylim(H_, 0); ax.axis('off'); ax.set_title(cam, fontsize=9)
axb = fig.add_subplot(gs[:, 3]); P, _ = ds.keyframe_lidar(tok); axb.set_facecolor('black'); axb.scatter(-P[:, 1], P[:, 0], s=.3, c=np.clip(P[:, 2], -3, 3), cmap='Greys_r', vmin=-3, vmax=3, linewidths=0)
for name, boxes, col, lw in [('GT', gt, '#39ff14', 1.0)] + [(m, rows(SRC[m], a.idx, a.thr), COL[m], 1.3) for m in models]:
    for b in boxes:
        cc = corners(b)[[0, 1, 5, 4, 0]]; axb.plot(-cc[:, 1], cc[:, 0], color=col, lw=lw)
    axb.plot([], [], color=col, label=f'{name} ({len(boxes)})')
axb.set_xlim(-54, 54); axb.set_ylim(-54, 54); axb.set_aspect('equal'); axb.legend(loc='upper right', fontsize=8); axb.set_title(f'LiDAR BEV + boxes (score >= {a.thr})', fontsize=10); axb.plot(0, 0, 'c^')
fig.suptitle(f'VAL frame {a.idx} | {ds.scene[ds.sample[tok]["scene_token"]]["name"]} | token {tok[:8]} | real images from data/ | official checkpoints are contaminated on mini VAL', fontsize=11)
png = os.path.join(a.out, f'detections_val{a.idx}_{"+".join(models)}.png'); fig.savefig(png, dpi=60, bbox_inches='tight'); print('saved', png, '| boxes:', {m: len(rows(SRC[m], a.idx, a.thr)) for m in models}, '| GT', len(gt))
