"""Stage G evaluation add-ons on mini VAL: detection-derived flow reference, MATLAB export (Level-1 flow contract layout), figures."""
import csv, json, os, zipfile
import numpy as np
from scipy.io import savemat
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__)); OUTD = os.path.join(HERE, 'out', 'outputs'); RES = os.path.join(HERE, 'results'); os.makedirs(RES, exist_ok=True)
E = os.path.join(HERE, '..', 'exports', 'L3E')
d = np.load(os.path.join(OUTD, 'flow_val_predictions.npz'), allow_pickle=True)
N = 81; NC = 200; xs = -50 + (np.arange(NC) + 0.5) * 0.5; XX, YY = np.meshgrid(xs, xs, indexing='ij')
gt_flow = d['gt_flow'].astype(np.float32); gv = d['gt_flow_valid']; gt_occ = d['gt_occ'].astype(int)
sp = np.hypot(gt_flow[:, 0], gt_flow[:, 1]); mov = gv & (sp >= 0.3); sta = gv & (sp < 0.3)
tokens = [r['sample_token'] for r in csv.DictReader(open(os.path.join(E, 'samples.csv')))]
assert list(d['token']) == tokens


def qR(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def load_table(n):
    p = os.path.join(E, 'tables', n + '.json')
    if os.path.exists(p):
        return json.load(open(p, encoding='utf-8'))
    with zipfile.ZipFile(p + '.zip') as z:
        return json.load(z.open(z.namelist()[0]))


_sd = load_table('sample_data'); _ego = {e['token']: e for e in load_table('ego_pose')}
_kf = {x['sample_token']: x for x in _sd if x['is_key_frame'] and '/LIDAR_TOP/' in x['filename']}
_pose = {t: (np.array(_ego[_kf[t]['ego_pose_token']]['translation']), qR(_ego[_kf[t]['ego_pose_token']]['rotation'])) for t in tokens}


def det_csv(path, thr):
    out = [[] for _ in range(N)]
    for r in csv.DictReader(open(path)):
        if float(r['score']) >= thr:
            out[int(r['sample_idx'])].append((float(r['x']), float(r['y']), float(r['w']), float(r['l']), float(r['yaw']), float(r['vx']), float(r['vy'])))
    return out


def det_json(path, thr):
    res = json.load(open(path))['results']; out = [[] for _ in range(N)]
    for i, t in enumerate(tokens):
        tr, R = _pose[t]
        for b in res[t]:
            if b['detection_score'] < thr:
                continue
            c = R.T @ (np.array(b['translation']) - tr); Rb = R.T @ qR(b['rotation']); v = (R.T @ np.array([b['velocity'][0], b['velocity'][1], 0.0]))[:2]
            out[i].append((c[0], c[1], b['size'][0], b['size'][1], float(np.arctan2(Rb[1, 0], Rb[0, 0])), v[0], v[1]))
    return out


def flow_from_boxes(boxes):
    """rasterise box footprints carrying their (ground-velocity, ego-axes) velocity; later boxes overwrite earlier ones. Uncovered cells stay NaN."""
    f = np.full((N, 2, NC, NC), np.nan, np.float32)
    for i in range(N):
        for x, y, w, l, yaw, vx, vy in boxes[i]:
            c, s = np.cos(yaw), np.sin(yaw); dx, dy = XX - x, YY - y
            m = (np.abs(c * dx + s * dy) <= l / 2) & (np.abs(-s * dx + c * dy) <= w / 2)
            f[i, 0][m] = vx; f[i, 1][m] = vy
    return f


def flow_stats(f):
    cov = np.isfinite(f[:, 0]); fz = np.where(cov[:, None], f, 0.0); epe = np.hypot(fz[:, 0] - gt_flow[:, 0], fz[:, 1] - gt_flow[:, 1]); pf = np.hypot(fz[:, 0], fz[:, 1])
    ang = np.rad2deg(np.arccos(np.clip((fz[:, 0] * gt_flow[:, 0] + fz[:, 1] * gt_flow[:, 1]) / np.maximum(pf * sp, 1e-6), -1, 1))); am = gv & (sp >= 0.5) & (pf >= 0.1)
    return dict(EPE_moving_all=round(float(epe[mov].mean()), 3), EPE_moving_where_covered=round(float(epe[mov & cov].mean()), 3), moving_cell_coverage=round(float((mov & cov).sum() / mov.sum()), 3),
                angle_median_deg=round(float(np.median(ang[am])), 1), static_object_false_flow_mean=round(float(pf[sta].mean()), 3))


ref = {}
for nm, (kind, p) in {'Detection-derived flow: official Camera+LiDAR (score>=0.5, contaminated)': ('csv', os.path.join(E, 'pred_lidar_camera_ego.csv')),
                       'Detection-derived flow: fused CL+CRN (score>=0.5, contaminated)': ('csv', os.path.join(HERE, '..', 'fusion', 'unified', 'unified_pretrained_ego.csv')),
                       'Detection-derived flow: our Camera+LiDAR (Stage B, mini-trained, score>=0.3)': ('json', os.path.join(HERE, '..', 'models', 'our_bevfusion_mini', 'predictions', 'our_bevfusion_mini_final_last_results_nusc.json'))}.items():
    thr = 0.3 if 'our' in nm else 0.5
    ref[nm] = flow_stats(flow_from_boxes(det_csv(p, thr) if kind == 'csv' else det_json(p, thr)))
ref['Zero flow (predict no motion)'] = dict(EPE_moving_all=round(float(sp[mov].mean()), 3), EPE_moving_where_covered=None, moving_cell_coverage=1.0, angle_median_deg=None, static_object_false_flow_mean=0.0)
m = json.load(open(os.path.join(OUTD, 'flow_metrics.json')))['results']
learned = {f'Learned {k}': dict(EPE_moving_all=v['flow']['EPE_moving'], angle_median_deg=v['flow']['angle_median_deg'], static_object_false_flow_mean=v['flow']['static_object_false_flow_mean'], mIoU=v['occupancy']['mIoU'], IoU_occupied=v['occupancy']['IoU_occupied']) for k, v in m.items()}
json.dump(dict(learned=learned, reference=ref, gt=dict(moving_cells=int(mov.sum()), static_object_cells=int(sta.sum()), median_moving_speed=round(float(np.median(sp[mov])), 2))), open(os.path.join(RES, 'stage_g_reference.json'), 'w'), indent=2)
print('moving cells', int(mov.sum()), 'median speed', round(float(np.median(sp[mov])), 2), 'm/s')
for k, v in ref.items(): print(f'{k:82s}', v)
for k, v in learned.items(): print(f'{k:82s}', v)

# ---- MATLAB export (Level-1 flow contract: flowX / flowY single, m/s, NaN where not occupied; axes rows +x, cols +y) ----
o = d['out_T4'].astype(np.float32); occ_cls = o[:, :3].argmax(1).astype(np.uint8); occp = occ_cls > 0
flowX = np.where(occp, o[:, 3], np.nan).astype(np.float32); flowY = np.where(occp, o[:, 4], np.nan).astype(np.float32)
sig = lambda z: 1 / (1 + np.exp(-z))
savemat(os.path.join(RES, 'flow_predictions.mat'), dict(occupancy_class=occ_cls, flowX=flowX, flowY=flowY, future_object_prob_0p5s=sig(o[:, 5]).astype(np.float32), future_object_prob_1p0s=sig(o[:, 6]).astype(np.float32),
        gt_occupancy_class=gt_occ.astype(np.uint8), gt_flowX=np.where(gv, gt_flow[:, 0], np.nan).astype(np.float32), gt_flowY=np.where(gv, gt_flow[:, 1], np.nan).astype(np.float32), sample_idx=np.arange(1, N + 1, dtype=float),
        token=np.array(tokens, dtype=object).reshape(-1, 1), cell_m=0.5, extent_m=50.0,
        legend='occupancy_class 0 free / 1 static / 2 object; flow = GROUND velocity (m/s) in the current ego axes (x forward, y left), NaN where the model predicts free; rows = +x, columns = +y'), do_compression=True)
# ---- figure ----
def quiv(ax, fx, fy, mask, title, step=3):
    ax.set_xlim(50, -50); ax.set_ylim(-50, 50); ax.set_aspect('equal'); ax.grid(alpha=.3); ax.set_title(title, fontsize=9); ax.plot(0, 0, 'k^')
    r, c = np.where(mask); sel = slice(None, None, step)
    ax.quiver(xs[c][sel], xs[r][sel], fy[r, c][sel], fx[r, c][sel], np.hypot(fx[r, c], fy[r, c])[sel], angles='xy', scale_units='xy', scale=2.5, cmap='viridis', width=.003, clim=(0, 15))
for idx in [int(i) for i in np.argsort(-mov.sum((1, 2)))[:3]]:
    fig, ax = plt.subplots(1, 4, figsize=(24, 6.2))
    quiv(ax[0], gt_flow[idx, 0], gt_flow[idx, 1], gv[idx], 'GT ground-velocity flow (annotated objects)')
    quiv(ax[1], flowX[idx], flowY[idx], occp[idx] & (occ_cls[idx] == 2), 'Learned T4 flow at predicted object cells')
    fd = flow_from_boxes(det_csv(os.path.join(HERE, '..', 'fusion', 'unified', 'unified_pretrained_ego.csv'), 0.5)); quiv(ax[2], fd[idx, 0], fd[idx, 1], np.isfinite(fd[idx, 0]), 'Detection-derived flow (fused CL+CR, contaminated)')
    ax[3].imshow(np.where(gt_occ[idx] == 2, 2, np.where(occ_cls[idx] == 2, 1, 0)), origin='lower', extent=[-50, 50, -50, 50], cmap='viridis', vmin=0, vmax=2); ax[3].invert_xaxis(); ax[3].set_title('object cells: GT (yellow) vs predicted T4 only (teal)', fontsize=9)
    fig.suptitle(f'Stage G | nuScenes-mini VAL sample {idx + 1}/81 | arrows = ground velocity in ego axes (arrow length ~ speed), colour = speed m/s', fontsize=11)
    fig.savefig(os.path.join(RES, f'stage_g_flow_sample{idx + 1}.png'), dpi=60, bbox_inches='tight'); plt.close(fig)
print('wrote', RES)
