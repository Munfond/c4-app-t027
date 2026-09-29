import json

cells = []


def bash(s):
    cells.append({"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
                  "source": ("%%bash\n" + s.strip("\n")).splitlines(keepends=True)})


CRN_COMMIT = '5e9d2fa2f91c714b297e75ca666d27fc4ad0d13d'

bash(r'''
set -euo pipefail
cat > /kaggle/working/cr_env.sh <<'EOF'
export W=/tmp/l3
export ENVDIR=$W/envs/camera_radar
export PY=$ENVDIR/bin/python
export CUDA_HOME=/tmp/cuda-11.1
export CUDA_VISIBLE_DEVICES=0
export MPLBACKEND=Agg
export OUT=/kaggle/working/outputs
export TORCH_CUDA_ARCH_LIST=7.5
export FORCE_CUDA=1
export MAX_JOBS=4
true
EOF
source /kaggle/working/cr_env.sh
mkdir -p $W/logs $OUT
{
echo "== gcc/nvcc on host"; gcc --version | head -1; nvcc --version | tail -1; nvidia-smi -L
echo "== gcc-10?"; (apt-get update -qq && apt-get install -y -qq gcc-10 g++-10) > $W/logs/apt_gcc10.log 2>&1 && echo "apt gcc-10 OK" || { echo "apt gcc-10 FAILED (see log)"; tail -5 $W/logs/apt_gcc10.log; }
which gcc-10 g++-10 || true
df -h /tmp | tail -1
} 2>&1 | tee $W/logs/step0_host.log
''')

bash(r'''
set -euo pipefail
source /kaggle/working/cr_env.sh
{
# --- CUDA 11.1 toolkit (compile-time only, matches torch 1.9.1+cu111) ---
cd $W
wget -q https://developer.download.nvidia.com/compute/cuda/11.1.1/local_installers/cuda_11.1.1_455.32.00_linux.run -O cuda11.run
ls -la cuda11.run
mkdir -p $W/cudatmp
sh cuda11.run --silent --toolkit --toolkitpath=$CUDA_HOME --no-opengl-libs --no-man-page --no-drm --override --tmpdir=$W/cudatmp > $W/logs/cuda11_install.log 2>&1 || { tail -30 $W/logs/cuda11_install.log; exit 1; }
rm -f cuda11.run
$CUDA_HOME/bin/nvcc --version | tail -2
ls $CUDA_HOME/lib64 | grep -c cudart
# --- python 3.8 conda env ---
wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O $W/miniconda.sh
bash $W/miniconda.sh -b -p $W/miniconda3 > /dev/null
$W/miniconda3/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main || true
$W/miniconda3/bin/conda tos accept || true
$W/miniconda3/bin/conda create -y --override-channels -c conda-forge -p $ENVDIR python=3.8 pip
$PY --version
} 2>&1 | tee $W/logs/step1_cuda_conda.log
''')

bash(r'''
set -euo pipefail
source /kaggle/working/cr_env.sh
cat > $W/constraints_cr.txt <<'EOF'
numpy==1.23.5
torch==1.9.1+cu111
torchvision==0.10.1+cu111
protobuf==4.25.1
EOF
{
$PY -m pip install -q "pip==23.3.1" wheel
$PY -m pip install "setuptools==59.5.0"
$PY -m pip install -c $W/constraints_cr.txt torch==1.9.1+cu111 torchvision==0.10.1+cu111 -f https://download.pytorch.org/whl/torch_stable.html
$PY -m pip install -c $W/constraints_cr.txt numpy==1.23.5 numba==0.53.0 llvmlite==0.36.0 nuscenes-devkit==1.1.9 opencv-python-headless==4.8.1.78 \
   pycocotools==2.0.7 pyquaternion==0.9.9 scikit-image==0.21.0 scikit-learn==1.3.2 scipy==1.10.1 shapely==1.8.5.post1 matplotlib==3.5.3 \
   networkx==3.1 pandas==1.4.4 pillow==10.1.0 tensorboardx==2.6.2.2 tqdm==4.65.2 fire==0.5.0 descartes==1.1.0 termcolor==2.4.0 \
   lyft_dataset_sdk plyfile trimesh yapf addict packaging pyyaml tabulate rich
$PY -m pip install -c $W/constraints_cr.txt pytorch-lightning==1.6.0 torchmetrics==0.9.3
$PY -m pip install -c $W/constraints_cr.txt mmcv-full==1.6.0 -f https://download.openmmlab.com/mmcv/dist/cu111/torch1.9.0/index.html
$PY -m pip install -c $W/constraints_cr.txt mmsegmentation==0.28.0 mmdet==2.25.2
$PY -m pip install "setuptools==59.5.0"
$PY -c "
import torch, numpy, mmcv, mmdet, mmseg, pytorch_lightning
from mmcv.ops import get_compiling_cuda_version
print('torch', torch.__version__, 'cuda', torch.version.cuda, 'avail', torch.cuda.is_available(), torch.cuda.get_device_name(0))
print('numpy', numpy.__version__, 'mmcv', mmcv.__version__, 'mmcv cuda', get_compiling_cuda_version(), 'mmdet', mmdet.__version__, 'mmseg', mmseg.__version__, 'PL', pytorch_lightning.__version__)
assert torch.__version__ == '1.9.1+cu111' and mmcv.__version__ == '1.6.0' and numpy.__version__ == '1.23.5'
from mmcv.ops import nms
b = torch.tensor([[0,0,10,10],[1,1,11,11],[50,50,60,60]], dtype=torch.float32, device='cuda'); s = torch.tensor([0.9,0.8,0.7], device='cuda')
assert nms(b, s, 0.5)[1].tolist() == [0, 2]
print('CR PYTHON STACK GATE PASS')
"
} 2>&1 | tee $W/logs/step2_python_stack.log
''')

bash(r'''
set -euo pipefail
source /kaggle/working/cr_env.sh
cd $W
git clone https://github.com/youngskkim/CRN.git CRN 2>&1 | tail -1
git -C CRN checkout @COMMIT@ 2>&1 | tail -1
git -C CRN log -1 --format='%H %ad'
# host gcc-11 is too new for nvcc 11.1 -> use gcc-10 (apt) if present, else fall back to conda toolchain
if command -v gcc-10 >/dev/null 2>&1; then export CC=gcc-10 CXX=g++-10; else
  $W/miniconda3/bin/conda install -y -p $ENVDIR -c conda-forge gcc_linux-64=10 gxx_linux-64=10 > $W/logs/conda_gcc.log 2>&1
  export CC=$ENVDIR/bin/x86_64-conda-linux-gnu-gcc CXX=$ENVDIR/bin/x86_64-conda-linux-gnu-g++; fi
echo "CC=$CC $($CC --version | head -1)"
export PATH=$CUDA_HOME/bin:$PATH LD_LIBRARY_PATH=$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-} LIBRARY_PATH=$CUDA_HOME/lib64
export PYTHONPATH=
{
cd $W/CRN/mmdetection3d
$PY -m pip install -v -e . --no-deps --no-build-isolation > $W/logs/step3_mmdet3d_build.log 2>&1 || { grep -nE "error|Error" $W/logs/step3_mmdet3d_build.log | head -30; tail -30 $W/logs/step3_mmdet3d_build.log; exit 1; }
tail -2 $W/logs/step3_mmdet3d_build.log
cd $W/CRN
$PY setup.py develop > $W/logs/step4_crn_ops.log 2>&1 || { tail -40 $W/logs/step4_crn_ops.log; exit 1; }
tail -2 $W/logs/step4_crn_ops.log
} 2>&1 | tee $W/logs/step3_4_build.log
'''.replace('@COMMIT@', CRN_COMMIT))

bash(r'''
set -euo pipefail
source /kaggle/working/cr_env.sh
# runtime needs libcudart.so.11.0 for the compiled extensions; ship it inside the env (toolkit itself is NOT packed)
cp -a $CUDA_HOME/lib64/libcudart.so* $ENVDIR/lib/
export LD_LIBRARY_PATH=$ENVDIR/lib:${LD_LIBRARY_PATH:-}
cd $W/CRN
{
$PY -W ignore - <<'EOF'
import torch, mmcv, mmdet, mmdet3d, mmseg, numpy
import ops.voxel_pooling_v2.voxel_pooling_ext as vp
import ops.average_voxel_pooling_v2.average_voxel_pooling_ext as avp
from mmdet3d.ops import Voxelization
print('mmdet3d', mmdet3d.__version__, '| ext modules:', vp.__name__, avp.__name__)
from models.camera_radar_net_det import CameraRadarNetDet
print('CameraRadarNetDet import OK')
print('CR ENV GATE PASS')
EOF
} 2>&1 | tee $W/logs/step5_gate.log
''')

bash(r'''
set -euo pipefail
source /kaggle/working/cr_env.sh
{
echo "== date"; date -u; echo "== GPU"; nvidia-smi -L; $CUDA_HOME/bin/nvcc --version | tail -2
echo "== crn commit"; git -C $W/CRN log -1 --format='%H %ad'
echo "== constraints"; cat $W/constraints_cr.txt
echo "== pip freeze (camera_radar env)"; $PY -m pip freeze
} > $OUT/environment_camera_radar.txt 2>&1
mkdir -p $OUT/logs; cp $W/logs/*.log $OUT/logs/ 2>/dev/null || true
cd $W
tar -cf - envs/camera_radar CRN constraints_cr.txt | gzip -1 > /kaggle/working/env_camera_radar.tar.gz
ls -la /kaggle/working/env_camera_radar.tar.gz
sha256sum /kaggle/working/env_camera_radar.tar.gz | tee $OUT/SHA256SUMS_camera_radar.txt
gzip -t /kaggle/working/env_camera_radar.tar.gz && echo "archive integrity OK"
echo "CR ENV PACK PASS"
''')

nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 4}
json.dump(nb, open('bev-real-cr-env.ipynb', 'w', encoding='utf-8'), indent=1)
json.dump({"id": "canhquang/bev-real-cr-env", "title": "bev_real_cr_env", "code_file": "bev-real-cr-env.ipynb", "language": "python",
           "kernel_type": "notebook", "is_private": "true", "enable_gpu": "true", "machine_shape": "NvidiaTeslaT4", "enable_internet": "true",
           "dataset_sources": [], "competition_sources": [], "kernel_sources": []}, open('kernel-metadata.json', 'w'), indent=2)
print('cells', len(cells))
