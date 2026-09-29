"""Vẽ và tính cho từng chức năng của web. Không phụ thuộc streamlit: mỗi hàm trả về (figure, số liệu) để app.py hiển thị.
Tái dùng tools/local (cùng code với các script chạy dòng lệnh), không sao chép logic dựng input/nhãn."""
import csv, json, os, sys, time
import numpy as np
import torch
from matplotlib.figure import Figure
from matplotlib.colors import ListedColormap
from PIL import Image

WEB = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(WEB)
sys.path.insert(0, os.path.join(WS, 'tools', 'local'))
from nuscenes_local import NuScenesMini, CAMS, xs, qR          # noqa: E402
from models import load_occupancy, load_flow, warp_history      # noqa: E402

RADARS = ['RADAR_FRONT', 'RADAR_FRONT_LEFT', 'RADAR_FRONT_RIGHT', 'RADAR_BACK_LEFT', 'RADAR_BACK_RIGHT']
RADAR_COL = ['#d62728', '#ff7f0e', '#2ca02c', '#1f77b4', '#9467bd']
OCC_FILES = {'lidar_radar': 'occupancy/our_occupancy.pth', 'lidar': 'occupancy/variants/our_occupancy_lidar.pth', 'radar': 'occupancy/variants/our_occupancy_radar.pth'}
FLOW_FILES = {'T4': 'temporal_flow/our_flow.pth', 'T2': 'temporal_flow/variants/our_flow_T2.pth', 'T1': 'temporal_flow/variants/our_flow_T1.pth', 'T4_nowarp': 'temporal_flow/variants/our_flow_T4_nowarp.pth'}
DET_SRC = {'official_lidar': 'exports/L3E/pred_lidar_only_ego.csv', 'official_cl': 'exports/L3E/pred_lidar_camera_ego.csv', 'our_lidar': 'exports/L3E/pred_our_lidar_ego.csv',
           'our_cl': 'exports/L3E/pred_our_bevfusion_ego.csv', 'crn': 'exports/L3E/pred_camera_radar_ego.csv', 'fused': 'fusion/unified/unified_pretrained_ego.csv'}
DET_COL = {'official_lidar': '#1f77b4', 'official_cl': '#d62728', 'our_lidar': '#ff7f0e', 'our_cl': '#9467bd', 'crn': '#17becf', 'fused': '#e377c2'}
EDGES = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
OCC_CMAP = ListedColormap(['#111111', '#8a8a8a', '#e6a400'])
EXT = [-50, 50, -50, 50]


def _bev_axes(ax, title):
    ax.set_title(title, fontsize=10); ax.invert_xaxis(); ax.set_xlabel('y trái [m]'); ax.set_ylabel('x tiến [m]'); ax.set_aspect('equal')


# ---------------- nạp một lần ----------------
def load_dataset():
    return NuScenesMini()


def load_occ_model(variant):
    return load_occupancy(os.path.join(WS, 'models', *OCC_FILES[variant].split('/')))


def load_flow_model(variant):
    return load_flow(os.path.join(WS, 'models', *FLOW_FILES[variant].split('/')))


def read_det_csv(name):
    """{sample_idx: [x,y,z,w,l,h,yaw,score,class]} của một model (chỉ 81 frame val)."""
    out = {}
    for r in csv.DictReader(open(os.path.join(WS, *DET_SRC[name].split('/')))):
        out.setdefault(int(r['sample_idx']), []).append([float(r[k]) for k in ('x', 'y', 'z', 'w', 'l', 'h', 'yaw', 'score')] + [r['class']])
    return out


def read_gt_csv():
    out = {}
    for r in csv.DictReader(open(os.path.join(WS, 'exports', 'L3E', 'gt_ego.csv'))):
        out.setdefault(int(r['sample_idx']), []).append([float(r[k]) for k in ('x', 'y', 'z', 'w', 'l', 'h', 'yaw')] + [1.0, r['class']])
    return out


def read_json(rel):
    p = os.path.join(WS, *rel.split('/'))
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else None


# ---------------- suy luận ----------------
def predict_occ(model, ck, x):
    t0 = time.time()
    with torch.no_grad():
        logits = model(torch.from_numpy(x[ck['channels']])[None])[0]
    pred = logits.argmax(0).numpy().astype(np.uint8)
    return pred, (time.time() - t0) * 1000


def iou_frame(pred, gt):
    r = {}
    for c, n in enumerate(('free', 'static', 'object')):
        i = ((pred == c) & (gt == c)).sum(); u = ((pred == c) | (gt == c)).sum(); r[n] = float(i / max(1, u))
    r['occupied'] = float(((pred > 0) & (gt > 0)).sum() / max(1, ((pred > 0) | (gt > 0)).sum()))
    return r


def predict_flow(model, ck, ds, bev_fn, tok):
    T, warp = ck['T'], ck['warp']; t0 = time.time(); frames = [torch.from_numpy(bev_fn(tok))]
    for src, A, b in ds.history(tok, T - 1):
        h = torch.from_numpy(bev_fn(src)); frames.append(warp_history(h, A, b) if warp else h)
    x = torch.cat(frames[::-1], 0)[None]
    with torch.no_grad():
        o = model(x)[0].numpy()
    o[3:5] *= 10.0
    return o, (time.time() - t0) * 1000


# ---------------- hình ----------------
def fig_cameras(ds, tok):
    return [(cam, Image.open(ds.image_path(tok, cam)).convert('RGB')) for cam in CAMS]


def fig_lidar_radar(ds, tok, show_lidar=True, radar_sel=RADARS, arrows=True):
    t0 = time.time(); P, _ = ds.keyframe_lidar(tok); fig = Figure(figsize=(9, 9)); ax = fig.subplots()
    ax.set_facecolor('black')
    if show_lidar:
        ax.scatter(P[:, 1], P[:, 0], s=0.3, c=np.clip(P[:, 2], -3, 3), cmap='Greys_r', vmin=-3, vmax=3, linewidths=0)
    n_rad = {}
    for ch in radar_sel:
        rr = ds.keyframe_radar(tok, chans=(ch,)); k = RADARS.index(ch)
        if not rr:
            n_rad[ch] = 0; continue
        Pr, _, sp = rr[0]; n_rad[ch] = len(Pr); ax.scatter(Pr[:, 1], Pr[:, 0], s=18, c=RADAR_COL[k], label=f'{ch} ({len(Pr)})')
    ax.plot(0, 0, 'c^'); ax.set_xlim(60, -60); ax.set_ylim(-60, 60); ax.set_aspect('equal'); ax.set_xlabel('y trái [m]'); ax.set_ylabel('x tiến [m]')
    ax.set_title(f'LiDAR ({len(P)} điểm) + radar (hệ ego)'); ax.legend(loc='lower left', fontsize=8)
    return fig, {'lidar_points': int(len(P)), 'radar_points': n_rad, 'ms': (time.time() - t0) * 1000}


def fig_inputs_bev(x):
    names = ['LiDAR: log số điểm vật cản', 'LiDAR: độ cao max', 'LiDAR: log mọi điểm', 'LiDAR: cường độ', 'Radar: log số điểm', 'Radar: RCS', 'Radar: tốc độ']
    fig = Figure(figsize=(18, 5.2)); axs = fig.subplots(2, 4).ravel()
    for i in range(7):
        axs[i].imshow(x[i], origin='lower', extent=EXT, cmap='magma', interpolation='nearest'); _bev_axes(axs[i], names[i])
    axs[7].axis('off'); fig.tight_layout()
    return fig


def fig_occupancy(ds, tok, pred, gt=None, iou=None):
    cols = 3 if gt is not None else 2; fig = Figure(figsize=(6.5 * cols, 6.2)); axs = fig.subplots(1, cols)
    axs[0].imshow(Image.open(ds.image_path(tok, 'CAM_FRONT'))); axs[0].axis('off'); axs[0].set_title('CAM_FRONT (ảnh thật)')
    pan = ([(gt, 'nhãn: footprint GT + static pseudo-GT từ LiDAR')] if gt is not None else []) + [(pred, 'dự đoán U-Net' + (f'  (IoU static {iou["static"]:.2f}, object {iou["object"]:.2f})' if iou else ''))]
    for ax, (g, t) in zip(axs[1:], pan):
        ax.imshow(g, cmap=OCC_CMAP, vmin=0, vmax=2, origin='lower', extent=EXT, interpolation='nearest'); _bev_axes(ax, t)
    fig.tight_layout()
    return fig


def fig_flow(ds, tok, o, gt, valid):
    occ = o[:3].argmax(0); fig = Figure(figsize=(20, 6.6)); axs = fig.subplots(1, 3)
    axs[0].imshow(Image.open(ds.image_path(tok, 'CAM_FRONT'))); axs[0].axis('off'); axs[0].set_title('CAM_FRONT (ảnh thật)')

    def quiver(ax, fx, fy, mask, title):
        ax.set_xlim(50, -50); ax.set_ylim(-50, 50); ax.set_aspect('equal'); ax.grid(alpha=.3); ax.set_title(title, fontsize=10); ax.plot(0, 0, 'k^'); ax.set_xlabel('y trái [m]'); ax.set_ylabel('x tiến [m]')
        r, c = np.where(mask)
        if len(r):
            ax.quiver(xs[c][::2], xs[r][::2], fy[r, c][::2], fx[r, c][::2], np.hypot(fx[r, c], fy[r, c])[::2], angles='xy', scale_units='xy', scale=2.5, cmap='viridis', width=.003, clim=(0, 15))
    quiver(axs[1], gt[0], gt[1], valid, 'GT: vận tốc mặt đất (màu = m/s)')
    quiver(axs[2], o[3], o[4], occ == 2, 'Dự đoán flow tại ô object dự đoán')
    fig.tight_layout()
    return fig


def flow_stats(o, gt, valid):
    sp = np.hypot(gt[0], gt[1]); mov = valid & (sp >= 0.3); sta = valid & (sp < 0.3)
    e = np.hypot(o[3] - gt[0], o[4] - gt[1])
    return {'moving_cells': int(mov.sum()), 'EPE': float(e[mov].mean()) if mov.any() else None, 'zero_flow_baseline': float(sp[mov].mean()) if mov.any() else None,
            'false_flow_static': float(np.hypot(o[3], o[4])[sta].mean()) if sta.any() else None}


def _corners(b):
    x, y, z, w, l, h, yaw = b[:7]; c, s = np.cos(yaw), np.sin(yaw)
    xc = np.array([1, 1, 1, 1, -1, -1, -1, -1]) * l / 2; yc = np.array([1, -1, -1, 1, 1, -1, -1, 1]) * w / 2; zc = np.array([1, 1, -1, -1, 1, 1, -1, -1]) * h / 2
    return np.stack([x + c * xc - s * yc, y + s * xc + c * yc, z + zc], 1)


def fig_detections(ds, tok, idx, models, det, gt_rows, thr):
    """6 ảnh camera thật với hộp 3D chiếu lên (xanh lá = GT) + BEV LiDAR. Trả (fig, {model: số hộp}, GT)."""
    Rl, tl = ds.pose(tok); fig = Figure(figsize=(26, 9.5)); gs = fig.add_gridspec(2, 4, width_ratios=[1, 1, 1, 1.15])
    sets = [('GT', gt_rows.get(idx, []), '#39ff14', 0.8)] + [(m, [b for b in det[m].get(idx, []) if b[7] >= thr], DET_COL[m], 1.4) for m in models]
    for k, cam in enumerate(CAMS):
        ax = fig.add_subplot(gs[k // 3, k % 3]); img = Image.open(ds.image_path(tok, cam)).convert('RGB'); W_, H_ = img.size; ax.imshow(img)
        d = ds.key[(tok, cam)]; c = ds.cs[d['calibrated_sensor_token']]; e = ds.ego[d['ego_pose_token']]; K = np.array(c['camera_intrinsic']); Rc, tc = qR(e['rotation']), np.array(e['translation'])
        Rk = qR(c['rotation']); tk = np.array(c['translation'])
        for name, boxes, col, lw in sets:
            for b in boxes:
                Pg = (Rl @ _corners(b).T).T + tl; Pe = (Rc.T @ (Pg - tc).T).T; Pc = (Rk.T @ (Pe - tk).T).T; uv = (K @ Pc.T).T; uv = uv[:, :2] / np.maximum(uv[:, 2:3], 1e-3)
                for i, j in EDGES:
                    if Pc[i, 2] > 0.1 and Pc[j, 2] > 0.1:
                        ax.plot([uv[i, 0], uv[j, 0]], [uv[i, 1], uv[j, 1]], color=col, lw=lw)
        ax.set_xlim(0, W_); ax.set_ylim(H_, 0); ax.axis('off'); ax.set_title(cam, fontsize=9)
    axb = fig.add_subplot(gs[:, 3]); P, _ = ds.keyframe_lidar(tok); axb.set_facecolor('black')
    axb.scatter(-P[:, 1], P[:, 0], s=.3, c=np.clip(P[:, 2], -3, 3), cmap='Greys_r', vmin=-3, vmax=3, linewidths=0)
    for name, boxes, col, lw in sets:
        for b in boxes:
            cc = _corners(b)[[0, 1, 5, 4, 0]]; axb.plot(-cc[:, 1], cc[:, 0], color=col, lw=lw + .2)
        axb.plot([], [], color=col, label=f'{name} ({len(boxes)})')
    axb.set_xlim(-54, 54); axb.set_ylim(-54, 54); axb.set_aspect('equal'); axb.legend(loc='upper right', fontsize=8); axb.set_title(f'LiDAR BEV + hộp (score ≥ {thr})', fontsize=10); axb.plot(0, 0, 'c^')
    fig.tight_layout()
    return fig, {n: len(b) for n, b, _, _ in sets}


# ---------------- risk / tracking / classical ----------------
RISK_SYSTEMS = ['oracle', 'classical', 'learned_occ', 'learned_detflow', 'learned_zeroflow', 'learned_flownet']
RISK_NOTE = {'oracle': 'GT occupancy + GT flow (tham chiếu)', 'classical': 'occupancy classical LiDAR, không flow', 'learned_occ': 'occupancy U-Net, không flow',
             'learned_detflow': 'occupancy U-Net + flow từ detection (nhiễm: official CL)', 'learned_zeroflow': 'occupancy U-Net + flow = 0', 'learned_flownet': 'occupancy + flow từ U-Net flow'}


def load_risk_precomputed():
    import scipy.io as sio
    O = sio.loadmat(os.path.join(WS, 'stage_h', 'risk_out.mat')); S = sio.loadmat(os.path.join(WS, 'stage_h', 'risk_inputs.mat'))
    return O, S


def fig_risk(ds, tok, maps, titles, boxes, vmax=0.6):
    n = len(maps); fig = Figure(figsize=(6.6 * n + 4.5, 6.6)); axs = fig.subplots(1, n + 1)
    axs[0].imshow(Image.open(ds.image_path(tok, 'CAM_FRONT'))); axs[0].axis('off'); axs[0].set_title('CAM_FRONT (ảnh thật)')
    xsg = np.linspace(-50, 50, 200)
    for ax, M, t in zip(axs[1:], maps, titles):
        # lưới risk cùng chỉ số ô với occupancy (hàng = x ego từ -50, cột = y); phần dịch 1,3 m nằm trong cấu hình risk, không phải toạ độ hiển thị
        im = ax.imshow(M, origin='lower', extent=[-50, 50, -50, 50], cmap='hot', vmin=0, vmax=vmax, interpolation='nearest'); ax.set_facecolor('#111')
        for (cx, cy, w, l, yaw) in boxes:
            c, s = np.cos(yaw), np.sin(yaw); u = np.array([1, 1, -1, -1, 1]) * l / 2; v = np.array([1, -1, -1, 1, 1]) * w / 2
            ax.plot(cy + s * u + c * v, cx + c * u - s * v, '-', color='c', lw=0.6)
        ax.plot(0, 0, 'g^'); _bev_axes(ax, t); ax.set_xlim(50, -50); ax.set_ylim(-50, 50)
    fig.colorbar(im, ax=axs[1:].tolist(), fraction=0.02, pad=0.01, label='điểm risk (chưa hiệu chuẩn)')
    return fig


def risk_stats(risk, ttc):
    fin = np.isfinite(ttc)
    return {'risk max': float(risk.max()), 'ô risk ≥ 0,3': int((risk >= 0.3).sum()), 'ô risk ≥ 0,1': int((risk >= 0.1).sum()), 'TTC nhỏ nhất (s)': (round(float(ttc[fin].min()), 2) if fin.any() else 'không có (∞)')}


def fig_classical(ds, tok, P, occ, objs, gt_boxes):
    fig = Figure(figsize=(8.5, 8.5)); ax = fig.subplots(); ax.set_facecolor('black')
    ax.scatter(P[:, 1], P[:, 0], s=0.3, c='#777', linewidths=0)
    r, c = np.where(occ); ax.scatter(xs[c], xs[r], s=7, c='#e6d02a', marker='s', linewidths=0, label=f'ô occupied ({len(r)})')

    def box(cx, cy, w, l, yaw, col, lw):
        cc, s = np.cos(yaw), np.sin(yaw); u = np.array([1, 1, -1, -1, 1]) * l / 2; v = np.array([1, -1, -1, 1, 1]) * w / 2
        ax.plot(cy + s * u + cc * v, cx + cc * u - s * v, '-', color=col, lw=lw)
    for o in objs:
        box(o[0], o[1], o[2], o[3], o[4], '#ff8c00', 1.6)
    for g in gt_boxes:
        box(g[0], g[1], g[2], g[3], g[4], '#39ff14', 1.0)
    ax.plot([], [], color='#ff8c00', label=f'classical objects ({len(objs)})'); ax.plot([], [], color='#39ff14', label=f'GT ({len(gt_boxes)})'); ax.plot(0, 0, 'c^')
    ax.set_xlim(50, -50); ax.set_ylim(-50, 50); ax.set_aspect('equal'); ax.set_xlabel('y trái [m]'); ax.set_ylabel('x tiến [m]'); ax.legend(loc='upper right', fontsize=8)
    ax.set_title('Pipeline classical (MATLAB Level 1) · LiDAR ' + str(len(P)) + ' điểm')
    return fig


def fig_tracks(ds, frames, idxs, cur, gt_frames=None, trail=6):
    """BEV của frame `cur` (chỉ số val) với các track và vệt đường đi (trail frame trước, hệ ego hiện tại)."""
    tok = ds.token('val', cur); Rc, tc = ds.pose(tok); P, _ = ds.keyframe_lidar(tok); fig = Figure(figsize=(9, 9)); ax = fig.subplots(); ax.set_facecolor('black')
    ax.scatter(P[:, 1], P[:, 0], s=0.3, c='#555', linewidths=0)
    cmap = __import__('matplotlib').colormaps['tab20']; pos = {}
    for j in [i for i in idxs if cur - trail <= i <= cur]:
        Rj, tj = ds.pose(ds.token('val', j))
        for (tid, x, y, cls, age) in frames.get(j, []):
            g = Rj[:2, :2] @ np.array([x, y]) + tj[:2]; e = Rc[:2, :2].T @ (g - tc[:2]); pos.setdefault(tid, []).append((j, e, cls))
    for tid, pts in pos.items():
        col = cmap(tid % 20); e = np.array([p[1] for p in pts]); ax.plot(e[:, 1], e[:, 0], '-', color=col, lw=1.4)
        if pts[-1][0] == cur:
            ax.scatter(e[-1, 1], e[-1, 0], s=45, color=col, edgecolor='w', zorder=5); ax.annotate(f'#{tid}', (e[-1, 1], e[-1, 0]), color='w', fontsize=8, xytext=(3, 3), textcoords='offset points')
    ax.plot(0, 0, 'c^'); ax.set_xlim(50, -50); ax.set_ylim(-50, 50); ax.set_aspect('equal'); ax.set_xlabel('y trái [m]'); ax.set_ylabel('x tiến [m]')
    ax.set_title(f'Tracks tại frame val {cur} (vệt {trail} frame trước, mỗi màu một ID)')
    return fig


def ego_motion(ds, tok):
    """(v_ego (2,) m/s theo trục ego, yaw_rate rad/s) bằng sai phân trung tâm ego pose của frame trước/sau (giống stage_h/prepare_risk_inputs.py)."""
    s = ds.sample[tok]; a, b = (s['prev'] or tok), (s['next'] or tok)
    dt = (ds.sample[b]['timestamp'] - ds.sample[a]['timestamp']) / 1e6
    if dt <= 0:
        return np.zeros(2), 0.0
    Ra, ta = ds.pose(a); Rb, tb = ds.pose(b); R0, _ = ds.pose(tok)
    v = (R0.T @ ((tb - ta) / dt))[:2]; d = np.arctan2(Rb[1, 0], Rb[0, 0]) - np.arctan2(Ra[1, 0], Ra[0, 0]); d = (d + np.pi) % (2 * np.pi) - np.pi
    return v, float(d / dt)

