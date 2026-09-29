import json

occ = open('../stage_f/build_occ_dataset.py', encoding='utf-8').read()
bf = open('build_flow_dataset.py', encoding='utf-8').read()
tf = open('train_flow.py', encoding='utf-8').read()
old = "NPZ = None\nfor r, d, f in os.walk('/kaggle/input'):\n    if 'occ_dataset.npz' in f:\n        NPZ = os.path.join(r, 'occ_dataset.npz'); break"
assert old in bf
bf = bf.replace(old, "NPZ = '/tmp/l3/data/occ_dataset.npz'")
c1 = ("import os\nos.makedirs('/tmp/l3', exist_ok=True)\n"
      "open('/tmp/l3/build_occ_dataset.py','w',encoding='utf-8').write(%r)\n"
      "open('/tmp/l3/build_flow_dataset.py','w',encoding='utf-8').write(%r)\n"
      "open('/tmp/l3/train_flow.py','w',encoding='utf-8').write(%r)\nprint('written')") % (occ, bf, tf)
c2 = r'''%%bash
set -euo pipefail
export W=/tmp/l3 MPLBACKEND=Agg CUDA_VISIBLE_DEVICES=0
mkdir -p /kaggle/working/outputs $W/data
TAR=$(find /kaggle/input -maxdepth 6 -name 'env_bevfusion.tar.*' | head -1); echo "$TAR"
case "$TAR" in *.zst) zstd -dc "$TAR" | tar -C $W -xf - envs/bevfusion ;; *.gz) tar -C $W -xzf "$TAR" envs/bevfusion ;; esac
PY=$W/envs/bevfusion/bin/python
$PY -c "import torch; print('torch', torch.__version__, torch.cuda.get_device_name(0))"
$PY -W ignore $W/build_occ_dataset.py $W/data 2>&1 | tail -4
$PY -W ignore $W/build_flow_dataset.py $W/data 2>&1 | tail -6
$PY -W ignore $W/train_flow.py $W/data $W/data /kaggle/working/outputs 2>&1 | tail -30
ls -la /kaggle/working/outputs
'''
cells = [{"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": c.splitlines(keepends=True)} for c in (c1, c2)]
json.dump({"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 4},
          open('bev-real-flow.ipynb', 'w'), indent=1)
json.dump({"id": "canhquang/bev-real-flow", "title": "bev_real_flow", "code_file": "bev-real-flow.ipynb", "language": "python", "kernel_type": "notebook", "is_private": "true",
           "enable_gpu": "true", "machine_shape": "NvidiaTeslaT4", "enable_internet": "false", "dataset_sources": ["aadimator/nuscenes-mini"], "competition_sources": [],
           "kernel_sources": ["canhquang/bev-real-freeze"]}, open('kernel-metadata.json', 'w'), indent=2)
print('notebook written')
