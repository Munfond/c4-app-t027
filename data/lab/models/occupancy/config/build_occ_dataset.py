"""Stage F data: BEV occupancy inputs and labels for all 404 nuScenes-mini keyframes (ego frame, 200x200 cells of 0.5 m, rows +x, cols +y, +/-50 m).

INPUT (single keyframe only, no sweeps):
  LiDAR channels : [log1p(#points with 0.3<z<3.0)/3, (max z +1)/5 where obstacle-height points exist, log1p(#all points)/3, mean intensity/255]
  Radar channels : 5 radars, devkit filter (invalid_state==0, ambig_state==3): [log1p(#hits)/2, mean rcs/50, mean |v_comp|/20]
LABEL (never seen by the model as input):
  2 object : rasterised footprints of ALL annotated boxes of the 10 evaluated categories (real human GT)
  1 static : cell hit by obstacle-height points (0.3<z<3.0 m, ego z=0 is ground) in >= 4 of the 11 ego-motion-compensated sweeps
             (keyframe + up to 10 previous sweeps), and not on/next to an object footprint  (PSEUDO-GT, derived from LiDAR)
  0 free   : everything else (includes cells never observed: occluded / out of range - the label cannot tell them apart)
All thresholds are fixed here, before any model is trained."""
import glob, json, os, sys
import numpy as np
from scipy.ndimage import binary_dilation

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
V = None
for r, d, f in os.walk('/kaggle/input'):
    if 'v1.0-mini' in d:
        V = r; break
ROOT = V; TAB = os.path.join(ROOT, 'v1.0-mini')
tab = lambda n: json.load(open(os.path.join(TAB, n + '.json')))
sample = {s['token']: s for s in tab('sample')}; scene = {s['token']: s for s in tab('scene')}
sd = {d['token']: d for d in tab('sample_data')}; cs = {c['token']: c for c in tab('calibrated_sensor')}; ego = {e['token']: e for e in tab('ego_pose')}
inst = {i['token']: i for i in tab('instance')}; cat = {c['token']: c['name'] for c in tab('category')}
ann = {}
for a in tab('sample_annotation'):
    ann.setdefault(a['sample_token'], []).append(a)
from nuscenes.utils import splits
GEN = {'vehicle.car', 'vehicle.truck', 'vehicle.bus.bendy', 'vehicle.bus.rigid', 'vehicle.trailer', 'vehicle.construction', 'vehicle.motorcycle', 'vehicle.bicycle',
       'human.pedestrian.adult', 'human.pedestrian.child', 'human.pedestrian.construction_worker', 'human.pedestrian.police_officer', 'movable_object.trafficcone', 'movable_object.barrier'}
NC, RES, EXT = 200, 0.5, 50.0
BODY = np.array([[-1.0, 3.7], [-1.1, 1.1]])
TY = {('F', 4): '<f4', ('F', 8): '<f8', ('I', 1): 'i1', ('I', 2): '<i2', ('I', 4): '<i4', ('U', 1): 'u1', ('U', 2): '<u2', ('U', 4): '<u4'}


def qR(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def read_pcd(p):
    with open(p, 'rb') as f:
        h = {}
        while True:
            k, *v = f.readline().decode().strip().split(); h[k] = v
            if k == 'DATA':
                break
        dt = np.dtype([(n, TY[(t, int(s))]) for n, t, s in zip(h['FIELDS'], h['TYPE'], h['SIZE'])])
        return np.frombuffer(f.read(), dtype=dt, count=int(h['POINTS'][0]))


def cells(xy):
    r = np.floor((xy[:, 0] + EXT) / RES).astype(int); c = np.floor((xy[:, 1] + EXT) / RES).astype(int)
    ok = (r >= 0) & (r < NC) & (c >= 0) & (c < NC)
    return r[ok], c[ok], ok


def lidar_to_ego(sdr):
    c = cs[sdr['calibrated_sensor_token']]
    raw = np.fromfile(os.path.join(ROOT, sdr['filename']), dtype=np.float32).reshape(-1, 5)
    return (qR(c['rotation']) @ raw[:, :3].T).T + np.array(c['translation']), raw[:, 3]


def strip_body(P, *extra):
    m = ~((P[:, 0] > BODY[0, 0]) & (P[:, 0] < BODY[0, 1]) & (P[:, 1] > BODY[1, 0]) & (P[:, 1] < BODY[1, 1]))
    return (P[m],) + tuple(e[m] for e in extra)


xs = -EXT + (np.arange(NC) + 0.5) * RES; XX, YY = np.meshgrid(xs, xs, indexing='ij')


def raster_boxes(boxes):
    m = np.zeros((NC, NC), bool)
    for cx, cy, w, l, yaw in boxes:
        c, s = np.cos(yaw), np.sin(yaw); r0 = max(0, int((cx - l - w + EXT) / RES) - 2); r1 = min(NC, int((cx + l + w + EXT) / RES) + 3)
        c0 = max(0, int((cy - l - w + EXT) / RES) - 2); c1 = min(NC, int((cy + l + w + EXT) / RES) + 3)
        if r0 >= r1 or c0 >= c1:
            continue
        dx, dy = XX[r0:r1, c0:c1] - cx, YY[r0:r1, c0:c1] - cy
        u = c * dx + s * dy; v = -s * dx + c * dy
        m[r0:r1, c0:c1] |= (np.abs(u) <= l / 2) & (np.abs(v) <= w / 2)
    return m


mini_train, mini_val = set(splits.mini_train), set(splits.mini_val)
items = []
for t, s in sample.items():
    nm = scene[s['scene_token']]['name']
    if nm in mini_train or nm in mini_val:
        items.append((s['scene_token'], s['timestamp'], t, 'train' if nm in mini_train else 'val', nm))
items.sort()
key_lidar = {d['sample_token']: d for d in sd.values() if d['is_key_frame'] and '/LIDAR_TOP/' in d['filename']}
key_radar = {}
for d in sd.values():
    if d['is_key_frame'] and '/RADAR_' in d['filename']:
        key_radar.setdefault(d['sample_token'], []).append(d)

N = len(items); XL = np.zeros((N, 4, NC, NC), np.float16); XR = np.zeros((N, 3, NC, NC), np.float16); Y = np.zeros((N, NC, NC), np.uint8)
STATS = []
for k, (_, ts, t, split, nm) in enumerate(items):
    kl = key_lidar[t]; ek = ego[kl['ego_pose_token']]; Rk, tk = qR(ek['rotation']), np.array(ek['translation'])
    P, inten = lidar_to_ego(kl); P, inten = strip_body(P, inten)
    obst = (P[:, 2] > 0.3) & (P[:, 2] < 3.0)
    r, c, ok = cells(P[obst, :2]); cnt = np.zeros((NC, NC)); np.add.at(cnt, (r, c), 1)
    mz = np.full((NC, NC), -np.inf); np.maximum.at(mz, (r, c), P[obst, 2][ok])
    ra, ca, oka = cells(P[:, :2]); call = np.zeros((NC, NC)); np.add.at(call, (ra, ca), 1); isum = np.zeros((NC, NC)); np.add.at(isum, (ra, ca), inten[oka])
    XL[k, 0] = np.log1p(cnt) / 3; XL[k, 1] = np.where(np.isfinite(mz), (mz + 1) / 5, 0); XL[k, 2] = np.log1p(call) / 3; XL[k, 3] = np.where(call > 0, isum / np.maximum(call, 1) / 255, 0)
    # radar
    hits = np.zeros((NC, NC)); rcs = np.zeros((NC, NC)); spd = np.zeros((NC, NC))
    for rd in key_radar[t]:
        a = read_pcd(os.path.join(ROOT, rd['filename'])); a = a[(a['invalid_state'] == 0) & (a['ambig_state'] == 3)]
        if len(a) == 0:
            continue
        cr = cs[rd['calibrated_sensor_token']]; Pe = (qR(cr['rotation']) @ np.stack([a['x'], a['y'], a['z']]).astype(float)).T + np.array(cr['translation'])
        rr, cc, okr = cells(Pe[:, :2]); np.add.at(hits, (rr, cc), 1); np.add.at(rcs, (rr, cc), a['rcs'][okr]); np.add.at(spd, (rr, cc), np.hypot(a['vx_comp'], a['vy_comp'])[okr])
    XR[k, 0] = np.log1p(hits) / 2; XR[k, 1] = np.where(hits > 0, rcs / np.maximum(hits, 1) / 50, 0); XR[k, 2] = np.where(hits > 0, spd / np.maximum(hits, 1) / 20, 0)
    # object labels (human GT)
    boxes = []
    for a in ann.get(t, []):
        if cat[inst[a['instance_token']]['category_token']] not in GEN:
            continue
        cen = Rk.T @ (np.array(a['translation']) - tk); Rb = Rk.T @ qR(a['rotation'])
        boxes.append((cen[0], cen[1], a['size'][0], a['size'][1], float(np.arctan2(Rb[1, 0], Rb[0, 0]))))
    obj = raster_boxes(boxes)
    # static pseudo-GT: persistence over 11 ego-motion-compensated sweeps
    persist = (cnt > 0).astype(int); token = kl['prev']; nsw = 0
    while token and nsw < 10:
        sw = sd[token]; ep = ego[sw['ego_pose_token']]
        Pw, _ = lidar_to_ego(sw); Pg = (qR(ep['rotation']) @ Pw.T).T + np.array(ep['translation']); Pk = (Rk.T @ (Pg - tk).T).T
        Pk, = strip_body(Pk); m = (Pk[:, 2] > 0.3) & (Pk[:, 2] < 3.0); rr, cc, _ = cells(Pk[m, :2]); h = np.zeros((NC, NC), bool); h[rr, cc] = True
        persist += h; token = sw['prev']; nsw += 1
    static = (persist >= 4) & ~binary_dilation(obj, np.ones((3, 3), bool))
    Y[k][static] = 1; Y[k][obj] = 2
    STATS.append(dict(idx=k, token=t, split=split, scene=nm, sweeps=nsw, n_obj=len(boxes), obj_cells=int(obj.sum()), static_cells=int(static.sum())))
    if k % 50 == 0:
        print('built', k, '/', N, flush=True)
split = np.array([s['split'] for s in STATS]); tokens = np.array([s['token'] for s in STATS]); scenes = np.array([s['scene'] for s in STATS])
np.savez_compressed(os.path.join(OUT, 'occ_dataset.npz'), XL=XL, XR=XR, Y=Y, split=split, token=tokens, scene=scenes)
json.dump(STATS, open(os.path.join(OUT, 'occ_dataset_stats.json'), 'w'))
tr, va = split == 'train', split == 'val'
print('train', tr.sum(), 'val', va.sum(), '| label frequency train free/static/object:', [round(float((Y[tr] == c).mean()), 4) for c in range(3)], 'val:', [round(float((Y[va] == c).mean()), 4) for c in range(3)])
print('mean sweeps used', np.mean([s['sweeps'] for s in STATS]), '| DATASET BUILD PASS')
