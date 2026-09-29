"""Stage G data: temporal geometry + flow / future labels for the 404 keyframes of Stage F (same sample order, taken from occ_dataset.npz).

For every keyframe t (ego frame E_t, 200x200 cells of 0.5 m, rows +x, cols +y):
  H[t,k]      row index of keyframe t-(k+1) (k=0..2); when the scene history is shorter, the oldest available keyframe is reused.
  A[t,k], b[t,k]  planar rigid map current-cell (x,y) -> location in the history frame:  q = A @ [x,y] + b   (A = (R_p^T R_c)[:2,:2], b = (R_p^T (t_c - t_p))[:2]).
  FLOW  (2,200,200) m/s : GROUND velocity of the annotated object covering the cell, expressed in E_t axes (static objects ~ 0; not relative to ego). NaN velocity -> not valid.
  FVALID (200,200)      : cells with a valid flow label.
  FUT05 / FUT10         : footprints of all annotated objects at t+0.5 s / t+1.0 s (next keyframes) in E_t (world-anchored), AV05 / AV10 availability.
  FM05 / FM10           : same, restricted to objects moving (speed >= 0.3 m/s) at that future time.
Velocity of an annotation = finite difference of the instance's translation over its previous/next keyframe annotations (the nuScenes devkit rule, max gap 1.5 s)."""
import json, os, sys
import numpy as np

OUT = sys.argv[1]
NPZ = None
for r, d, f in os.walk('/kaggle/input'):
    if 'occ_dataset.npz' in f:
        NPZ = os.path.join(r, 'occ_dataset.npz'); break
V = None
for r, d, f in os.walk('/kaggle/input'):
    if 'v1.0-mini' in d:
        V = r; break
print('occ dataset:', NPZ, '| nuScenes root:', V)
tok = np.load(NPZ, allow_pickle=True)['token']
TAB = os.path.join(V, 'v1.0-mini'); tab = lambda n: json.load(open(os.path.join(TAB, n + '.json')))
sample = {s['token']: s for s in tab('sample')}; sd = tab('sample_data'); ego = {e['token']: e for e in tab('ego_pose')}
inst = {i['token']: i for i in tab('instance')}; cat = {c['token']: c['name'] for c in tab('category')}
annt = {a['token']: a for a in tab('sample_annotation')}; ann_by_sample = {}
for a in annt.values():
    ann_by_sample.setdefault(a['sample_token'], []).append(a)
key_lidar = {d['sample_token']: d for d in sd if d['is_key_frame'] and '/LIDAR_TOP/' in d['filename']}
GEN = {'vehicle.car', 'vehicle.truck', 'vehicle.bus.bendy', 'vehicle.bus.rigid', 'vehicle.trailer', 'vehicle.construction', 'vehicle.motorcycle', 'vehicle.bicycle',
       'human.pedestrian.adult', 'human.pedestrian.child', 'human.pedestrian.construction_worker', 'human.pedestrian.police_officer', 'movable_object.trafficcone', 'movable_object.barrier'}
NC, RES, EXT = 200, 0.5, 50.0
xs = -EXT + (np.arange(NC) + 0.5) * RES; XX, YY = np.meshgrid(xs, xs, indexing='ij')


def qR(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def velocity(a):
    """global xy velocity (m/s) of annotation a, NaN if undefined (devkit rule)."""
    t0 = sample[a['sample_token']]['timestamp'] / 1e6
    prev = annt[a['prev']] if a['prev'] else None; nxt = annt[a['next']] if a['next'] else None
    p0 = np.array(a['translation'])
    if prev and nxt:
        dt = (sample[nxt['sample_token']]['timestamp'] - sample[prev['sample_token']]['timestamp']) / 1e6; d = np.array(nxt['translation']) - np.array(prev['translation'])
    elif nxt:
        dt = (sample[nxt['sample_token']]['timestamp'] / 1e6 - t0); d = np.array(nxt['translation']) - p0
    elif prev:
        dt = (t0 - sample[prev['sample_token']]['timestamp'] / 1e6); d = p0 - np.array(prev['translation'])
    else:
        return np.full(2, np.nan)
    if dt <= 0 or dt > 1.5:
        return np.full(2, np.nan)
    return (d / dt)[:2]


def raster(boxes, values=None):
    """boxes: (cx,cy,w,l,yaw); values: optional per-box vectors -> (mask, value map)."""
    m = np.zeros((NC, NC), bool); vm = None if values is None else np.zeros((len(values[0]) if len(values) else 2, NC, NC), np.float32)
    for i, (cx, cy, w, l, yaw) in enumerate(boxes):
        c, s = np.cos(yaw), np.sin(yaw); r0 = max(0, int((cx - l - w + EXT) / RES) - 2); r1 = min(NC, int((cx + l + w + EXT) / RES) + 3)
        c0 = max(0, int((cy - l - w + EXT) / RES) - 2); c1 = min(NC, int((cy + l + w + EXT) / RES) + 3)
        if r0 >= r1 or c0 >= c1:
            continue
        dx, dy = XX[r0:r1, c0:c1] - cx, YY[r0:r1, c0:c1] - cy
        inside = (np.abs(c * dx + s * dy) <= l / 2) & (np.abs(-s * dx + c * dy) <= w / 2)
        m[r0:r1, c0:c1] |= inside
        if values is not None:
            for ch in range(vm.shape[0]):
                vm[ch, r0:r1, c0:c1][inside] = values[i][ch]
    return m, vm


def boxes_at(sample_token, Rc, tc, want_velocity=False):
    """annotated objects of a keyframe expressed in the ego frame (Rc, tc) of ANOTHER keyframe."""
    out, vel = [], []
    for a in ann_by_sample.get(sample_token, []):
        if cat[inst[a['instance_token']]['category_token']] not in GEN:
            continue
        cen = Rc.T @ (np.array(a['translation']) - tc); Rb = Rc.T @ qR(a['rotation'])
        out.append((cen[0], cen[1], a['size'][0], a['size'][1], float(np.arctan2(Rb[1, 0], Rb[0, 0]))))
        v = velocity(a); vel.append((Rc.T @ np.array([v[0], v[1], 0.0]))[:2] if np.all(np.isfinite(v)) else np.full(2, np.nan))
    return out, vel


N = len(tok); row = {t: i for i, t in enumerate(tok)}
H = np.zeros((N, 3), np.int64); A = np.zeros((N, 3, 2, 2), np.float32); B = np.zeros((N, 3, 2), np.float32)
FLOW = np.zeros((N, 2, NC, NC), np.float16); FVALID = np.zeros((N, NC, NC), bool)
FUT = {h: np.zeros((N, NC, NC), bool) for h in ('05', '10')}; FM = {h: np.zeros((N, NC, NC), bool) for h in ('05', '10')}; AV = {h: np.zeros(N, bool) for h in ('05', '10')}
pose = {}
for t in tok:
    e = ego[key_lidar[t]['ego_pose_token']]; pose[t] = (qR(e['rotation']), np.array(e['translation']))
for i, t in enumerate(tok):
    Rc, tc = pose[t]
    chain = []; cur = t
    for _ in range(3):
        p = sample[cur]['prev']
        if not p:
            break
        chain.append(p); cur = p
    for k in range(3):
        src = chain[k] if k < len(chain) else (chain[-1] if chain else t)
        H[i, k] = row[src]; Rp, tp = pose[src]
        A[i, k] = (Rp.T @ Rc)[:2, :2]; B[i, k] = (Rp.T @ (tc - tp))[:2]
    boxes, vel = boxes_at(t, Rc, tc)
    m, vm = raster(boxes, vel)
    fv = m & np.isfinite(vm[0]) & np.isfinite(vm[1]); FLOW[i] = np.where(fv[None], np.nan_to_num(vm), 0); FVALID[i] = fv
    nxt = t
    for h in ('05', '10'):
        nxt = sample[nxt]['next'] if nxt else ''
        if not nxt:
            continue
        bx, bv = boxes_at(nxt, Rc, tc); FUT[h][i], _ = raster(bx); AV[h][i] = True
        moving = [b for b, v in zip(bx, bv) if np.all(np.isfinite(v)) and np.hypot(*v) >= 0.3]
        FM[h][i], _ = raster(moving)
    if i % 100 == 0:
        print('built', i, '/', N, flush=True)
np.savez_compressed(os.path.join(OUT, 'flow_dataset.npz'), H=H, A=A, B=B, FLOW=FLOW, FVALID=FVALID, FUT05=FUT['05'], FUT10=FUT['10'], FM05=FM['05'], FM10=FM['10'], AV05=AV['05'], AV10=AV['10'])
sp = np.hypot(FLOW[:, 0].astype(np.float32), FLOW[:, 1].astype(np.float32))
print('flow-valid cells / object cells:', int(FVALID.sum()), '| moving cells (>=0.3 m/s):', int(((sp >= 0.3) & FVALID).sum()), '| median speed of moving cells', float(np.median(sp[(sp >= 0.3) & FVALID])))
print('future available 0.5 s:', int(AV['05'].sum()), '1.0 s:', int(AV['10'].sum()), '| FLOW DATASET BUILD PASS')
