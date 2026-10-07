# Thu dữ liệu cảm biến cho active sensing

Ngày nghiệm thu: 08/10/2026. Đây là bộ thu raw + calibration + ground truth,
**chưa phải** adapter inference BEVFusion/CRN, measured replay hay policy RL đã train.
Không đổi cadence 0.5 s của các checkpoint occupancy đang dùng trên web.

## Đã chạy thật

- CARLA 0.9.16, RTX 2050 4 GB, Town01/clear, seed 7, 8 xe, không người đi bộ.
- 20 frame liên tiếp, dt = 0.05 s; khoảng cách frame đầu/cuối 0.95 s.
- 6 RGB 640×360, 6 semantic camera GT, LiDAR 32, LiDAR 64, semantic LiDAR GT 64,
  5 radar: tổng 20 stream. Tất cả packet cùng frame và timestamp snapshot.
- Cả 8 actor đều được semantic LiDAR quan sát trong mọi frame của đoạn ngắn.
- 305.093 điểm LiDAR 32; 611.523 điểm LiDAR 64; 1.113.048 điểm semantic LiDAR.
- Verify checksum, kiểu dữ liệu, shape, cadence, intrinsic/extrinsic và đổi hệ tọa độ thành công.
- Reader đưa dữ liệu thật qua cả 24 **profile ứng viên**. Scheduler chọn 5/10/20 slot
  tương ứng từng Hz trên 20 frame. Chưa chạy detector ở các slot đó.
- 163 automated tests qua; Ruff qua. Hình audit calibration đã được mở và kiểm tra:
  hộp GT chiếu lên xe trong camera, cloud/radar cùng hệ ego. Đây không phải ảnh dự đoán.

Raw giữ ở `data/active-sensing/rig-nearby-20261008/` ngoài Git.
Bản ghi nghiệm thu nhẹ nằm ở `eval/full-rig-2026-10-08/`, gồm manifest, metadata/actor GT
của frame đầu, verification, acceptance và `calibration-audit.png`.
SHA manifest: `c72255c929c32d55c07fa1ec48ba0dc4504cf4142b2316714eabbc8ee7f581b3`.

Smoke đầu tiên hai frame với traffic ngẫu nhiên có 0 actor nhìn thấy. Nó chỉ kiểm tra
stream/calibration; không dùng làm bằng chứng detection. Vì vậy CLI thêm lựa chọn
`nearest_spawn` để chọn spawn point gần ego, có ghi rõ trong manifest. Seed cố định;
xe vẫn dùng Traffic Manager, policy sensing không điều khiển xe.

## Lệnh

Từ root repo, dùng runtime matching CARLA đã cài:

```bash
.venv-experiments/bin/python scripts/collect_active_sensing.py capture \
  --seconds 1 --hz 20 --map Town01 --weather clear --seed 7 \
  --vehicles 8 --include-64 --output data/active-sensing/episode-new

.venv-experiments/bin/python scripts/collect_active_sensing.py verify \
  data/active-sensing/episode-new

MPLCONFIGDIR=/tmp/p027-matplotlib .venv-experiments/bin/python \
  scripts/preview_sensor_episode.py data/active-sensing/episode-new \
  --output eval/episode-new/calibration-audit.png
```

CLI cho 0.1–120 s; mặc định 20 Hz, có 2 Hz cho smoke nhẹ. Chỉ capture 20 Hz mới đủ dữ liệu
so scheduler 5/10/20 Hz. `--include-64` thêm LiDAR 64 thực, không suy ra từ LiDAR 32.
`--traffic-placement spawn_random` giữ cách chọn spawn ngẫu nhiên; mặc định `nearest_spawn`.
Route highway dùng Town04 và placement đã kiểm tra của capture cũ.

Camera cho 640×360 hoặc 1280×720, FOV ngang 100°. Không tự resize camera trong calibration.
Chưa coi rig này là nuScenes-equivalent; adapter model cần dùng intrinsic đã ghi và augmentation
đúng config. Không đổi thông số model để giả vờ sensor mới có cùng phân phối huấn luyện.

Không ghi đè thư mục đã tồn tại. Script kiểm tra dung lượng bảo thủ trước khi khởi động:
ảnh raw + điểm raw/ego + headroom/log. Với ổ còn khoảng 12 GB, **không** tự thu episode dài
120 s ở full rig. Chọn ổ đủ trống hoặc chia capture ngắn; episode gốc vẫn phải cùng một split.
Đây là kiểm tra disk, không phải dự đoán chính xác kích thước PNG/NPZ nén.

Managed mode dùng `.env` `CARLA_SERVER_EXECUTABLE` đã cấu hình, server mới + client riêng
mỗi capture, tự dừng đúng server của mình khi xong/lỗi. Lock dùng chung với worker web;
không capture đồng thời cùng simulator. Nếu không cấu hình binary, CLI dùng external server
và không dừng nó. Chỉ manifest `status=complete` mới được đọc; lỗi/cancel/verify thất bại
không để lại manifest hoàn tất. Log/partial files giữ để điều tra.

## Contract dữ liệu

- `inputs/frame_NNNNN/`: RGB PNG, LiDAR NPZ và radar NPZ. Không chứa nhãn GT.
- `ground_truth/frame_NNNNN/`: camera tag uint8, semantic LiDAR và actor boxes/velocity.
- `frame_NNNNN.json`: đường dẫn, SHA256/byte, frame/timestamp, pose sensor/world/ego,
  camera K và optical extrinsic, số phần tử, ego speed (odometry).
- `manifest.json`: phiên bản/rig, scenario, realized population, từng frame, thống kê stream,
  provenance và limitations. `verification.json`: kết quả audit.

Raw CARLA: x trước/y phải/z lên. Ego Lab: x trước/y trái/z lên, gốc xấp xỉ đáy bounding box ego.
Camera optical: x phải/y xuống/z trước; K dùng FOV ngang và pixel width/height thật.
Box GT hiện chỉ gồm actor được episode spawn. Xe đỗ/prop tĩnh trên map chưa có
box annotation đầy đủ; cần quy tắc coverage/ignore trước khi tính false positives.
Không coi bản ghi này là detection-eval ready chỉ vì có box.

Actor velocity là vận tốc world được biểu diễn trong trục ego; **không** phải vận tốc tương đối
đã bù chuyển động ego. Box lấy full transform của bounding box, không chỉ yaw actor.

LiDAR input giữ XYZI CARLA, intensity 0..1 nguyên bản. Semantic LiDAR là sensor tham chiếu
độc lập; không gán tag của điểm reference cho điểm input theo index. Muốn đánh giá segmentation
input phải có bước matching/valid mask được kiểm chứng, không so hai array khác điểm trực tiếp.
Camera GT lấy **kênh đỏ trong raw BGRA**, không lấy màu palette làm class ID.

Radar lưu `[radial_velocity, azimuth, altitude, depth]`, chuyển polar sang XYZ rồi đổi ego.
Không có RCS hoặc full `vx_comp/vy_comp`; reader/gate giữ cờ unavailable. Chưa dùng nó để
chạy CRN pretrained nuScenes bằng cách điền số giả. Weather clear/rain/fog chỉ là weather renderer;
chưa có corruption vật lý LiDAR/radar được kiểm định.

`RawEpisode.inputs()` chỉ đọc input/odometry, tính brightness/contrast/return ratio/radar count;
không đưa weather GT, actor boxes, semantic labels, IoU hay cost GT cho policy actor.
Chi phí monitoring này vẫn cần cộng vào phép đo perception sau này. `age_ms=0` hiện là
capture đồng bộ offline, không phải phép đo latency/age của một dịch vụ online.

## Cổng tiếp theo

1. Khôi phục/chốt checkpoint detector và runtime CUDA riêng; hiện không có
   `our_lidar.pth`, `our_bevfusion.pth`, checkpoint detection chính thức hoặc CRN trên máy.
2. Adapter LiDAR trước, smoke inference và đối chiếu projected GT/canonical box axes.
   Mỗi artifact ghi checkpoint SHA/config SHA; không lấy metric nuScenes cũ cho CARLA mới.
3. CL/radar/segmentation chỉ mở sau kiểm chứng riêng; giữ profile ứng viên chưa đạt cổng ở trạng thái disabled.
4. Đo tổng GPU work/window thật cho 2–3 profile trước khi mở 12–24; cùng capture, same task,
   giữ môi trường/map/seed chưa thấy cho test. Dữ liệu đầu vào này chưa đủ cho trainer.
5. BC → Discrete masked PPO → so full/min/rule/RL. ROS online và MultiDiscrete triển khai sau.

Nguồn contract: [CARLA 0.9.16 sensors](https://carla.readthedocs.io/en/0.9.16/ref_sensors/)
và [bounding-box projection](https://carla.readthedocs.io/en/0.9.16/tuto_G_bounding_boxes/).
