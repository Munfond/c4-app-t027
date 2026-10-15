# PointPillars — 20 mẫu trải trên episode 60 giây

Ba cấu hình dùng cùng capture/hash và indices 0,60,…,1140. Timestamp span của mẫu:
57 giây; không phải model chạy ở cadence 3 giây hoặc replay policy liên tục.
Capture đầy đủ đã verify 1.200 frame/20 streams. Raw và checkpoint ở ngoài Git.

| Cấu hình | Wall mean / p95 (ms) | CUDA activity/call (ms) | Ghép mục tiêu/frame |
|---|---:|---:|---:|
| Full FP32 | 76,72 / 80,57 | 63,10 | 30/62 |
| Half points FP32 | 67,87 / 70,55 | 54,52 | 26/62 |
| Full AMP | 53,42 / 55,81 | 40,09 | 30/62 |

AMP giảm wall mean khoảng 30,37% và CUDA activity/call khoảng 36,47% so với
FP32, giữ cùng số lượt ghép trong mẫu này. Giảm nửa điểm chỉ giảm wall khoảng
11,53% nhưng mất 4 lượt ghép. Đây là lý do thử AMP trước khi giảm density;
**không phải lựa chọn profile đã nghiệm thu**. 19/20 mẫu AMP vẫn vượt 50 ms,
nên chưa đáp ứng chu kỳ inference 20 Hz ngay cả trước monitor/IO/chuyển cấu hình.

62 lượt target/frame tương quan của một cảnh, ghép class-agnostic tâm XY ≤2 m,
score ≥0,3 và visibility semantic reference64. Không phải mAP, complete precision,
segmentation IoU hay recall vận hành ngoài thực tế. GT scope: world vehicle/walker
actors; static/parked mesh mapping/ontology còn chưa kiểm định. Không đồng nhất
reference visibility với observability của LiDAR32.

CUDA dùng CUPTI trong pass riêng; wall pass không profiler, warmup không tính.
CARLA đã dừng khi chạy detector; chưa đo tổng GPU/window, deadline online hoặc
segmentation/radar task. `selection=null`, `measured_perception_replay_ready=false`.
Không dùng archive này để train BC/PPO hoặc tự gắn cờ validated.

`summary.json` pin SHA report/geometry của từng variant. `capture-manifest.json`
pin toàn bộ source; `capture-verification.json` là output kiểm tra thật. Thư mục
`capture/` chỉ giữ metadata/GT của 20 mẫu đã chọn; dữ liệu cảm biến đầy đủ không
có trong archive. `artifact-manifest.json` kiểm checksum các file trong bundle;
nó không thay kiểm định chất lượng/engineer review. Hình `comparison.png` là số đo
thật, đã được mở kiểm tra; không phải UI screenshot.

Kết quả pilot 8 variant trên bot trước đó thuộc capture 20 frame ban đầu. Không
đổi nhãn pilot cũ thành run này hoặc so trực tiếp tỷ lệ khác mẫu như cùng bộ val.

Lệnh tái lập, chọn output mới:

```bash
data/runtime/detector-env/bin/python scripts/bench_carla_detector.py \
  data/active-sensing/rig-town01-60s-retry-20261008 --family pointpillars \
  --frames 20 --frame-stride 60 --output data/active-sensing/pp-sparse-recheck
```
