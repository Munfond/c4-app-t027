# Hướng dẫn chạy & kiểm tra thật bằng Python trên máy local

Mục tiêu: **không chỉ nhìn ảnh đã lưu** mà tự lấy frame nuScenes-mini trong `data/`, nạp file trọng số (`.pth`) và chạy suy luận ngay trên máy.
Mọi lệnh dưới đây đã được chạy thật trên máy này (Windows 11, CPU, không GPU) ngày 25/09/2026.

> Thư mục làm việc: `D:\Vinuni\endgame\cam_lidar_radar\cam_lidar_radat_real_ws` (gọi là `WS`). Chạy mọi lệnh từ `WS`.

## 0. Cái gì chạy được ở local, cái gì không

| Model | Trọng số | Chạy local (CPU)? | Cách xem kết quả |
|---|---|---|---|
| Occupancy U-Net (LiDAR+Radar / LiDAR / Radar) | `models/occupancy/*.pth` | **Có** – ~0.1–0.3 s/frame | `run_occupancy.py` |
| Temporal flow U-Net (T1/T2/T4/T4_nowarp) | `models/temporal_flow/*.pth` | **Có** – ~0.1 s/frame | `run_flow.py` |
| BEVFusion LiDAR-only / Camera+LiDAR (official và bản tự train) | `models/lidar_only`, `models/camera_lidar` | **Không** – cần CUDA + mmdet3d + spconv (máy này không có GPU NVIDIA, không WSL) | chạy trên Kaggle; kết quả đã xuất sẵn ra CSV cho **81 frame val**, xem bằng `view_detections.py` |
| CRN Camera+Radar (pretrained) | `models/camera_radar/` | **Không** (cần CUDA, env riêng py3.8/torch1.9) | như trên |

Hiểu rõ giới hạn: bạn có thể *chạy lại thật* occupancy và flow trên **bất kỳ** frame nào trong 404 keyframe. Với các detector 3D, local chỉ *xem lại* output đã tính trên Kaggle (chi tiết mục 6 để chạy lại chúng trên Kaggle).

## 1. Cài môi trường (một lần)

```powershell
cd D:\Vinuni\endgame\cam_lidar_radar\cam_lidar_radat_real_ws
py -3.11 -m venv .venv_local
.venv_local\Scripts\python -m pip install --upgrade pip
.venv_local\Scripts\python -m pip install numpy scipy matplotlib pillow
.venv_local\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
```
Môi trường đã kiểm thử: Python 3.11, torch 2.14.0+cpu, numpy 2.4.6, scipy 1.17.1, matplotlib 3.11.2. Trong các lệnh dưới, `py` = `.venv_local\Scripts\python.exe`.

Nếu `data/` không nằm trong `WS`, đặt biến môi trường: `$env:NUSC_ROOT = "D:\duong\toi\nuscenes"`.

## 2. Kiểm tra dữ liệu và trọng số

```powershell
.venv_local\Scripts\python tools\local\check_data.py
```
Kết quả mong đợi (đã chạy): 31 206 bản ghi sample_data, 0 file thiếu, 404 keyframe = 323 train + 81 val, dòng cuối `DATA CHECK PASS`.

```powershell
.venv_local\Scripts\python tools\local\inspect_checkpoints.py
```
Nạp cả 21 file `.pth` bằng PyTorch thuần, so sha256 với `models/CHECKPOINTS.sha256`. Mong đợi: 21 dòng `OK`, `CHECKPOINT INSPECTION PASS`.

## 3. Chạy occupancy trên một frame bất kỳ

```powershell
# frame val số 5 (đánh số từ 0), model LiDAR+Radar mặc định
.venv_local\Scripts\python tools\local\run_occupancy.py --split val --idx 5
# chọn frame bằng token nuScenes, bỏ qua tính nhãn cho nhanh
.venv_local\Scripts\python tools\local\run_occupancy.py --token c1eed31234b94e9f8e22fbf3428b0ac2 --no-label
# đổi biến thể: lidar_radar | lidar | radar ; đổi split: train | val
.venv_local\Scripts\python tools\local\run_occupancy.py --split train --idx 100 --variant lidar
```
In ra: số ô static/object dự đoán, thời gian suy luận CPU, IoU của frame (khi có nhãn), và lưu PNG vào `reports\local_runs\occupancy_<split><idx>_<variant>.png` (input, nhãn, dự đoán).
Ví dụ đã chạy: `val[5]` → IoU free 0.961 / static 0.531 / object 0.166.

**Lưu ý trung thực:** frame `train` đã nằm trong dữ liệu huấn luyện nên IoU cao (train[100]: object 0.95) — đó không phải hiệu năng tổng quát. Chỉ số có ý nghĩa là trên **val**.

### Kiểm chứng đầy đủ (parity với Kaggle)
```powershell
.venv_local\Scripts\python tools\local\run_occupancy.py --split val --all
```
Chạy 81 frame (~25 s trên CPU). Kết quả đã chạy:
`IoU free 0.9602 static 0.4898 object 0.1959 | mIoU 0.5486 | IoU occupied 0.4230`,
`agreement with the Kaggle-GPU predictions: 100.000% of cells`, nhãn dựng lại từ `data/` trùng nhãn Kaggle 100.000%.
=> pipeline dựng input/nhãn local **giống hệt** lúc huấn luyện, và CPU cho cùng kết quả GPU.

## 4. Chạy temporal flow (vận tốc mặt đất)

```powershell
.venv_local\Scripts\python tools\local\run_flow.py --split val --idx 51                 # T4 có bù chuyển động ego
.venv_local\Scripts\python tools\local\run_flow.py --split val --idx 51 --variant T1    # T1 | T2 | T4 | T4_nowarp
.venv_local\Scripts\python tools\local\run_flow.py --split val --all
```
Mỗi frame in EPE (m/s), baseline zero-flow, flow giả trên vật tĩnh; lưu `reports\local_runs\flow_val51_T4.png`.
Kết quả `--all` đã chạy: `EPE 3.518 m/s | zero-flow baseline 3.792 | static-object false flow 1.696`; khớp output Kaggle: argmax occupancy 100%, sai lệch flow trung bình 0.0003 m/s.

Đọc kết quả đúng: EPE của learned flow chỉ hơn zero-flow một chút, và với frame 51 T4 3.99 vs 5.44 nhưng T1 6.34 > 5.44 (tệ hơn). Học flow từ 323 frame **chưa dùng được** – xem `stage_g/results` và báo cáo cuối. Stage H dùng flow từ detection thay thế.

## 5. Xem detection trên ảnh camera thật + LiDAR

```powershell
.venv_local\Scripts\python tools\local\view_detections.py --idx 40 --models official_cl,our_cl,crn
.venv_local\Scripts\python tools\local\view_detections.py --idx 5 --models our_lidar,fused --thr 0.4
```
Vẽ 6 ảnh camera thật đọc từ `data/samples/CAM_*` với hộp 3D chiếu lên (xanh lá = GT, màu khác = từng model) và BEV LiDAR. Tên model: `official_lidar`, `official_cl`, `our_lidar`, `our_cl`, `crn`, `fused`. Lưu `reports\local_runs\detections_val<idx>_<models>.png`. `--idx` là chỉ số 0–80 trong val (sample_idx của các CSV trong `exports/L3E`).
Ví dụ đã chạy (idx 40): GT 37 hộp; official_cl 25, our_cl 8, crn 28 (score ≥ 0.3). Nhớ: checkpoint official đã thấy mini-val lúc huấn luyện (nhiễm) nên không so sánh công bằng với `our_*`.

Muốn tự ngắm/đổi ngưỡng: mở CSV `exports/L3E/pred_*_ego.csv` (cột `sample_idx,class,x,y,z,w,l,h,yaw,vx,vy,score`, hệ ego: x tiến, y trái, z lên, yaw ngược chiều kim đồng hồ).

## 6. Chạy lại detector (BEVFusion / CRN) trên Kaggle với ảnh/frame bạn chọn
Local không có CUDA nên phải chạy trên Kaggle:
1. Dùng `tools/kgl.sh` (đọc token từ `D:\kaggle_mcp\.env`; lệnh trong `TOOLING.md`) để push kernel trong `notebooks/` (ví dụ `bev-real-l3c` cho LiDAR-only, `cr-infer` cho CRN). Cần bật GPU T4; hạn mức 30 h/tuần.
2. Notebook chạy suy luận với checkpoint trong `models/`, xuất CSV ego → tải về `exports/L3E/`.
3. Quay lại local, `view_detections.py` để xem trên ảnh thật.
Detector chỉ nhận đúng định dạng nuScenes (6 camera + LiDAR + radar + calib + ego pose) nên **không thể** đưa một ảnh JPG rời vào; mọi frame phải là keyframe/sweep của nuScenes hoặc dữ liệu được chuyển sang định dạng đó.

## 7. Tự thử với frame khác / viết code riêng
`tools/local/nuscenes_local.py` là thư viện nhỏ:
```python
import sys; sys.path.insert(0, 'tools/local')
from nuscenes_local import NuScenesMini
from models import load_occupancy
import torch
ds = NuScenesMini(); tok = ds.token('val', 5)
x = ds.bev_inputs(tok)                       # (7,200,200) float32 giống lúc train
model, ck = load_occupancy('models/occupancy/our_occupancy.pth')
with torch.no_grad(): pred = model(torch.from_numpy(x)[None]).argmax(1)[0]   # 0 free, 1 static, 2 object
```
Các hàm khác: `image_path(tok, cam)`, `keyframe_lidar`, `keyframe_radar`, `boxes`, `labels`, `gt_flow`, `history`.

## 8. Xử lý sự cố
| Triệu chứng | Cách xử lý |
|---|---|
| `ModuleNotFoundError: scipy` | đang gọi Python hệ thống, dùng `.venv_local\Scripts\python` |
| `FileNotFoundError` trong data | chạy `check_data.py`, hoặc đặt `NUSC_ROOT` |
| `torch.load ... weights_only` | script đã đặt `weights_only=False`; chỉ nạp file `.pth` tin cậy của dự án |
| Chậm | CPU 1 frame ~0.1–0.3 s; `--all` 25 s. Dựng nhãn cần sweep nên chậm hơn; thêm `--no-label` |
| Muốn xem ảnh | mở PNG trong `reports\local_runs\` |
