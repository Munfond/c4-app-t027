# PROJECT_STATE — Level 3 trên dữ liệu thật

Cập nhật: 25/09/2026 (Stage H xong). Mọi số liệu: nuScenes-mini VAL (81 mẫu). "contaminated" = model official đã train trên trainval.

## Bảng trạng thái

| Giai đoạn | Trạng thái | Kết quả chính | Bằng chứng |
|---|---|---|---|
| L3A/B Môi trường + dataset | PASS | Env BEVFusion dựng lại và đóng băng; nuScenes-mini 404 keyframe | `frozen/`, `models/*/environment.txt` |
| L3C/D Pretrained LiDAR, Camera+LiDAR | PASS | official LiDAR mAP 0.543 / NDS 0.563; Camera+LiDAR 0.570 / 0.576 (contaminated) | `frozen/L3C_L3E_v1` |
| L3E/G Export ego + import MATLAB | PASS | `exports/L3E` (CSV, .mat, loader đã chạy thật trong MATLAB) | `exports/L3E` |
| Visualization dữ liệu thật | PASS | 81/81 mẫu: 6 camera, box 3D, LiDAR BEV, GT so với dự đoán | `notebooks/bev-real-viz/out/viz` |
| Stage A: LiDAR-only tự train | PASS chuỗi đầy đủ | mAP 0.210 / NDS 0.232 (15 epoch, từ đầu); còn thiếu train, val chưa hội tụ | `models/lidar_only` |
| Stage B: Camera+LiDAR tự train | PASS chuỗi đầy đủ | mAP 0.192 / NDS 0.207, thấp hơn Stage A (nhánh camera overfit 323 mẫu) | `models/camera_lidar` |
| Stage C: Camera+Radar | Pretrained PASS; **own training CHƯA làm** (optional) | Audit radar PASS; CRN R18 pretrained mAP 0.433 / NDS 0.476 (contaminated) | `models/camera_radar` |
| Stage D: 3-sensor hybrid late fusion | PASS (baseline) | official CL + CRN 0.574 / 0.578, không hơn Camera+LiDAR (0.570 / 0.576) trong sai số ±0.003 | `fusion/README.md` |
| Stage E: Classical vs Learned | PASS (đã chạy lại với toolbox thật) | classical (code Level 1, không chỉnh ngưỡng) F1 0.46; learned pretrained F1 0.76-0.90 (contaminated) | `stage_e/README.md` |
| Stage F: Learned occupancy | PASS chuỗi đầy đủ | mIoU 0.549; IoU vùng chiếm 0.423 (quy tắc tương thích nhãn 0.384; classical 0.289) | `models/occupancy` |
| Stage G: Temporal / flow | PASS cơ học, **flow chưa đạt chất lượng** | occupancy mIoU 0.569 (1 frame 0.552); flow EPE 3.52 m/s so với zero-flow 3.79 | `models/temporal_flow` |
| Stage H: Tổng kết Level 3 | PASS (cầu nối risk + báo cáo cuối + checklist); runtime chưa đo thống nhất | Risk Level 1 trên 81 frame thật: tương quan hạng với oracle 0.94 (occupancy học + flow detection), 0.86 (classical), 0.74 (flow học được); lợi ích flow 19.9% (< ngưỡng 25%) | `stage_h/README.md`, `reports/LEVEL3_FINAL_REPORT.md`, `reports/FINAL_CHECKLIST_STATUS.md` |

## Vấn đề đã biết (không che giấu)

1. **Đã giải quyết (25/09/2026):** các toolbox MATLAB còn thiếu (Computer Vision, Lidar, Sensor Fusion and Tracking, Navigation, Radar, Automated Driving, Simulink 3D Animation…) đã được cài. Stage E đã chạy lại với hàm toolbox thật; kết quả khớp bản shim (F1 0.459 so với 0.460), nên các kết luận không đổi. Shim vẫn còn trong `stage_e/matlab/shims`, chỉ dùng khi thiếu toolbox.
2. Ngưỡng classical của Level 1 (đặt cho cảnh Unreal) **không** được chỉnh lại; kết quả classical là "pipeline hiện có đặt lên dữ liệu thật", không phải mức tối ưu của classical.
3. Stage B thấp hơn Stage A; Stage G: flow học được không dùng được; nên dùng flow suy ra từ vận tốc detection (nhưng số đo hiện có đến từ model official, contaminated).
4. Không có GT occupancy dày trong nuScenes-mini: nhãn `static` là pseudo-GT từ LiDAR; chỉ số occupancy không so được với Occ3D / SurroundOcc / TPVFormer.
5. Kết quả một seed, 81 mẫu: chênh lệch cỡ 0.01 chưa kết luận được. Số official chạy lại trong môi trường đóng băng lệch tới 0.003 so với lần đầu (nhiễu GPU).
6. Một patch nguồn duy nhất trên đường train của mmdet3d (`np.long` sang `np.int64`, `models/*/config/numpy_alias_patch.diff`); không đổi dependency nào.
7. Risk không có GT trên nuScenes-mini: Stage H chỉ đo độ nhạy của điểm risk theo chất lượng perception (oracle = cùng công thức trên GT), không kiểm chứng risk.
8. Dữ liệu tải về `notebooks/bev-real-train-a|b/out` (checkpoint, log gốc) chỉ còn ở `D:\kaggle_mcp\notebooks\...` (đã có bản sao trong `models/`).

## Quyết định của người dùng còn hiệu lực

- Không train thêm LiDAR chỉ để tăng metric trước khi cả pipeline Level 3 PASS; không làm lại Stage A/B; không thay dependency đang chạy được; không xoá hoặc ghi đè checkpoint.
- Thứ tự: C, D, E, F, G, H. Own Camera+Radar training là optional.
