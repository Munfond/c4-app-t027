# cam_lidar_radat_real_ws — Level 3 trên dữ liệu thật (nuScenes-mini)

Workspace làm việc cho **Level 3 (Advanced Research Lite)**: model học (pretrained và tự train) trên dữ liệu nuScenes-mini thật, so sánh với pipeline classical của Level 1, xuất kết quả sang MATLAB.
Workspace Level 1 (MATLAB/Simulink, mô phỏng Unreal) nằm ở `..\cam_lidar_radar_ws` và **không bị sửa** ở đây. Tài liệu yêu cầu Level 3: `..\docs\level3_training_pipeline_docs_vi`, `..\docs\level3_advanced_research_lite_docs_vi`.

**Đọc trước:** `reports\LEVEL3_FINAL_REPORT.md` (báo cáo cuối), `PROJECT_STATE.md` (tiến độ và bằng chứng), `NEXT_ACTIONS.md` (việc còn lại), `models\MODEL_ZOO.md` (checkpoint và số liệu).

## Nguyên tắc số liệu (áp dụng cho mọi file trong workspace)

- Tất cả số liệu là **nuScenes-mini VAL: 81 keyframe, 2 scene** (scene-0103, scene-0916). **Không** phải benchmark nuScenes đầy đủ.
- Checkpoint **official** đã train trên nuScenes trainval, trong đó có các scene mini, nên điểm của chúng trên mini VAL bị **contaminated**. Chỉ dùng làm tham chiếu tích hợp, không dùng để tuyên bố khả năng tổng quát hoá.
- Checkpoint **own** chỉ train trên mini TRAIN (323 keyframe, 8 scene); VAL không dùng để train và không dùng để chọn model (báo cáo epoch cuối).
- Nhãn `static` của occupancy là pseudo-GT suy từ LiDAR, không phải nhãn người gán.

## Cấu trúc

```text
models/            model zoo: lidar_only, camera_lidar, camera_radar, occupancy, temporal_flow (+ our_bevfusion_mini = artifact gốc gộp)
exports/L3E/       dự đoán ở khung ego chung (CSV + .mat) và loader MATLAB
fusion/            Stage D: late fusion Camera+LiDAR x Camera+Radar, Unified Object List (fusion/unified)
stage_e/           Stage E: classical (MATLAB Level 1, có shim toolbox) so với learned
stage_f/           Stage F: BEV occupancy học được
stage_g/           Stage G: temporal / occupancy flow
stage_h/           Stage H: cầu nối MATLAB risk (computeRiskFields của Level 1) trên frame thật
reports/           báo cáo cuối Level 3, đối chiếu checklist, hình tổng quan
frozen/            baseline đã đóng băng L3C-L3E (chỉ đọc, có SHA256SUMS)
notebooks/         mã nguồn các notebook Kaggle (build_*.py, .ipynb, kernel-metadata.json) và output nhỏ cần cho tái lập
tools/             kgl.sh, poll_kernel.sh: gọi Kaggle CLI mà không lưu token trong workspace
```

Định dạng đối tượng chung cho MATLAB: `sample_idx, class, x, y, z, w, l, h, yaw, vx, vy, score`; khung ego: x tiến, y trái, z lên, yaw ngược chiều kim đồng hồ từ +x. Lưới BEV: hàng theo +x, cột theo +y, ô 0.5 m, ±50 m, ranh giới nửa mở.



Các số liệu Stage E/F/G đã được tái lập **giống hệt** từ workspace này (so sánh JSON trước và sau khi gom).

## Hướng dẫn sử dụng

- `FILE_GUIDE.md` – chức năng của từng file/thư mục.
- `GUIDE_RUN_PYTHON_LOCAL.md` – chạy thật trên máy local (CPU) bằng `tools/local`: occupancy, flow, xem detection trên ảnh thật; đã kiểm parity 100% với Kaggle.
- `GUIDE_RUN_MATLAB.md` – demo classical/risk trên `data/` và `matlab/check_local_matlab.m` (12/12 PASS).
- `web/README.md` – giao diện web (Streamlit): camera, LiDAR/radar, occupancy/flow live, detection, tracking, risk (live bằng MATLAB Engine), classical, ablation, video mô phỏng Level 1. Chạy: `.venv_local\Scripts\streamlit run web\app.py --server.address localhost`.
