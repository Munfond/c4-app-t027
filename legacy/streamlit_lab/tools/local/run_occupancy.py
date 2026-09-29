"""Run OUR trained BEV-occupancy network (Stage F, `models/occupancy/our_occupancy.pth`) locally on CPU, on real nuScenes-mini data read from `data/`.

  python tools/local/run_occupancy.py --split val --idx 5                 # one frame -> PNG
  python tools/local/run_occupancy.py --split train --idx 100 --variant lidar
  python tools/local/run_occupancy.py --split val --all                   # whole VAL: reproduces the Stage-F metrics
Any of the 404 keyframes works (the network was trained on `train`, evaluated on `val`)."""
import argparse, os, sys, time
import numpy as np
import torch
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from nuscenes_local import NuScenesMini, WS
from models import load_occupancy

ap = argparse.ArgumentParser()
ap.add_argument('--split', choices=['train', 'val'], default='val'); ap.add_argument('--idx', type=int, default=5); ap.add_argument('--token', default=None)
ap.add_argument('--variant', choices=['lidar_radar', 'lidar', 'radar'], default='lidar_radar'); ap.add_argument('--all', action='store_true')
ap.add_argument('--out', default=os.path.join(WS, 'reports', 'local_runs')); ap.add_argument('--no-label', action='store_true', help='skip the (slower) label / metrics computation')
a = ap.parse_args()
ck_path = os.path.join(WS, 'models', 'occupancy', 'our_occupancy.pth' if a.variant == 'lidar_radar' else f'variants/our_occupancy_{a.variant}.pth')
model, ck = load_occupancy(ck_path); ch = ck['channels']
ds = NuScenesMini(); os.makedirs(a.out, exist_ok=True)
print(f'model {os.path.relpath(ck_path, WS)} | channels {ch} | classes {ck["classes"]} | data {ds.root}')


def predict(x):
    with torch.no_grad():
        return model(torch.from_numpy(x[ch])[None])[0].argmax(0).numpy().astype(np.uint8)


def iou(pred, gt):
    r = {}
    for c, n in enumerate(('free', 'static', 'object')):
        i = ((pred == c) & (gt == c)).sum(); u = ((pred == c) | (gt == c)).sum(); r[n] = i / max(1, u)
    po, go = pred > 0, gt > 0; r['occupied'] = (po & go).sum() / max(1, (po | go).sum()); return r


if a.all:
    toks = ds.by_split[a.split]; P, G = [], []; t0 = time.time()
    ref = os.path.join(WS, 'stage_f', 'out', 'outputs', 'occ_val_predictions.npz'); ref = np.load(ref, allow_pickle=True) if (a.split == 'val' and os.path.exists(ref)) else None
    for i, t in enumerate(toks):
        x = ds.bev_inputs(t); P.append(predict(x)); G.append(ds.labels(t))
        if i % 10 == 0:
            print(f'  {i}/{len(toks)} ({time.time() - t0:.0f}s)', flush=True)
    P, G = np.stack(P), np.stack(G); ious = [((P == c) & (G == c)).sum() / ((P == c) | (G == c)).sum() for c in range(3)]
    print(f'{a.split}: {len(toks)} frames | IoU free {ious[0]:.4f} static {ious[1]:.4f} object {ious[2]:.4f} | mIoU {np.mean(ious):.4f} | IoU occupied {(((P > 0) & (G > 0)).sum() / ((P > 0) | (G > 0)).sum()):.4f}')
    if ref is not None and a.variant == 'lidar_radar':
        kp = ref['pred_lidar_radar']; print(f'agreement with the Kaggle-GPU predictions: {(P == kp).mean() * 100:.3f}% of cells | labels identical to the Kaggle labels: {(G == ref["gt"]).mean() * 100:.3f}% of cells')
    sys.exit(0)

tok = a.token or ds.token(a.split, a.idx)
x = ds.bev_inputs(tok); t0 = time.time(); pred = predict(x); dt = time.time() - t0
print(f'sample {tok} ({a.split}[{a.idx}], scene {ds.scene[ds.sample[tok]["scene_token"]]["name"]}) | inference {dt * 1000:.0f} ms on CPU | predicted cells: static {(pred == 1).sum()}, object {(pred == 2).sum()}')
cmap = ListedColormap(['#111111', '#8a8a8a', '#e6a400']); fig, ax = plt.subplots(1, 4 if not a.no_label else 3, figsize=(24 if not a.no_label else 19, 6.2))
ax[0].imshow(Image.open(ds.image_path(tok, 'CAM_FRONT'))); ax[0].axis('off'); ax[0].set_title('CAM_FRONT (real image)')
ax[1].imshow(np.where(x[0] > 0, 1, 0), cmap='gray', origin='lower', extent=[-50, 50, -50, 50]); ax[1].set_title('input: LiDAR obstacle-height hits (1 sweep)')
show = [(2, 'prediction (our_occupancy.pth)', pred)]
if not a.no_label:
    lab = ds.labels(tok); m = iou(pred, lab); show = [(2, 'label (annotated objects + LiDAR pseudo-GT static)', lab), (3, f'prediction: IoU static {m["static"]:.2f}, object {m["object"]:.2f}, occupied {m["occupied"]:.2f}', pred)]
    print('frame IoU:', {k: round(float(v), 3) for k, v in m.items()})
for k, t_, g in show:
    ax[k].imshow(g, cmap=cmap, vmin=0, vmax=2, origin='lower', extent=[-50, 50, -50, 50], interpolation='nearest'); ax[k].set_title(t_, fontsize=10)
for k in range(1, len(ax)):
    ax[k].invert_xaxis(); ax[k].set_xlabel('y left [m]'); ax[k].set_ylabel('x forward [m]')
png = os.path.join(a.out, f'occupancy_{a.split}{a.idx}_{a.variant}.png'); fig.savefig(png, dpi=70, bbox_inches='tight'); print('saved', png)
