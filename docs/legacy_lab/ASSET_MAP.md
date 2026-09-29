# Bản đồ tài sản chuyển từ web Streamlit cũ (cam_lidar_radat_real_ws/web)

| Vị trí trong P-027 | Nội dung | Git | Dùng cho |
|---|---|---|---|
| `legacy/streamlit_lab/web/` | app.py, panels.py, tables.py, tracking.py, matlab_bridge.py | có | Logic tham chiếu để port sang FastAPI (`src/`) |
| `legacy/streamlit_lab/tools/local/` | nuscenes_local.py, models.py (đọc nuScenes, dựng BEV, nạp U-Net) | có | Phụ thuộc bắt buộc của panels.py |
| `legacy/streamlit_lab/matlab/` | risk_from_arrays.m, classical_from_points.m, ... | có | Cầu nối MATLAB (chỉ máy dev, server khách nên bỏ) |
| `frontend/public/sim/` | 3 video mp4, figure PNG, final_report.pdf + 6 trang PNG, ablation PNG | có | Mục "Mô phỏng Level 1", "Ablation" |
| `frontend/public/lab/` | PNG kết quả Stage E-H, demo_images, training_curves | có | Trang kết quả/giải thích model |
| `data/nuscenes/` | v1.0-mini, maps, samples (6 cam + LiDAR + 5 radar, 404 keyframe) | ignore | Camera, LiDAR+Radar, Occupancy live |
| `data/lab/models/` | 7 checkpoint .pth (occupancy x3, flow x4) + metrics/README/config | ignore | Occupancy, Flow live |
| `data/lab/exports/L3E`, `fusion/unified` | CSV detection tính sẵn (6 nguồn) + gt_ego.csv + operating_points.json | ignore | Detection, Tracking |
| `data/lab/stage_*/results`, `stage_h/*.mat` | JSON chỉ số Stage E-H, risk_out/risk_inputs.mat | ignore | Bảng chỉ số, Risk heatmap |
| `data/sim/` | ablation_summary.csv, manifest, risk_verification.json | ignore | Bảng ablation Level 1 |
| `docs/legacy_lab/` | README/PROJECT_STATE/... của lab cũ, LEVEL3_FINAL_REPORT | có | Tài liệu nội dung |

## Cố ý KHÔNG copy
- `data/sweeps` (LiDAR sweeps 2,3 GB): chỉ cần để tính nhãn pseudo-GT static khi so IoU occupancy live. Copy `data/sweeps/LIDAR_TOP` nếu cần mục đó.
- Checkpoint detection BEVFusion/CRN/LiDAR-only (~600 MB): web chỉ hiển thị kết quả CSV tính sẵn, cần CUDA để chạy lại.
- File `.mat` lớn (flow_predictions, demo_session.mat 45 MB, sensors.mat).

## Lưu ý khi port
- Đường dẫn cứng trong code cũ: `tables.py` (SIM_RUNS), `matlab_bridge.py` (PROJ). Code cũ chưa chạy được nguyên trạng trong P-027; `NUSC_ROOT` env trỏ tới `data/nuscenes` cho `nuscenes_local.py`.
- `data/` nằm trong .gitignore và checkpoint cần đưa lên server bằng cách khác (volume/artifact storage) khi làm vấn đề 2.
