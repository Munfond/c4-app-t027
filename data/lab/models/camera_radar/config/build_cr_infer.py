import json

viz_src = open('viz_l3.py', encoding='utf-8').read()
cells = []


def code(s):
    cells.append({"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": s.strip("\n").splitlines(keepends=True)})


def bash(s):
    code("%%bash\n" + s.strip("\n"))


bash(r'''
set -euo pipefail
cat > /kaggle/working/cr_env.sh <<'EOF'
export W=/tmp/l3
export ENVDIR=$W/envs/camera_radar
export PY=$ENVDIR/bin/python
export CUDA_VISIBLE_DEVICES=0
export MPLBACKEND=Agg
export OUT=/kaggle/working/outputs
export LD_LIBRARY_PATH=$ENVDIR/lib:${LD_LIBRARY_PATH:-}
true
EOF
source /kaggle/working/cr_env.sh
mkdir -p $W $OUT $W/logs
TAR=$(find /kaggle/input -maxdepth 6 -name 'env_camera_radar.tar.gz' | head -1)
[ -n "$TAR" ] || { echo "no env tar"; find /kaggle/input -maxdepth 4 | head -30; exit 1; }
ls -la "$TAR"; tar -C $W -xzf "$TAR"; ls $W
V=$(find /kaggle/input -maxdepth 6 -type d -name v1.0-mini | head -1); ROOT=$(dirname "$V"); echo "nuScenes root: $ROOT"
mkdir -p $W/CRN/data/nuScenes
for d in samples sweeps maps v1.0-mini; do ln -sfn "$ROOT/$d" $W/CRN/data/nuScenes/$d; done
ls -la $W/CRN/data/nuScenes; git -C $W/CRN log -1 --format='%H'
cd $W/CRN; export PYTHONPATH=$PWD
$PY -W ignore -c "
import torch, mmcv, mmdet3d, pytorch_lightning as pl
import ops.voxel_pooling_v2.voxel_pooling_ext, ops.average_voxel_pooling_v2.average_voxel_pooling_ext
from models.camera_radar_net_det import CameraRadarNetDet
print('restored CR env OK', torch.__version__, torch.cuda.get_device_name(0), mmcv.__version__, mmdet3d.__version__, pl.__version__)
"
''')

PATCH = r'''
import os, subprocess
os.chdir('/tmp/l3/CRN')
open('scripts/gen_info_mini.py', 'w').write("""
import sys, mmcv
sys.path.insert(0, 'scripts')
from gen_info import generate_info
from nuscenes.nuscenes import NuScenes
from nuscenes.utils import splits
nusc = NuScenes(version='v1.0-mini', dataroot='./data/nuScenes/', verbose=True)
tr = generate_info(nusc, splits.mini_train)
va = generate_info(nusc, splits.mini_val)
mmcv.dump(tr, './data/nuScenes/nuscenes_infos_train.pkl')
mmcv.dump(va, './data/nuScenes/nuscenes_infos_val.pkl')
print('MINI INFOS: train', len(tr), 'val', len(va), 'scenes train', sorted({i['scene_name'] for i in tr}), 'val', sorted({i['scene_name'] for i in va}))
""")
for name in ['gen_radar_bev', 'gen_radar_pv', 'gen_depth_gt']:
    s = open('scripts/%s.py' % name).read()
    s = s.replace("SPLIT = 'v1.0-trainval'", "SPLIT = 'v1.0-mini'").replace('Pool(24)', 'Pool(4)')
    open('scripts/%s_mini.py' % name, 'w').write(s)
p = 'exps/base_exp.py'
s = open(p).read()
old = "output_dir=self.default_root_dir)"
assert s.count(old) == 1
open(p, 'w').write(s.replace(old, "output_dir=self.default_root_dir,\n                                          version='v1.0-mini')"))
print(subprocess.run(['git', 'diff', '--stat'], capture_output=True, text=True).stdout)
os.makedirs('/kaggle/working/outputs/config', exist_ok=True)
open('/kaggle/working/outputs/config/crn_mini_patch.diff', 'w').write(subprocess.run(['git', 'diff'], capture_output=True, text=True).stdout)
open('/tmp/l3/viz_l3.py', 'w', encoding='utf-8').write(VIZ_SRC)
print('patched')
'''
code("VIZ_SRC = %r\n" % viz_src + PATCH)

bash(r'''
set -euo pipefail
source /kaggle/working/cr_env.sh
cd $W/CRN; export PYTHONPATH=$PWD
{
$PY -W ignore scripts/gen_info_mini.py 2>&1 | tail -3
$PY -W ignore scripts/gen_radar_bev_mini.py 2>&1 | tail -2
$PY -W ignore scripts/gen_radar_pv_mini.py 2>&1 | tail -2
$PY -W ignore scripts/gen_depth_gt_mini.py 2>&1 | tail -3
echo "depth_gt files: $(ls data/nuScenes/depth_gt | wc -l)"
echo "radar_bev_filter files: $(ls data/nuScenes/radar_bev_filter | wc -l) | radar_pv_filter files: $(ls data/nuScenes/radar_pv_filter | wc -l)"
$PY - <<'EOF'
import numpy as np, glob
fs = sorted(glob.glob('data/nuScenes/radar_bev_filter/*.bin'))
n = [np.fromfile(f, dtype=np.float32).reshape(-1, 7).shape[0] for f in fs]
print('BEV radar points/sample (8 sweeps, 5 radars, filtered): mean %.0f min %d max %d' % (np.mean(n), min(n), max(n)))
fp = sorted(glob.glob('data/nuScenes/radar_pv_filter/*.bin'))
m = [np.fromfile(f, dtype=np.float32).size // 9 for f in fp[:600]]
print('PV radar points/camera-image (first 600): mean %.0f max %d' % (np.mean(m), max(m)))
import os
assert len(fs) == 404 and len(fp) == 6 * 404 and len(os.listdir('data/nuScenes/depth_gt')) == 6 * 404, 'preprocessing incomplete'
print('RADAR PREP PASS')
EOF
} 2>&1 | tee $W/logs/data_prep.log
''')

bash(r'''
set -uo pipefail
source /kaggle/working/cr_env.sh
mkdir -p $OUT/logs
trap 'cp $W/logs/*.log $OUT/logs/ 2>/dev/null || true' EXIT
cd $W/CRN; export PYTHONPATH=$PWD
mkdir -p checkpoints
CK=checkpoints/CRN_r18_256x704_128x128_4key.pth
wget -q https://github.com/youngskkim/CRN/releases/download/v1.0/CRN_r18_256x704_128x128_4key.pth -O $CK
ls -la $CK; sha256sum $CK | tee $OUT/logs/crn_r18_checkpoint_sha256.txt
$PY -W ignore -c "
import torch
c = torch.load('$CK', map_location='cpu'); print('ckpt keys:', list(c.keys())[:8]); sd = c.get('state_dict', c); print('tensors:', len(sd), 'params(M): %.1f' % (sum(v.numel() for v in sd.values() if hasattr(v, 'numel')) / 1e6))
"
$PY -W ignore exps/det/CRN_r18_256x704_128x128_4key.py --ckpt_path $CK -e -b 1 --gpus 1 2>&1 | tee $W/logs/crn_eval.log | grep -vE "^\s*$" | tail -60
echo "eval exit: ${PIPESTATUS[0]}"
find . -name results_nusc.json -o -name metrics_summary.json | head
''')

bash(r'''
set -euo pipefail
source /kaggle/working/cr_env.sh
cd $W/CRN
R=$(find outputs -name results_nusc.json | head -1); M=$(find outputs -name metrics_summary.json | head -1)
echo "results=$R metrics=$M"
D=$OUT/crn_r18_pretrained; mkdir -p $D
cp "$R" $D/results_nusc.json; cp "$M" $D/metrics_summary.json; cp $W/logs/crn_eval.log $D/
$PY - <<'EOF'
import json
m = json.load(open('/kaggle/working/outputs/crn_r18_pretrained/metrics_summary.json'))
r = json.load(open('/kaggle/working/outputs/crn_r18_pretrained/results_nusc.json'))
n = sum(len(v) for v in r['results'].values())
print('CRN R18 pretrained on mini VAL: mAP=%.4f NDS=%.4f | samples=%d boxes=%d | meta=%s' % (m['mean_ap'], m['nd_score'], len(r['results']), n, r['meta']))
print('AP@2m', {k: round(v, 2) for k, v in m['mean_dist_aps'].items()})
assert len(r['results']) == 81 and m['mean_ap'] > 0.1
print('CRN PRETRAINED INFERENCE PASS')
EOF
OFF=$(find /kaggle/input -name results_nusc.json -path '*L3D_lidar_camera*' | head -1)
V=$(find /kaggle/input -maxdepth 6 -type d -name v1.0-mini | head -1); ROOT=$(dirname "$V")
mkdir -p $D/demo_images
python3 /tmp/l3/viz_l3.py --root "$ROOT" --tables "$ROOT/v1.0-mini" --res_lidar $D/results_nusc.json --res_cam "$OFF" --out $D/demo_images --every 9 --thr 0.3 --dpi 70 --cam_pred l \
  --label_l "CRN Camera+Radar (official pretrained)" --label_c "BEVFusion Camera+LiDAR (official pretrained)" \
  --note "official checkpoints trained on trainval -> contaminated on mini VAL; not a benchmark" 2>&1 | tail -8
du -sh $OUT; ls $D
''')

nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 4}
json.dump(nb, open('bev-real-cr-infer.ipynb', 'w', encoding='utf-8'), indent=1)
json.dump({"id": "canhquang/bev-real-cr-infer", "title": "bev_real_cr_infer", "code_file": "bev-real-cr-infer.ipynb", "language": "python", "kernel_type": "notebook",
           "is_private": "true", "enable_gpu": "true", "machine_shape": "NvidiaTeslaT4", "enable_internet": "true",
           "dataset_sources": ["aadimator/nuscenes-mini"], "competition_sources": [],
           "kernel_sources": ["canhquang/bev-real-cr-env", "canhquang/bev-real-l3c"]}, open('kernel-metadata.json', 'w'), indent=2)
print('cells', len(cells))
