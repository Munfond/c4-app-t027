import json

b = open('build_occ_dataset.py', encoding='utf-8').read()
t = open('train_occ.py', encoding='utf-8').read()
c1 = "import os\nos.makedirs('/tmp/l3', exist_ok=True)\nopen('/tmp/l3/build_occ_dataset.py','w',encoding='utf-8').write(%r)\nopen('/tmp/l3/train_occ.py','w',encoding='utf-8').write(%r)\nprint('written')" % (b, t)
c2 = r'''%%bash
set -euo pipefail
export W=/tmp/l3 MPLBACKEND=Agg CUDA_VISIBLE_DEVICES=0
mkdir -p /kaggle/working/outputs $W/data
TAR=$(find /kaggle/input -maxdepth 6 -name 'env_bevfusion.tar.*' | head -1); echo "$TAR"
case "$TAR" in *.zst) zstd -dc "$TAR" | tar -C $W -xf - envs/bevfusion ;; *.gz) tar -C $W -xzf "$TAR" envs/bevfusion ;; esac
PY=$W/envs/bevfusion/bin/python
$PY -c "import torch, scipy, numpy; print('torch', torch.__version__, torch.cuda.get_device_name(0), 'numpy', numpy.__version__)"
$PY -W ignore $W/build_occ_dataset.py $W/data 2>&1 | tail -15
cp $W/data/occ_dataset_stats.json /kaggle/working/outputs/
$PY -W ignore $W/train_occ.py $W/data /kaggle/working/outputs 2>&1 | tail -30
ls -la /kaggle/working/outputs
'''
cells = [{"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": c.splitlines(keepends=True)} for c in (c1, c2)]
json.dump({"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 4}, open('bev-real-occ.ipynb', 'w'), indent=1)
json.dump({"id": "canhquang/bev-real-occ", "title": "bev_real_occ", "code_file": "bev-real-occ.ipynb", "language": "python", "kernel_type": "notebook", "is_private": "true",
           "enable_gpu": "true", "machine_shape": "NvidiaTeslaT4", "enable_internet": "false", "dataset_sources": ["aadimator/nuscenes-mini"], "competition_sources": [],
           "kernel_sources": ["canhquang/bev-real-freeze"]}, open('kernel-metadata.json', 'w'), indent=2)
print('ok')
