# PPO chọn LiDAR trong capture CARLA — 14/10/2026

Policy native đã được train trước đó được giữ nguyên và gọi **trong lúc CARLA đang capture**. Không chạy optimizer trong lượt này: đây là inference online của policy đã học, không phải online RL training.

## Luồng thật

CARLA chạy đồng bộ, một process sở hữu tick. Tạo sẵn 12 LiDAR vật lý: 16/32/64 kênh × 150/300/450/600k điểm/s, cộng semantic LiDAR tham chiếu và camera. Chỉ raw XYZ/intensity của LiDAR đang chọn được gửi qua IPC sang process perception/PPO. Không đưa nhãn, actor pose, weather GT hoặc các stream chưa chọn vào observation. Parent đọc tín hiệu hiện tại và latency CPU đã đo, rồi chọn sensor dùng ở **frame kế tiếp**. Response phải khớp index, frame ID và SHA raw; stale response, timeout, profile ngoài catalog đều làm dừng lượt thử. Camera/GT được dùng để review và chấm ô quan sát sau capture.

Cả 12 sensor vẫn chạy. Đây là chọn input vào model, **chưa phải tắt cảm biến, tiết kiệm điện hay giảm tổng tải simulator**. TM autopilot giữ việc lái xe; PPO không điều khiển ga/phanh/vô-lăng. Chỉ checkpoint occupancy LiDAR dùng được trong vòng này, chưa có camera/radar fusion, sensor failure, ROS2 hoặc MultiDiscrete.

## Evidence thật đã hoàn tất

| Lượt thử | Frame | Action đang dùng (đánh số từ 0) | Kết luận |
| --- | --- | --- | --- |
| Diagnostic lịch cố định | 4 | 7 → 0 → 11 → 7 | Kiểm chứng stream vật lý được đổi đúng. **Không phải quyết định PPO.** |
| Policy PPO frozen | 4 | 7 → 7 → 7 → 7 | 3 quyết định trong capture trực tiếp; vẫn giữ mặc định32 kênh/600k. Chưa chứng minh thích nghi tốt hơn. |

Cùng Town01/clear/route110/seed210; reference SHA giống hệt. Checkpoint/policy không đổi từ báo cáo native đã chọn bằng validation. Metrics smoke không thay thế test offline hoặc chứng minh generalization. `eval/native-online-2026-10-14/` giữ plan/report/audit sealed; raw/camera ngoài Git.

Bản diagnostic đầu tiên chỉ lưu thời gian feature+model. Báo cáo gốc được giữ nguyên; snapshot UI không hiển thị trường cũ bị đặt nhãn model-only sai. Lượt PPO đo riêng feature+model và chọn profile; frame0 đo440,6ms +68,6ms, các frame sau feature+model khoảng84–89ms. Vì vậy nhịp0,5 giây **sim-time** không chứng minh real-time wall-clock. Không xóa frame đầu để làm đẹp số đo.

Kế hoạch đối chiếu20 frame đã đăng ký **trước chạy** trên route112/seed212. Baseline đầu bị chặn trước launch bởi guard RAM10 GiB, xử lý0 frame; giữ output `data/native-online-full20-20261014`. PPO20 chưa chạy, không có kết quả giả. Khi đủ RAM/GPU khỏe, chạy baseline trong output retry riêng và PPO theo plan đã seal, rồi chỉ so chất lượng nếu reference SHA khớp.

## Xem trên Lab

Mở `/lab`, bot → nguồn **CARLA** → **PPO trong CARLA · xem quyết định từng frame** → **Xem capture & quyết định**. Preview mở ở workspace cạnh bot, không thêm tab điều hướng. Có Play/Pause, Previous/Next, thanh frame, loop, tốc độ; camera/model/reference đồng bộ. Frame đang hiển thị gắn cấu hình thật và quyết định cho frame sau. Chỉ đọc bản ghi, không tạo job/simulator/train.

API: `GET /api/v1/experiments/native-online`, `/{run}/report`, `/{run}/camera?index=0`, `/{run}/predictions/occupancy_lidar/0`, `/{run}/reference/0`. Run ID được allowlist. Artifacts phải khớp seal; camera/prediction/reference bị sửa bị chặn. Các hash dùng để kiểm tra dữ liệu local, không phải chứng nhận độc lập từ bên thứ ba. Bấm tải snapshot để xem trace; report gốc giữ riêng trong evidence.

Đã kiểm tra HTTP qua frontend: hai clip ×4frame ảnhPNG640×360 decode được, occupancy/reference đủ40.000 ô, hai actor geometry/frame. Ngoài frame trả404, index20 trả422, run lạ trả404. Native offline policy/report SHA vẫn giữ nguyên. Kết quả8 case tại `http-contract-results.json`. **Chưa kiểm tra render browser thực tế** vì tab trình duyệt đang là trang lỗi; API/image checks không thay thế visual QA.

## Tiếp tục sau khi runtime khỏe

GPU hiện trả `Unknown Error / No devices were found` từ nvidia-smi; kernel có lỗi nvidia-modeset sau suspend. Chưa xác định nguyên nhân gốc. Managed CARLA có preflight từ chối GPU lỗi trước launch và không reset driver. RAM lúc kiểm tra lại chỉ8,1GiB khả dụng. Giữ guard10GiB, không dừng ứng dụng khác hoặc ép launch.

Sau khởi động lại, kiểm tra `nvidia-smi` và `free -h`; mount Windows read-only nếu cần raw nuScenes. Dịch vụ web không cần GPU để xem bản ghi.

```bash
# Tại root repo. Không chạy hai collector cạnh tranh.
# Output retry phải mới; giữ lần bị chặn trước đó.
.venv-recovery312/bin/python -m scripts.run_native_online_ppo \
  --output data/native-online-full20-retry1-20261014 \
  --mode full_baseline --route 112 --seed 212 --frames 20 --run-sealed-plan

# Chỉ sau baseline thành công; plan PPO đã niêm phong.
.venv-recovery312/bin/python -m scripts.run_native_online_ppo \
  --output data/native-online-ppo20-20261014 \
  --mode ppo --route 112 --seed 212 --frames 20 --run-sealed-plan
```

Nếu reference khác, báo không thể so cùng cảnh; không ghép gần đúng hoặc chọn scene có điểm đẹp. Test offline cũ không dùng để retune. Ưu tiên kiểm tra đủ20 frame và browser; weather vật lý/radar/ROS2 là phần còn thiếu của mục tiêu lớn, không coi MVP này đã hoàn thành toàn bộ plan.
