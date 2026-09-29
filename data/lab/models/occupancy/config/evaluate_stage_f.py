"""Stage F evaluation on mini VAL (81): learned occupancy variants vs the project's classical occupancy vs detection-derived footprints, on the SAME labels."""
import csv, json, os, sys
import numpy as np
from scipy.io import loadmat, savemat
from scipy.ndimage import binary_dilation
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

HERE = os.path.dirname(os.path.abspath(__file__)); OUTD = os.path.join(HERE, 'out', 'outputs'); RES = os.path.join(HERE, 'results'); os.makedirs(RES, exist_ok=True)
E = os.path.join(HERE, '..', 'exports', 'L3E')
d = np.load(os.path.join(OUTD, 'occ_val_predictions.npz'), allow_pickle=True)
gt = d['gt'].astype(int); N = len(gt)
tokens_l3e = [r['sample_token'] for r in csv.DictReader(open(os.path.join(E, 'samples.csv')))]
assert list(d['token']) == tokens_l3e, 'sample order differs from the L3E exports'
pred = {k[5:]: d[k].astype(int) for k in d.files if k.startswith('pred_')}
cl = loadmat(os.path.join(HERE, '..', 'stage_e', 'classical_out', 'classical_full.mat'))
classical_occ = cl['occ'].astype(bool); classical_radar = cl['rhit'].astype(bool)
K = np.ones((1, 3, 3), bool); dil = lambda a: binary_dilation(a, K)


def binary(po, name):
    go = gt > 0; i = (po & go).sum(); u = (po | go).sum()
    obj = gt == 2
    return dict(system=name, IoU_occupied=round(float(i / u), 4), precision=round(float(i / max(1, po.sum())), 4), recall=round(float(i / go.sum()), 4),
                precision_tol1=round(float((po & dil(go)).sum() / max(1, po.sum())), 4), recall_tol1=round(float((go & dil(po)).sum() / go.sum()), 4),
                object_cells_covered=round(float((po & obj).sum() / obj.sum()), 4), object_cells_covered_tol1=round(float((obj & dil(po)).sum() / obj.sum()), 4),
                occupied_cells_per_frame=round(float(po.sum() / N), 0))


rows = [binary(classical_occ, 'Classical LiDAR occupancy (project buildBevOccupancy, single sweep)'),
        binary(classical_radar, 'Classical radar hits (project rasterizeRadarBev)'),
        binary(classical_occ | classical_radar, 'Classical LiDAR U radar (union)'),
        binary(d['XL'].astype(np.float32)[:, 0] > 0, 'Rule: any obstacle-height LiDAR point (single sweep)')]
names = {'lidar_radar': 'Learned U-Net: LiDAR + radar (our_occupancy.pth)', 'lidar': 'Learned U-Net: LiDAR only', 'radar': 'Learned U-Net: radar only'}
for k, v in pred.items():
    rows.append(binary(v > 0, names[k]))
# object channel: learned occupancy vs detection-derived footprints
xs = -50 + (np.arange(200) + 0.5) * 0.5; XX, YY = np.meshgrid(xs, xs, indexing='ij')


def foot(b):
    m = np.zeros((200, 200), bool)
    for x, y, w, l, yaw in b:
        c, s = np.cos(yaw), np.sin(yaw); dx, dy = XX - x, YY - y; m |= (np.abs(c * dx + s * dy) <= l / 2) & (np.abs(-s * dx + c * dy) <= w / 2)
    return m


def boxes_from_csv(path, thr):
    out = [[] for _ in range(N)]
    for r in csv.DictReader(open(path)):
        if float(r['score']) >= thr:
            out[int(r['sample_idx'])].append((float(r['x']), float(r['y']), float(r['w']), float(r['l']), float(r['yaw'])))
    return out


obj = gt == 2
objrows = []
for nm, p in (('Detection footprints: official Camera+LiDAR (score>=0.5, contaminated)', os.path.join(E, 'pred_lidar_camera_ego.csv')),
              ('Detection footprints: fused CL+CRN (score>=0.5, contaminated)', os.path.join(HERE, '..', 'fusion', 'unified', 'unified_pretrained_ego.csv'))):
    P = np.stack([foot(b) for b in boxes_from_csv(p, 0.5)]); i = (P & obj).sum()
    objrows.append(dict(system=nm, object_IoU=round(float(i / (P | obj).sum()), 4), precision=round(float(i / max(1, P.sum())), 4), recall=round(float(i / obj.sum()), 4)))
for k in ('lidar_radar', 'lidar', 'radar'):
    P = pred[k] == 2; i = (P & obj).sum()
    objrows.append(dict(system=names[k] + ' (object class)', object_IoU=round(float(i / (P | obj).sum()), 4), precision=round(float(i / max(1, P.sum())), 4), recall=round(float(i / obj.sum()), 4)))
m = json.load(open(os.path.join(OUTD, 'occupancy_metrics.json')))
out = dict(binary_occupancy=rows, object_channel=objrows, learned_per_class={k: m['results'][k] for k in ('lidar_radar', 'lidar', 'radar')}, rule_baseline=m['results']['baseline_rule_single_sweep_obstacle_height'])
json.dump(out, open(os.path.join(RES, 'stage_f_metrics.json'), 'w'), indent=2)
print(f"{'binary occupancy (static+object) vs labels':78s} IoU    P     R    P_tol R_tol objCov cells/fr")
for r in rows:
    print(f"{r['system']:78s} {r['IoU_occupied']:.3f} {r['precision']:.3f} {r['recall']:.3f} {r['precision_tol1']:.3f} {r['recall_tol1']:.3f} {r['object_cells_covered']:.3f} {r['occupied_cells_per_frame']:.0f}")
print('\nobject channel:')
for r in objrows:
    print(f"{r['system']:86s} IoU {r['object_IoU']:.3f} P {r['precision']:.3f} R {r['recall']:.3f}")
for k in ('lidar_radar', 'lidar', 'radar'):
    r = m['results'][k]; print(k, {a: r[a] for a in ('IoU_free', 'IoU_static', 'IoU_object', 'mIoU', 'params_M', 'latency_ms_T4', 'reload_identical', 'peak_mem_MB')})

# MATLAB export (ego frame: rows = +x, cols = +y, 0.5 m cells, +/-50 m; classes 0 free, 1 static, 2 object)
savemat(os.path.join(RES, 'occupancy_predictions.mat'), dict(gt=gt.astype(np.uint8), pred_lidar_radar=pred['lidar_radar'].astype(np.uint8), pred_lidar=pred['lidar'].astype(np.uint8), pred_radar=pred['radar'].astype(np.uint8),
                                                             classical_lidar_occ=classical_occ, classical_radar_hit=classical_radar, sample_idx=np.arange(1, N + 1, dtype=float),
                                                             token=np.array(tokens_l3e, dtype=object).reshape(-1, 1), cell_m=0.5, extent_m=50.0,
                                                             legend='class 0 free, 1 static (LiDAR pseudo-GT), 2 object (annotated box footprint); grid rows +x forward, columns +y left'), do_compression=True)
cmap = ListedColormap(['#111111', '#8a8a8a', '#e6a400'])
for idx in (4, 30, 60):
    fig, ax = plt.subplots(1, 5, figsize=(26, 5.6))
    cl3 = np.where(classical_occ[idx], 1, 0)
    panels = [('Label (pseudo-GT static grey, GT objects orange)', gt[idx]), ('Classical LiDAR occupancy (single sweep)', cl3), ('Learned U-Net LiDAR+radar', pred['lidar_radar'][idx]),
              ('Learned U-Net LiDAR only', pred['lidar'][idx]), ('Learned U-Net radar only', pred['radar'][idx])]
    for a, (t, g) in zip(ax, panels):
        a.imshow(g, cmap=cmap, vmin=0, vmax=2, origin='lower', extent=[-50, 50, -50, 50], interpolation='nearest'); a.set_title(t, fontsize=9)
        a.set_xlabel('y left [m]'); a.set_ylabel('x forward [m]')
        a.invert_xaxis()
    fig.suptitle(f'Stage F | nuScenes-mini VAL sample {idx + 1}/81 | static labels are LiDAR-derived pseudo-GT, object labels are annotated boxes', fontsize=11)
    fig.savefig(os.path.join(RES, f'stage_f_compare_sample{idx + 1}.png'), dpi=60, bbox_inches='tight'); plt.close(fig)
print('wrote', RES)
