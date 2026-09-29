# Đối chiếu `docs/15_FINAL_CHECKLIST.md` (level3_training_pipeline_docs_vi) với bằng chứng

Ký hiệu: [x] đạt, có bằng chứng; [~] đạt một phần; [ ] chưa làm.

## Environment
- [x] freeze environment: `models/*/environment.txt` (pip freeze, conda list, GPU, CUDA, nvcc, phiên bản Python/torch/mmcv/mmdet/mmdet3d/spconv), gói env kèm SHA-256 (`environment_archive_SHA256.txt`); env Camera+Radar riêng `models/camera_radar/environment_camera_radar.txt`
- [x] git SHA: mmdetection3d v1.4.0 (environment.txt), CRN commit `5e9d2fa2f91c714b297e75ca666d27fc4ad0d13d`
- [x] CUDA / GPU info: Tesla T4, driver 580.159.04, nvcc 12.8 (BEVFusion); CUDA 11.1 toolkit chỉ để biên dịch op CRN

## LiDAR-only (`models/lidar_only`)
- [x] smoke train · [x] train (15 epoch) · [x] checkpoint `our_lidar.pth` · [x] reload · [x] inference · [x] evaluate (mAP 0.210 / NDS 0.232)
- [x] export: `exports/L3E/pred_our_lidar_ego.csv`, `own_models_predictions.mat` (MATLAB đọc được)

## Camera+LiDAR (`models/camera_lidar`)
- [x] khởi tạo đúng: LiDAR branch từ `our_lidar.pth`, Swin-T ImageNet, không nạp checkpoint fusion official (log kiểm tra)
- [x] train (7 epoch) · [x] checkpoint · [x] reload · [x] inference · [x] evaluate (0.192 / 0.207)
- [x] export: `exports/L3E/pred_our_bevfusion_ego.csv`

## Camera+Radar (`models/camera_radar`)
- [x] model đã chọn theo audit (CRN R18; `BEVFusion-R` không tồn tại thành repo công khai)
- [ ] train / checkpoint riêng `our_camera_radar.pth`: **chưa làm** (optional theo quyết định)
- [x] evaluate / export cho checkpoint **pretrained** (0.433 / 0.476; `pred_camera_radar_ego.csv`, `.mat`)

## Occupancy (`models/occupancy`)
- [x] checkpoint `our_occupancy.pth` · [x] IoU / mIoU (0.423 / 0.549) · [x] visualization · [x] MATLAB export (`matlab/occupancy_predictions.mat`, loader chạy thật)
- [~] nhãn `static` là pseudo-GT từ LiDAR; không có GT occupancy dày trong mini

## Temporal / Flow (`models/temporal_flow`)
- [x] checkpoint `our_flow.pth` · [x] flow output · [x] EPE · [x] risk bridge (`stage_h`, dùng flow suy ra từ detection)
- [~] chuỗi cơ học PASS nhưng **chất lượng flow học được không đạt** (EPE 3.52 so với zero-flow 3.79; xem `models/temporal_flow/README.md`)

## PASS cuối theo từng nhánh: TRAIN → CHECKPOINT → RELOAD → INFERENCE → EVALUATION → EXPORT → MATLAB

| Nhánh | Trạng thái |
|---|---|
| LiDAR-only | PASS |
| Camera+LiDAR | PASS |
| Camera+Radar | pretrained PASS; own training chưa làm |
| Occupancy | PASS |
| Temporal / Flow | PASS cơ học; chất lượng flow chưa đạt |

## Mục khác trong yêu cầu (`docs/10`, `11`, `12`, `13`)
- [x] Detection mAP / NDS · [x] Occupancy IoU / mIoU · [x] Flow EPE (+ góc, false flow) · [~] Runtime: có số rời rạc trên phần cứng khác nhau, chưa đo thống nhất (`reports/LEVEL3_FINAL_REPORT.md` mục 6)
- [x] So sánh 4 dòng Official LiDAR / Official Camera+LiDAR / Our LiDAR / Our Camera+LiDAR (`models/our_bevfusion_mini/README.md`) và ghi rõ contamination
- [x] Common object format, toạ độ ego (x tiến, y trái, z lên, yaw ngược chiều kim đồng hồ), MATLAB đọc và vẽ không đảo trục (5 loader đã chạy thật)
- [x] Demo: 6 camera + box 3D, LiDAR BEV, GT so với dự đoán, Camera+LiDAR, Camera+Radar, Unified objects, occupancy, flow, risk (`reports/level3_overview.png`); mọi ảnh render từ run của dự án
- [x] Trình bày: nêu rõ checkpoint official / của dự án, split, metric, giới hạn (`reports/LEVEL3_FINAL_REPORT.md`)
