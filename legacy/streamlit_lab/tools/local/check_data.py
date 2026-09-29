"""Check that `data/` is a complete nuScenes-mini: folders, file counts, every file referenced by the tables exists, split sizes.
  python tools/local/check_data.py"""
import collections, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from nuscenes_local import NuScenesMini, DATA

ds = NuScenesMini(); ok = True
print('data root:', DATA)
cnt = collections.Counter(); miss = []
for d in ds.sd.values():
    cnt[(('samples' if d['is_key_frame'] else 'sweeps'), d['filename'].split('/')[1])] += 1
    if not os.path.exists(os.path.join(DATA, d['filename'])):
        miss.append(d['filename'])
print(f'sample_data records: {len(ds.sd)} | referenced files missing on disk: {len(miss)}')
for ch in ('LIDAR_TOP', 'CAM_FRONT', 'RADAR_FRONT'):
    print(f'  {ch:12s} keyframes {cnt[("samples", ch)]} sweeps {cnt[("sweeps", ch)]}')
n_tr, n_va = len(ds.by_split['train']), len(ds.by_split['val'])
print(f'samples: {len(ds.sample)} | mini_train {n_tr} | mini_val {n_va} | scenes: {[ds.scene[s]["name"] for s in ds.scene]}')
ok = (len(miss) == 0 and len(ds.sample) == 404 and n_tr == 323 and n_va == 81)
print('DATA CHECK', 'PASS' if ok else 'FAIL', '(expected: 404 samples = 323 train + 81 val, 0 missing files)')
sys.exit(0 if ok else 1)
