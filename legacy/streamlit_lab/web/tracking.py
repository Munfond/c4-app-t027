"""Tracker đơn giản (tự viết) chạy trên đầu ra của detector qua các keyframe liên tiếp (2 Hz) của mỗi scene val, và đo với GT có instance id.

Thuật toán (tham số chọn trước, KHÔNG tinh chỉnh trên val):
  - đưa detection về hệ toạ độ toàn cục bằng ego pose từng frame (bù chuyển động xe);
  - dự đoán vị trí track bằng vận tốc hằng (làm mượt EMA 0,5);
  - gán Hungarian theo khoảng cách tâm, cổng 3,0 m (xe) / 1,5 m (người và vật nhỏ);
  - track mới từ detection chưa gán, xoá sau 2 frame (1 s) không được gán; chỉ xuất track đã có >= 2 lần khớp hoặc đang khớp.
Đây KHÔNG phải benchmark nuScenes tracking: chỉ số dưới đây là MOTA-lite tự tính trên 81 frame val, dùng để so các nguồn detection với nhau.
"""
import numpy as np
from scipy.optimize import linear_sum_assignment

VEH = {'car', 'truck', 'bus', 'trailer', 'construction_vehicle'}
GATE_VEH, GATE_SMALL, GT_MATCH_M, MAX_MISS, EMA = 3.0, 1.5, 2.0, 2, 0.5


def _scene_sequences(ds):
    """[(scene_name, [idx_val,...])] theo thứ tự thời gian; idx_val = chỉ số trong tập val."""
    seq = {}
    for i, t in enumerate(ds.by_split['val']):
        seq.setdefault(ds.scene[ds.sample[t]['scene_token']]['name'], []).append(i)
    return sorted(seq.items())


def _to_global(ds, tok, xy):
    R, t = ds.pose(tok)
    return (R[:2, :2] @ xy.T).T + t[:2]


def gt_instances(ds, tok, min_pts=5):
    """GT của frame trong hệ toàn cục: [(instance_token, x, y, evaluable)] (evaluable = >= min_pts điểm LiDAR/radar và <= 50 m tính trong ego)."""
    R, t = ds.pose(tok); out = []
    from nuscenes_local import GEN
    for a in ds.ann_by_sample.get(tok, []):
        if ds.cat[ds.inst[a['instance_token']]['category_token']] not in GEN:
            continue
        p = np.array(a['translation']); ego = R.T @ (p - t); ok = (a['num_lidar_pts'] + a['num_radar_pts'] >= min_pts) and np.hypot(ego[0], ego[1]) <= 50
        out.append((a['instance_token'], p[0], p[1], bool(ok)))
    return out


class _Track:
    def __init__(self, tid, pos, k, cls):
        self.id, self.pos, self.vel, self.last, self.hits, self.miss, self.cls = tid, pos, np.zeros(2), k, 1, 0, cls


def run_tracking(ds, det, thr):
    """det: {sample_idx: [[x,y,z,w,l,h,yaw,score,class],...]} (ego frame). Trả (frames, metrics).
    frames[idx] = [(track_id, x_ego, y_ego, cls, age)] chỉ của các track được xuất; metrics: MOTA-lite so với GT."""
    val = ds.by_split['val']; frames = {}; nid = 0
    gt_match_prev = {}; stat = dict(gt=0, fn=0, fp=0, idsw=0, tp=0, tracks=set(), lens={}, gt_inst=set(), frag=0)
    for scene, idxs in _scene_sequences(ds):
        tracks, prev_t, gt_last = [], None, {}
        for k, i in enumerate(idxs):
            tok = val[i]; ts = ds.sample[tok]['timestamp'] / 1e6; dt = (ts - prev_t) if prev_t is not None else 0.5; prev_t = ts
            rows = [b for b in det.get(i, []) if b[7] >= thr]
            dpos = _to_global(ds, tok, np.array([[b[0], b[1]] for b in rows])) if rows else np.zeros((0, 2))
            pred = [tr.pos + tr.vel * (ts - tr.last_ts) if hasattr(tr, 'last_ts') else tr.pos for tr in tracks]
            matched_d, matched_t = set(), set()
            if tracks and len(rows):
                C = np.array([[np.hypot(*(pred[a] - dpos[b])) for b in range(len(rows))] for a in range(len(tracks))])
                for a, b in zip(*linear_sum_assignment(C)):
                    gate = GATE_VEH if rows[b][8] in VEH else GATE_SMALL
                    if C[a, b] <= gate:
                        tr = tracks[a]; new = dpos[b]; span = max(ts - getattr(tr, 'last_ts', ts - dt), 1e-3)
                        tr.vel = EMA * tr.vel + (1 - EMA) * (new - tr.pos) / span; tr.pos = new; tr.last_ts = ts; tr.hits += 1; tr.miss = 0; tr.cls = rows[b][8]
                        matched_d.add(b); matched_t.add(a)
            for a, tr in enumerate(tracks):
                if a not in matched_t:
                    tr.miss += 1
            tracks = [tr for tr in tracks if tr.miss <= MAX_MISS]
            for b in range(len(rows)):
                if b not in matched_d:
                    nid += 1; tr = _Track(nid, dpos[b], k, rows[b][8]); tr.last_ts = ts; tracks.append(tr)
            R, t = ds.pose(tok)
            out = [(tr.id, *(R[:2, :2].T @ (tr.pos - t[:2])), tr.cls, tr.hits) for tr in tracks if tr.miss == 0 and tr.hits >= 2]
            frames[i] = out
            for tr in tracks:
                if tr.miss == 0 and tr.hits >= 2:
                    stat['tracks'].add(tr.id); stat['lens'][tr.id] = stat['lens'].get(tr.id, 0) + 1
            # ---- đánh giá so với GT ----
            gts = gt_instances(ds, tok); ev = [g for g in gts if g[3]]; ign = [g for g in gts if not g[3]]
            outg = np.array([_to_global(ds, tok, np.array([[o[1], o[2]]]))[0] for o in out]) if out else np.zeros((0, 2))
            stat['gt'] += len(ev); used_t, used_g = set(), set()
            if len(ev) and len(out):
                C = np.hypot(*(np.array([[g[1], g[2]] for g in ev])[:, None, :] - outg[None, :, :]).transpose(2, 0, 1))
                for gi, ti in zip(*linear_sum_assignment(C)):
                    if C[gi, ti] <= GT_MATCH_M:
                        used_g.add(gi); used_t.add(ti); inst = ev[gi][0]; stat['gt_inst'].add(inst); stat['tp'] += 1
                        if inst in gt_match_prev and gt_match_prev[inst] != out[ti][0]:
                            stat['idsw'] += 1
                        gt_match_prev[inst] = out[ti][0]
            stat['fn'] += len(ev) - len(used_g)
            for ti in range(len(out)):
                if ti in used_t:
                    continue
                if len(ign) and min(np.hypot(g[1] - outg[ti][0], g[2] - outg[ti][1]) for g in ign) <= GT_MATCH_M:
                    continue
                stat['fp'] += 1
    n = max(stat['gt'], 1); lens = np.array(list(stat['lens'].values())) if stat['lens'] else np.zeros(1)
    m = {'GT (evaluable)': stat['gt'], 'TP': stat['tp'], 'FN': stat['fn'], 'FP': stat['fp'], 'ID switches': stat['idsw'], 'MOTA-lite': round(1 - (stat['fn'] + stat['fp'] + stat['idsw']) / n, 3),
         'recall': round(stat['tp'] / n, 3), 'tracks': len(stat['tracks']), 'mean track length (frames)': round(float(lens.mean()), 2)}
    return frames, m
