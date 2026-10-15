# Dataset từ prompt agent — 07/10/2026

LLM đề xuất cấu hình LiDAR → CARLA thu dữ liệu → checkpoint occupancy_lidar chạy CPU → so sánh và chọn cấu hình.

Prompt gốc:

Tôi muốn tối ưu cấu hình LiDAR để giảm lượng dữ liệu nhưng giữ chất lượng output của checkpoint occupancy_lidar. Tạo dữ liệu CARLA Town01 trời quang, 4 xe, 0 người đi bộ, seed 42, 20 frame mỗi cấu hình. Baseline 32 kênh, 600000 điểm/giây, tầm quét 100m. Agent hãy tự đề xuất 3 profiles tiết kiệm dữ liệu: một profile chỉ giảm số điểm/giây, một profile giảm số kênh và số điểm/giây, một profile giảm tầm quét và số điểm/giây; giữ FOV và vị trí lắp như baseline. Chấp nhận occupied IoU giảm tối đa 0.02, chỉ chọn cấu hình khi dữ liệu tham chiếu khớp. Thu dữ liệu cho mỗi profile, chạy qua checkpoint và giải thích lựa chọn.

4 trials succeeded, 20 frame/trial; 80 input NPZ, 80 ảnh camera và 80 prediction. Tất cả reference hashes khớp baseline.

| Cấu hình | Kênh | Điểm/giây | Tầm quét (m) | Occupied IoU | Giảm IoU | Giảm dữ liệu |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 32 | 600,000 | 100 | 0.3377 | 0.0000 | 0.0% |
| profile_points_reduction | 32 | 300,000 | 100 | 0.2992 | 0.0384 | 50.2% |
| profile_channels_points_reduction | 16 | 300,000 | 100 | 0.3008 | 0.0369 | 50.3% |
| profile_range_points_reduction | 32 | 150,000 | 50 | 0.2267 | 0.1110 | 76.1% |

**Lựa chọn tạm thời: baseline.** Cả 3 profiles tiết kiệm vượt ngưỡng giảm IoU 0,02.

Chỉ mục: dataset-index.json. Mỗi record liên kết prompt/profile/frame/input_npz/prediction_json.
Input model: x[[0,1,2,3]][None] có shape (1,4,200,200). Output: 200×200 class IDs free/static/object.
Đã đọc lại một input NPZ và chạy checkpoint độc lập với CARLA; output khớp prediction đã lưu (offline-check.json).

Toàn bộ dữ liệu: D:\CARLA\runs\prompt-lidar-dataset-20261007-002521
Nhóm file báo cáo: comparison.json, agent-summary.json, study-start.json, dataset-index.json, offline-check.json.

Labels là occupancy proxy trên observed cells. Kết quả chỉ áp dụng tạm thời cho Town01/seed42/các cấu hình đã thử; chưa chứng minh cấu hình tối ưu chung.
