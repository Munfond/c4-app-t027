"""Load every checkpoint in models/ with plain PyTorch (no mmdet3d needed) and report: size, checksum vs models/CHECKPOINTS.sha256, tensors, parameters, meta.
  python tools/local/inspect_checkpoints.py"""
import hashlib, os, sys
import torch

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
WS = os.environ.get('LAB_DATA_ROOT', os.path.join(REPO, 'data', 'lab'))
man = {}
for line in open(os.path.join(WS, 'models', 'CHECKPOINTS.sha256')):
    h, p = line.split(None, 1); man[os.path.normpath(p.strip().lstrip('*'))] = h
bad = 0
print(f"{'checkpoint':68s} {'MB':>6s} {'sha256':>7s} {'tensors':>8s} {'params(M)':>9s}  note")
for root, _, files in os.walk(os.path.join(WS, 'models')):
    for f in sorted(files):
        if not f.endswith('.pth'):
            continue
        p = os.path.join(root, f); rel = os.path.relpath(p, os.path.join(WS, 'models')); h = hashlib.sha256(open(p, 'rb').read()).hexdigest()
        sha = 'OK' if man.get(os.path.normpath(rel)) == h else 'MISMATCH'; bad += sha != 'OK'
        c = torch.load(p, map_location='cpu', weights_only=False); sd = c.get('state_dict', c)
        n = sum(v.numel() for v in sd.values() if hasattr(v, 'numel')) / 1e6; note = str((c.get('meta', {}) or {}).get('our_note', c.get('note', '')))[:70] if isinstance(c, dict) else ''
        print(f'{rel:68s} {os.path.getsize(p) / 1e6:6.1f} {sha:>7s} {len(sd):8d} {n:9.2f}  {note}')
print('CHECKPOINT INSPECTION', 'PASS' if bad == 0 else f'FAIL ({bad} checksum mismatches)')
print('Runnable locally on CPU: occupancy/*.pth and temporal_flow/*.pth (plain PyTorch). BEVFusion (lidar_only, camera_lidar) and CRN need CUDA + mmdet3d/spconv: run them on Kaggle.')
