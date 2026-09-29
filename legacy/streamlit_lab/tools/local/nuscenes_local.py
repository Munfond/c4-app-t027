"""Local (CPU) access to the nuScenes-mini folder `data/` and the exact BEV inputs / labels used by Stages F and G.

Conventions (identical to the Kaggle pipeline, so local results can be compared with the saved ones):
  ego frame: x forward, y left, z up; BEV grid 200 x 200 cells of 0.5 m, rows = +x, columns = +y, +/-50 m.
  sample order: mini_train U mini_val scenes sorted by (scene_token, timestamp); `split='val'` index 0..80 equals the sample_idx of every export in this workspace.
"""
import json, os
import numpy as np
from scipy.ndimage import binary_dilation

WS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA = os.environ.get('NUSC_ROOT', os.path.join(WS, 'data'))
MINI_TRAIN = ['scene-0061', 'scene-0553', 'scene-0655', 'scene-0757', 'scene-0796', 'scene-1077', 'scene-1094', 'scene-1100']
MINI_VAL = ['scene-0103', 'scene-0916']
NC, RES, EXT = 200, 0.5, 50.0
BODY = np.array([[-1.0, 3.7], [-1.1, 1.1]])
GEN = {'vehicle.car', 'vehicle.truck', 'vehicle.bus.bendy', 'vehicle.bus.rigid', 'vehicle.trailer', 'vehicle.construction', 'vehicle.motorcycle', 'vehicle.bicycle',
       'human.pedestrian.adult', 'human.pedestrian.child', 'human.pedestrian.construction_worker', 'human.pedestrian.police_officer', 'movable_object.trafficcone', 'movable_object.barrier'}
CAMS = ['CAM_FRONT_LEFT', 'CAM_FRONT', 'CAM_FRONT_RIGHT', 'CAM_BACK_LEFT', 'CAM_BACK', 'CAM_BACK_RIGHT']
_TY = {('F', 4): '<f4', ('F', 8): '<f8', ('I', 1): 'i1', ('I', 2): '<i2', ('I', 4): '<i4', ('U', 1): 'u1', ('U', 2): '<u2', ('U', 4): '<u4'}
xs = -EXT + (np.arange(NC) + 0.5) * RES
XX, YY = np.meshgrid(xs, xs, indexing='ij')


def qR(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def read_pcd(path):
    with open(path, 'rb') as f:
        h = {}
        while True:
            k, *v = f.readline().decode().strip().split(); h[k] = v
            if k == 'DATA':
                break
        dt = np.dtype([(n, _TY[(t, int(s))]) for n, t, s in zip(h['FIELDS'], h['TYPE'], h['SIZE'])])
        return np.frombuffer(f.read(), dtype=dt, count=int(h['POINTS'][0]))


class NuScenesMini:
    def __init__(self, root=DATA):
        self.root = root; tab = lambda n: json.load(open(os.path.join(root, 'v1.0-mini', n + '.json'), encoding='utf-8'))
        self.sample = {s['token']: s for s in tab('sample')}; self.scene = {s['token']: s for s in tab('scene')}
        self.sd = {d['token']: d for d in tab('sample_data')}; self.cs = {c['token']: c for c in tab('calibrated_sensor')}; self.ego = {e['token']: e for e in tab('ego_pose')}
        self.inst = {i['token']: i for i in tab('instance')}; self.cat = {c['token']: c['name'] for c in tab('category')}; self.annt = {a['token']: a for a in tab('sample_annotation')}
        self.ann_by_sample = {}
        for a in self.annt.values():
            self.ann_by_sample.setdefault(a['sample_token'], []).append(a)
        self.key = {}                                    # (sample_token, channel) -> keyframe sample_data
        for d in self.sd.values():
            if d['is_key_frame']:
                self.key[(d['sample_token'], d['filename'].split('/')[1])] = d
        items = []
        for t, s in self.sample.items():
            nm = self.scene[s['scene_token']]['name']
            if nm in MINI_TRAIN or nm in MINI_VAL:
                items.append((s['scene_token'], s['timestamp'], t, 'train' if nm in MINI_TRAIN else 'val', nm))
        items.sort()
        self.order = [(t, sp, nm) for _, _, t, sp, nm in items]
        self.by_split = {sp: [t for t, s, _ in self.order if s == sp] for sp in ('train', 'val')}

    # ---- indexing ----
    def token(self, split, idx):
        return self.by_split[split][idx]

    def pose(self, token):
        e = self.ego[self.key[(token, 'LIDAR_TOP')]['ego_pose_token']]
        return qR(e['rotation']), np.array(e['translation'])

    def image_path(self, token, cam):
        return os.path.join(self.root, self.key[(token, cam)]['filename'])

    # ---- sensors in the ego frame of the keyframe ----
    def lidar_ego(self, sd_rec):
        c = self.cs[sd_rec['calibrated_sensor_token']]
        raw = np.fromfile(os.path.join(self.root, sd_rec['filename']), dtype=np.float32).reshape(-1, 5)
        return (qR(c['rotation']) @ raw[:, :3].T).T + np.array(c['translation']), raw[:, 3]

    def keyframe_lidar(self, token):
        return self.lidar_ego(self.key[(token, 'LIDAR_TOP')])

    def keyframe_radar(self, token, chans=('RADAR_FRONT', 'RADAR_FRONT_LEFT', 'RADAR_FRONT_RIGHT', 'RADAR_BACK_LEFT', 'RADAR_BACK_RIGHT')):
        out = []
        for ch in chans:
            d = self.key[(token, ch)]; a = read_pcd(os.path.join(self.root, d['filename'])); a = a[(a['invalid_state'] == 0) & (a['ambig_state'] == 3)]
            if len(a) == 0:
                continue
            c = self.cs[d['calibrated_sensor_token']]
            P = (qR(c['rotation']) @ np.stack([a['x'], a['y'], a['z']]).astype(float)).T + np.array(c['translation'])
            out.append((P, a['rcs'].astype(float), np.hypot(a['vx_comp'], a['vy_comp']).astype(float)))
        return out

    # ---- BEV grid helpers ----
    @staticmethod
    def cells(xy):
        r = np.floor((xy[:, 0] + EXT) / RES).astype(int); c = np.floor((xy[:, 1] + EXT) / RES).astype(int); ok = (r >= 0) & (r < NC) & (c >= 0) & (c < NC)
        return r[ok], c[ok], ok

    @staticmethod
    def strip_body(P, *extra):
        m = ~((P[:, 0] > BODY[0, 0]) & (P[:, 0] < BODY[0, 1]) & (P[:, 1] > BODY[1, 0]) & (P[:, 1] < BODY[1, 1]))
        return (P[m],) + tuple(e[m] for e in extra)

    def bev_inputs(self, token):
        """(7,200,200) float32: 4 LiDAR channels (single keyframe sweep) + 3 radar channels, exactly as in build_occ_dataset.py."""
        P, inten = self.keyframe_lidar(token); P, inten = self.strip_body(P, inten)
        obst = (P[:, 2] > 0.3) & (P[:, 2] < 3.0); r, c, ok = self.cells(P[obst, :2])
        cnt = np.zeros((NC, NC)); np.add.at(cnt, (r, c), 1); mz = np.full((NC, NC), -np.inf); np.maximum.at(mz, (r, c), P[obst, 2][ok])
        ra, ca, oka = self.cells(P[:, :2]); call = np.zeros((NC, NC)); np.add.at(call, (ra, ca), 1); isum = np.zeros((NC, NC)); np.add.at(isum, (ra, ca), inten[oka])
        x = np.zeros((7, NC, NC), np.float32)
        x[0] = np.log1p(cnt) / 3; x[1] = np.where(np.isfinite(mz), (mz + 1) / 5, 0); x[2] = np.log1p(call) / 3; x[3] = np.where(call > 0, isum / np.maximum(call, 1) / 255, 0)
        hits = np.zeros((NC, NC)); rcs = np.zeros((NC, NC)); spd = np.zeros((NC, NC))
        for Pe, rc, sp in self.keyframe_radar(token):
            rr, cc, okr = self.cells(Pe[:, :2]); np.add.at(hits, (rr, cc), 1); np.add.at(rcs, (rr, cc), rc[okr]); np.add.at(spd, (rr, cc), sp[okr])
        x[4] = np.log1p(hits) / 2; x[5] = np.where(hits > 0, rcs / np.maximum(hits, 1) / 50, 0); x[6] = np.where(hits > 0, spd / np.maximum(hits, 1) / 20, 0)
        return x

    # ---- ground truth ----
    def boxes(self, token, ref_token=None):
        """annotated objects of `token` in the ego frame of `ref_token` (default: itself): list of (cx, cy, w, l, yaw)."""
        R, t0 = self.pose(ref_token or token); out = []
        for a in self.ann_by_sample.get(token, []):
            if self.cat[self.inst[a['instance_token']]['category_token']] not in GEN:
                continue
            c = R.T @ (np.array(a['translation']) - t0); Rb = R.T @ qR(a['rotation']); out.append((c[0], c[1], a['size'][0], a['size'][1], float(np.arctan2(Rb[1, 0], Rb[0, 0]))))
        return out

    @staticmethod
    def raster(boxes, values=None):
        m = np.zeros((NC, NC), bool); vm = None if values is None else np.zeros((2, NC, NC), np.float32)
        for i, (cx, cy, w, l, yaw) in enumerate(boxes):
            c, s = np.cos(yaw), np.sin(yaw); r0 = max(0, int((cx - l - w + EXT) / RES) - 2); r1 = min(NC, int((cx + l + w + EXT) / RES) + 3)
            c0 = max(0, int((cy - l - w + EXT) / RES) - 2); c1 = min(NC, int((cy + l + w + EXT) / RES) + 3)
            if r0 >= r1 or c0 >= c1:
                continue
            dx, dy = XX[r0:r1, c0:c1] - cx, YY[r0:r1, c0:c1] - cy; inside = (np.abs(c * dx + s * dy) <= l / 2) & (np.abs(-s * dx + c * dy) <= w / 2)
            m[r0:r1, c0:c1] |= inside
            if values is not None:
                for ch in range(2):
                    vm[ch, r0:r1, c0:c1][inside] = values[i][ch]
        return m, vm

    def labels(self, token):
        """(200,200) uint8: 0 free, 1 static (LiDAR pseudo-GT, >= 4 of 11 ego-motion-compensated sweeps), 2 object (annotated footprint). Needs `sweeps/LIDAR_TOP`."""
        Rk, tk = self.pose(token); kl = self.key[(token, 'LIDAR_TOP')]
        P, _ = self.keyframe_lidar(token); P, = self.strip_body(P)
        m = (P[:, 2] > 0.3) & (P[:, 2] < 3.0); r, c, _ = self.cells(P[m, :2]); persist = np.zeros((NC, NC), int); h = np.zeros((NC, NC), bool); h[r, c] = True; persist += h
        tok, n = kl['prev'], 0
        while tok and n < 10:
            sw = self.sd[tok]; ep = self.ego[sw['ego_pose_token']]; Pw, _ = self.lidar_ego(sw)
            Pg = (qR(ep['rotation']) @ Pw.T).T + np.array(ep['translation']); Pk = (Rk.T @ (Pg - tk).T).T; Pk, = self.strip_body(Pk)
            m = (Pk[:, 2] > 0.3) & (Pk[:, 2] < 3.0); rr, cc, _ = self.cells(Pk[m, :2]); h = np.zeros((NC, NC), bool); h[rr, cc] = True; persist += h; tok = sw['prev']; n += 1
        obj, _ = self.raster(self.boxes(token))
        static = (persist >= 4) & ~binary_dilation(obj, np.ones((3, 3), bool))
        y = np.zeros((NC, NC), np.uint8); y[static] = 1; y[obj] = 2
        return y

    def _velocity(self, a):
        ts = lambda t: self.sample[t]['timestamp'] / 1e6; t0 = ts(a['sample_token']); prev = self.annt[a['prev']] if a['prev'] else None; nxt = self.annt[a['next']] if a['next'] else None; p0 = np.array(a['translation'])
        if prev and nxt:
            dt = ts(nxt['sample_token']) - ts(prev['sample_token']); d = np.array(nxt['translation']) - np.array(prev['translation'])
        elif nxt:
            dt = ts(nxt['sample_token']) - t0; d = np.array(nxt['translation']) - p0
        elif prev:
            dt = t0 - ts(prev['sample_token']); d = p0 - np.array(prev['translation'])
        else:
            return np.full(2, np.nan)
        return np.full(2, np.nan) if (dt <= 0 or dt > 1.5) else (d / dt)[:2]

    def gt_flow(self, token):
        """(2,200,200) ground-velocity flow (m/s, ego axes at t) and (200,200) validity mask, from the annotated objects."""
        R, _ = self.pose(token); boxes, vel = [], []
        for a in self.ann_by_sample.get(token, []):
            if self.cat[self.inst[a['instance_token']]['category_token']] not in GEN:
                continue
            c = self.pose(token)[0].T @ (np.array(a['translation']) - self.pose(token)[1]); Rb = R.T @ qR(a['rotation']); boxes.append((c[0], c[1], a['size'][0], a['size'][1], float(np.arctan2(Rb[1, 0], Rb[0, 0]))))
            v = self._velocity(a); vel.append((R.T @ np.array([v[0], v[1], 0.0]))[:2] if np.all(np.isfinite(v)) else np.full(2, np.nan))
        m, vm = self.raster(boxes, vel) if boxes else (np.zeros((NC, NC), bool), np.zeros((2, NC, NC), np.float32))
        valid = m & np.isfinite(vm[0]) & np.isfinite(vm[1])
        return np.where(valid[None], np.nan_to_num(vm), 0).astype(np.float32), valid

    # ---- temporal geometry for Stage G ----
    def history(self, token, n=3):
        """rows (t-1..t-n): (history_token, A(2x2), b(2)) mapping current-frame cell (x,y) -> location in the history frame; oldest available frame is reused when the scene is short."""
        chain, cur = [], token
        for _ in range(n):
            p = self.sample[cur]['prev']
            if not p:
                break
            chain.append(p); cur = p
        Rc, tc = self.pose(token); out = []
        for k in range(n):
            src = chain[k] if k < len(chain) else (chain[-1] if chain else token); Rp, tp = self.pose(src)
            out.append((src, (Rp.T @ Rc)[:2, :2].astype(np.float32), (Rp.T @ (tc - tp))[:2].astype(np.float32)))
        return out
