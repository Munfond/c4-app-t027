"""Run OUR trained temporal / flow network (Stage G, `models/temporal_flow/our_flow.pth`) locally on CPU on real nuScenes-mini frames from `data/`.
Input: the frame and its previous keyframes (up to 3) warped into the current ego frame. Output: occupancy(t), ground-velocity flow (m/s, ego axes), future object occupancy.

  python tools/local/run_flow.py --split val --idx 51            # one frame -> PNG (frame 51 has moving vehicles)
  python tools/local/run_flow.py --split val --all               # whole VAL: reproduces the Stage-G flow numbers
  python tools/local/run_flow.py --variant T1 --split val --idx 51   # single-frame variant for comparison
The flow head is NOT reliable (see models/temporal_flow/README.md); this script exists so you can see that for yourself."""
import argparse, os, sys, time
import numpy as np
import torch
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from nuscenes_local import NuScenesMini, WS, xs
from models import load_flow, warp_history

ap = argparse.ArgumentParser()
ap.add_argument('--split', choices=['train', 'val'], default='val'); ap.add_argument('--idx', type=int, default=51); ap.add_argument('--token', default=None)
ap.add_argument('--variant', choices=['T4', 'T2', 'T1', 'T4_nowarp'], default='T4'); ap.add_argument('--all', action='store_true'); ap.add_argument('--out', default=os.path.join(WS, 'reports', 'local_runs'))
a = ap.parse_args()
path = os.path.join(WS, 'models', 'temporal_flow', 'our_flow.pth' if a.variant == 'T4' else f'variants/our_flow_{a.variant}.pth')
model, ck = load_flow(path); T, warp = ck['T'], ck['warp']
ds = NuScenesMini(); os.makedirs(a.out, exist_ok=True); cache = {}
print(f'model {os.path.relpath(path, WS)} | frames T={T} | ego-motion compensation {warp} | data {ds.root}')


def bev(t):
    if t not in cache:
        cache[t] = torch.from_numpy(ds.bev_inputs(t))
    return cache[t]


def infer(tok):
    frames = [bev(tok)]
    for src, A, b in ds.history(tok, T - 1):
        frames.append(warp_history(bev(src), A, b) if warp else bev(src))
    x = torch.cat(frames[::-1], 0)[None]
    with torch.no_grad():
        o = model(x)[0].numpy()
    o[3:5] *= 10.0
    return o                                                        # 0-2 occupancy logits, 3-4 flow m/s, 5-6 future object logits


def epe_stats(flow, gt, valid):
    sp = np.hypot(gt[0], gt[1]); mov = valid & (sp >= 0.3); sta = valid & (sp < 0.3); e = np.hypot(flow[0] - gt[0], flow[1] - gt[1]); pf = np.hypot(flow[0], flow[1])
    return e[mov], sp[mov], pf[sta]


if a.all:
    toks = ds.by_split[a.split]; E, S0, FF, outs = [], [], [], []; t0 = time.time()
    for i, t in enumerate(toks):
        o = infer(t); outs.append(o); gt, v = ds.gt_flow(t); e, s, ff = epe_stats(o[3:5], gt, v); E.append(e); S0.append(s); FF.append(ff)
        if i % 10 == 0:
            print(f'  {i}/{len(toks)} ({time.time() - t0:.0f}s)', flush=True)
    E, S0, FF = np.concatenate(E), np.concatenate(S0), np.concatenate(FF)
    print(f'{a.split}: {len(toks)} frames | moving cells {len(E)} | EPE {E.mean():.3f} m/s | zero-flow baseline {S0.mean():.3f} m/s | static-object false flow {FF.mean():.3f} m/s')
    ref = os.path.join(WS, 'stage_g', 'out', 'outputs', 'flow_val_predictions.npz')
    if a.split == 'val' and os.path.exists(ref) and a.variant in ('T4', 'T1', 'T2', 'T4_nowarp'):
        k = np.load(ref, allow_pickle=True)[f'out_{a.variant}'].astype(np.float32); O = np.stack(outs)
        print(f'agreement with the Kaggle-GPU outputs: occupancy argmax {(O[:, :3].argmax(1) == k[:, :3].argmax(1)).mean() * 100:.3f}% | mean |flow difference| {np.abs(O[:, 3:5] - k[:, 3:5]).mean():.4f} m/s')
    sys.exit(0)

tok = a.token or ds.token(a.split, a.idx); o = infer(tok); gt, valid = ds.gt_flow(tok); e, s, ff = epe_stats(o[3:5], gt, valid)
occ = o[:3].argmax(0)
print(f'sample {tok} ({a.split}[{a.idx}]) | moving GT cells {len(e)} | EPE {e.mean() if len(e) else float("nan"):.2f} m/s (zero-flow baseline {s.mean() if len(s) else float("nan"):.2f}) | false flow on static objects {ff.mean() if len(ff) else float("nan"):.2f} m/s')
fig, ax = plt.subplots(1, 3, figsize=(20, 6.6)); ax[0].imshow(Image.open(ds.image_path(tok, 'CAM_FRONT'))); ax[0].axis('off'); ax[0].set_title('CAM_FRONT (real image)')


def quiver(axx, fx, fy, mask, title, step=2):
    axx.set_xlim(50, -50); axx.set_ylim(-50, 50); axx.set_aspect('equal'); axx.grid(alpha=.3); axx.set_title(title, fontsize=10); axx.plot(0, 0, 'k^'); axx.set_xlabel('y left [m]'); axx.set_ylabel('x forward [m]')
    r, c = np.where(mask); sl = slice(None, None, step)
    if len(r):
        axx.quiver(xs[c][sl], xs[r][sl], fy[r, c][sl], fx[r, c][sl], np.hypot(fx[r, c], fy[r, c])[sl], angles='xy', scale_units='xy', scale=2.5, cmap='viridis', width=.003, clim=(0, 15))


quiver(ax[1], gt[0], gt[1], valid, 'GT ground-velocity flow (annotated objects); colour = speed m/s')
quiver(ax[2], o[3], o[4], occ == 2, f'{a.variant}: predicted flow at predicted object cells (EPE on moving cells {e.mean() if len(e) else float("nan"):.2f} m/s)')
png = os.path.join(a.out, f'flow_{a.split}{a.idx}_{a.variant}.png'); fig.savefig(png, dpi=65, bbox_inches='tight'); print('saved', png)
