"""Stage C0: audit the nuScenes-mini Kaggle dataset for RADAR. Pure numpy; no dataset is faked."""
import collections, glob, json, os, sys, zipfile
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
V = None
for r, d, f in os.walk('/kaggle/input'):
    if 'v1.0-mini' in d:
        V = os.path.join(r, 'v1.0-mini'); break
ROOT = os.path.dirname(V)
print('ROOT', ROOT)
RADARS = ['RADAR_FRONT', 'RADAR_FRONT_LEFT', 'RADAR_FRONT_RIGHT', 'RADAR_BACK_LEFT', 'RADAR_BACK_RIGHT']
CAMS = ['CAM_FRONT', 'CAM_FRONT_LEFT', 'CAM_FRONT_RIGHT', 'CAM_BACK', 'CAM_BACK_LEFT', 'CAM_BACK_RIGHT']


def load(n):
    p = os.path.join(V, n + '.json')
    if os.path.exists(p):
        return json.load(open(p))
    with zipfile.ZipFile(p + '.zip') as z:
        return json.load(z.open(z.namelist()[0]))


sample = {s['token']: s for s in load('sample')}
sd = load('sample_data')
cs = {c['token']: c for c in load('calibrated_sensor')}
ego = {e['token']: e for e in load('ego_pose')}
sensor = {s['token']: s for s in load('sensor')}
scene = {s['token']: s for s in load('scene')}
rep = dict(root=ROOT, n_samples=len(sample), n_scenes=len(scene))

# ---- 1. file counts ------------------------------------------------------------------------------------------------------
cnt = {}
for r in RADARS + ['LIDAR_TOP'] + CAMS:
    ns = len(os.listdir(f'{ROOT}/samples/{r}')) if os.path.isdir(f'{ROOT}/samples/{r}') else -1
    nw = len(os.listdir(f'{ROOT}/sweeps/{r}')) if os.path.isdir(f'{ROOT}/sweeps/{r}') else -1
    cnt[r] = dict(samples=ns, sweeps=nw)
rep['file_counts'] = cnt
print('file counts'); [print(f'  {k:18s} samples={v["samples"]:5d} sweeps={v["sweeps"]:6d}') for k, v in cnt.items()]

# ---- 2. table <-> files ------------------------------------------------------------------------------------------------------
by_ch = collections.defaultdict(list)
for d in sd:
    by_ch[d['filename'].split('/')[1]].append(d)
miss = {}
for r in RADARS:
    miss[r] = dict(key_total=sum(1 for d in by_ch[r] if d['is_key_frame']), sweep_total=sum(1 for d in by_ch[r] if not d['is_key_frame']),
                   missing=sum(1 for d in by_ch[r] if not os.path.exists(f'{ROOT}/{d["filename"]}')))
rep['table_vs_files'] = miss
print('table vs files', json.dumps(miss))

# ---- 3. calibration ------------------------------------------------------------------------------------------------------
cal = {}
for r in RADARS:
    ds = by_ch[r]
    c = cs[ds[0]['calibrated_sensor_token']]
    tset = {tuple(np.round(cs[d['calibrated_sensor_token']]['translation'], 4)) for d in ds}
    cal[r] = dict(translation=c['translation'], rotation=c['rotation'], intrinsic=c['camera_intrinsic'],
                  sensor_modality=sensor[c['sensor_token']]['modality'], n_distinct_extrinsics=len(tset))
rep['calibration'] = cal
print('radar calibration'); [print(f'  {k:18s} t={np.round(v["translation"], 3).tolist()} q={np.round(v["rotation"], 3).tolist()} modality={v["sensor_modality"]} distinct={v["n_distinct_extrinsics"]}') for k, v in cal.items()]

# ---- 4. timestamps ------------------------------------------------------------------------------------------------------
kf = collections.defaultdict(dict)
for d in sd:
    if d['is_key_frame']:
        kf[d['sample_token']][d['filename'].split('/')[1]] = d
dt = {r: [] for r in RADARS + CAMS}
for t, chs in kf.items():
    tl = chs['LIDAR_TOP']['timestamp']
    for r in RADARS + CAMS:
        if r in chs:
            dt[r].append((chs[r]['timestamp'] - tl) / 1e3)  # ms
rep['keyframe_dt_ms_vs_lidar'] = {r: dict(n=len(v), mean=float(np.mean(v)), std=float(np.std(v)), min=float(np.min(v)), max=float(np.max(v)),
                                          abs_p95=float(np.percentile(np.abs(v), 95))) for r, v in dt.items() if v}
print('keyframe dt (ms) vs LIDAR_TOP'); [print(f'  {r:18s} n={v["n"]} mean={v["mean"]:+.1f} std={v["std"]:.1f} range=[{v["min"]:+.1f},{v["max"]:+.1f}]') for r, v in rep['keyframe_dt_ms_vs_lidar'].items()]
sw = {}
for r in RADARS:
    ts = sorted(d['timestamp'] for d in by_ch[r])
    g = np.diff(ts) / 1e3
    g = g[(g > 0) & (g < 500)]
    sw[r] = dict(median_gap_ms=float(np.median(g)), hz=float(1000 / np.median(g)))
rep['radar_rate'] = sw
print('radar rate', {k: round(v['hz'], 1) for k, v in sw.items()})

# ---- 5. fields ------------------------------------------------------------------------------------------------------
TY = {('F', 4): '<f4', ('F', 8): '<f8', ('I', 1): 'i1', ('I', 2): '<i2', ('I', 4): '<i4', ('U', 1): 'u1', ('U', 2): '<u2', ('U', 4): '<u4'}


def read_pcd(p):
    with open(p, 'rb') as f:
        h = {}
        while True:
            k, *v = f.readline().decode().strip().split()
            h[k] = v
            if k == 'DATA':
                break
        dtp = np.dtype([(n, TY[(t, int(s))]) for n, t, s in zip(h['FIELDS'], h['TYPE'], h['SIZE'])])
        return h, np.frombuffer(f.read(), dtype=dtp, count=int(h['POINTS'][0]))


h0, a0 = read_pcd(f'{ROOT}/{by_ch["RADAR_FRONT"][0]["filename"]}')
rep['pcd_header'] = dict(fields=h0['FIELDS'], types=h0['TYPE'], sizes=h0['SIZE'], data=h0['DATA'], version=h0.get('VERSION'))
print('PCD fields:', h0['FIELDS'])
npts = {r: [] for r in RADARS}
allp = collections.defaultdict(list)
for r in RADARS:
    for d in [x for x in by_ch[r] if x['is_key_frame']]:
        _, a = read_pcd(f'{ROOT}/{d["filename"]}')
        npts[r].append(len(a))
        if len(allp[r]) < 60:
            allp[r].append(a)
rep['points_per_keyframe'] = {r: dict(n_frames=len(v), mean=float(np.mean(v)), min=int(np.min(v)), max=int(np.max(v)), zero_frames=int(np.sum(np.array(v) == 0))) for r, v in npts.items()}
print('points per keyframe'); [print(f'  {r:18s} {v}') for r, v in rep['points_per_keyframe'].items()]
A = np.concatenate([np.concatenate(v) for v in allp.values()])
fs = {}
for n in A.dtype.names:
    x = A[n].astype(float)
    fs[n] = dict(min=float(x.min()), max=float(x.max()), mean=float(x.mean()), n_unique=int(len(np.unique(x))) if len(np.unique(x)) < 64 else '>63')
rep['field_stats'] = fs
rep['invalid_state_hist'] = {int(k): int(v) for k, v in zip(*np.unique(A['invalid_state'], return_counts=True))}
rep['dyn_prop_hist'] = {int(k): int(v) for k, v in zip(*np.unique(A['dyn_prop'], return_counts=True))}
rep['ambig_state_hist'] = {int(k): int(v) for k, v in zip(*np.unique(A['ambig_state'], return_counts=True))}
print('field stats'); [print(f'  {k:16s} {v}') for k, v in fs.items()]
print('invalid_state', rep['invalid_state_hist'], '| dyn_prop', rep['dyn_prop_hist'], '| ambig', rep['ambig_state_hist'])

# ---- 6. visual proof: radar + lidar in ego frame for a real sample ----------------------------------------------------------------------
def qR(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


tok = sorted(kf.keys(), key=lambda t: sample[t]['timestamp'])[40]
fig, ax = plt.subplots(1, 2, figsize=(16, 8))
lid = kf[tok]['LIDAR_TOP']
L = np.fromfile(f'{ROOT}/{lid["filename"]}', dtype=np.float32).reshape(-1, 5)[:, :3]
cl = cs[lid['calibrated_sensor_token']]
Le = (qR(cl['rotation']) @ L.T).T + np.array(cl['translation'])
cols = dict(zip(RADARS, ['tab:red', 'tab:orange', 'tab:green', 'tab:blue', 'tab:purple']))
tot = 0
for a_, title in zip(ax, ['LiDAR (grey) + 5 radars (colour), ego frame', 'radar only, arrows = ego-motion-compensated velocity']):
    a_.set_aspect('equal'); a_.set_xlim(-60, 60); a_.set_ylim(-60, 60); a_.grid(alpha=.3); a_.set_title(title)
ax[0].scatter(-Le[:, 1], Le[:, 0], s=.2, c='0.6')
for r in RADARS:
    d = kf[tok][r]
    _, a = read_pcd(f'{ROOT}/{d["filename"]}')
    c = cs[d['calibrated_sensor_token']]
    R = qR(c['rotation'])
    P = (R @ np.stack([a['x'], a['y'], a['z']]).astype(float)).T + np.array(c['translation'])
    Vv = (R @ np.stack([a['vx_comp'], a['vy_comp'], np.zeros(len(a))]).astype(float)).T
    tot += len(a)
    ax[0].scatter(-P[:, 1], P[:, 0], s=14, c=cols[r], label=f'{r} ({len(a)})')
    ax[1].scatter(-P[:, 1], P[:, 0], s=14, c=cols[r])
    ax[1].quiver(-P[:, 1], P[:, 0], -Vv[:, 1], Vv[:, 0], color=cols[r], angles='xy', scale_units='xy', scale=1, width=.002)
ax[0].legend(fontsize=8); ax[0].plot(0, 0, 'k^')
fig.suptitle(f'nuScenes-mini sample {tok[:8]}  |  {tot} radar points over 5 sensors, {len(L)} LiDAR points')
fig.savefig(f'{OUT}/radar_lidar_ego_sample.png', dpi=90, bbox_inches='tight')

# ---- verdict ------------------------------------------------------------------------------------------------------
ok = all(cnt[r]['samples'] == 404 for r in RADARS) and all(v['missing'] == 0 for v in miss.values()) \
    and all(v['zero_frames'] < v['n_frames'] * 0.2 for v in rep['points_per_keyframe'].values()) \
    and all(v['n_distinct_extrinsics'] >= 1 for v in cal.values()) and 'vx_comp' in h0['FIELDS']
rep['verdict'] = 'RADAR DATASET AUDIT PASS' if ok else 'RADAR DATASET AUDIT FAIL'
json.dump(rep, open(f'{OUT}/radar_audit.json', 'w'), indent=2)
print(rep['verdict'])
