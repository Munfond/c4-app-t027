# Học tăng cường trên cấu hình LiDAR CARLA — bản nghiên cứu

Bản PPO nuScenes đã chạy đủ 12.288 bước vẫn giữ nguyên. Bộ mới dưới đây dùng **12 cấu hình LiDAR vật lý**, không phải giảm điểm sau khi đã thu LiDAR đầy đủ. Bản ngày 13/10 đã hoàn tất 48 capture, kiểm định 960 outcome và chạy PPO native đủ 8.192 bước / 256 cập nhật optimizer. Checkpoint chọn bằng validation tại bước 4.096. Report và policy đã được kiểm tra toàn vẹn. Không dùng pilot một route trước đó để thay thế tập train/validation/test.

## Giao thức đã chốt trước khi huấn luyện

- LiDAR: 16/32/64 kênh × 150/300/450/600 nghìn điểm/giây. Cấu hình mặc định là action 7: 32 kênh, 600 nghìn điểm/giây.
- CARLA Town01, trời quang, hai xe nền, 20 frame mỗi cấu hình. Hai route train, một route validation, một route test; route/seed khác nhau, không dùng lại route của pilot.
- Tổng: 48 capture, 960 outcome. Cùng route phải có **nhãn tham chiếu và ego pose giống hệt giữa 12 cấu hình**. Nếu không khớp, từ chối dữ liệu thay vì ghép gần đúng.
- Checkpoint occupancy LiDAR và adapter intensity thử nghiệm đều cố định theo SHA. Không train lại checkpoint perception. Camera phục vụ quan sát, không phải đầu vào model này.
- Frame 0 thu với cấu hình mặc định. Agent quan sát tín hiệu của cấu hình hiện tại, quyết định cấu hình cho **frame kế tiếp**. Mỗi episode chấm 19 quyết định; thời gian bootstrap được báo riêng.
- Actor nhận sáu đặc trưng từ điểm/intensity đang thu, độ trễ đã đo của lượt trước và one-hot cấu hình trước. Không nhận GT, chất lượng của các cấu hình chưa chọn, tên route hoặc seed.
- Reward: trung bình IoU occupied/object trên ô tham chiếu quan sát được, trừ phạt độ trễ và đổi cấu hình. Không tính chi phí tiền/GPU. Mốc 500 ms là nhịp dữ liệu nghiên cứu, không phải tiêu chuẩn an toàn ADAS.

PPO chạy 8.192 bước, đánh giá validation sau mỗi 1.024 bước **đã cập nhật optimizer**. Chọn checkpoint bằng validation; khóa checkpoint trước khi chấm test. So sánh với đủ 12 cấu hình cố định trên test, báo cả trường hợp không tốt hơn baseline.

## File và lệnh

Chạy tại root repo, dùng runtime `.venv-recovery312`. Collector chỉ xếp một lượt mỗi lần; không tạo collector thứ hai khi lượt hiện tại còn chạy. Các capture nghiên cứu được ẩn khỏi lịch sử demo mặc định; API `GET /api/v1/experiments?include_research=true` vẫn đọc được chúng.

```bash
# Tiếp tục capture bị ngắt có kiểm soát; thất bại kỹ thuật không tự retry.
.venv-recovery312/bin/python -m scripts.collect_native_rl_matrix \
  --resume --output data/native-rl-matrix-v1-20261013

# Chỉ chạy sau khi đủ 48 capture thành công. Output mới, không ghi đè.
.venv-recovery312/bin/python -m scripts.build_native_occupancy_replay \
  data/native-rl-matrix-v1-20261013 \
  --output data/native-rl-measured-v1-20261013

# Chỉ chạy nếu audit độc lập đã chấp nhận bộ đo.
.venv-recovery312/bin/python -m scripts.train_native_occupancy_ppo \
  data/native-rl-measured-v1-20261013/replay.json \
  --plan eval/recovery-mvp-2026-10-13/native-rl-training-plan.json \
  --output data/native-rl-ppo-v1-20261013
```

Capture plan: `eval/recovery-mvp-2026-10-13/native-rl-capture-plan.json` và seal `.sha256`. Training plan tương ứng: `native-rl-training-plan.json` và seal. Giữ `capture-state.json`, raw NPZ, `replay.json`, `audit.json`, policy ZIP, `report.json`, `test-traces.json` và các seal để tái kiểm tra. Không đưa raw/weights vào Git.

Collector giữ lock, hỗ trợ SIGTERM và đánh dấu capture bị ngắt. Một lượt native SIG11 có thể được retry thủ công duy nhất cho cả matrix bằng `--resume --retry-failed <exact-job-id>`; giữ job lỗi/partial artifacts trong `previous_job_ids` và `failed_retry`. Không retry để chọn metric đẹp hơn, không đổi cấu hình/split. Nếu lỗi lặp lại thì matrix vẫn incomplete và không được train. Measurement/trainer cũng ghi trạng thái incomplete khi bị ngắt hoặc lỗi; các file đã có được giữ lại. Thiếu dữ liệu, khác reference, thay checkpoint/adapter, giả observation hoặc pose trùng giữa các split đều không được chấp nhận.

## Giới hạn phải nói khi trình bày

Đây là RL offline trên bảng outcome đã đo từ mô phỏng, **chưa phải điều khiển sensor online**. Chưa đo thời gian đổi sensor thực tế. Chỉ có hai route train và một route test cùng Town01: đủ cho minh họa nghiên cứu nhỏ, không chứng minh ổn định ngoài thực tế. Reference là ô semantic LiDAR quan sát được và proxy chiều cao/footprint; ô chưa quan sát không được coi là free để tăng điểm. Gain intensity còn thử nghiệm. Không suy ra độ bền trước sương mù/mưa từ ảnh RGB; không có cam–radar–LiDAR fusion hay sensor-failure policy trong lần train này.

## Kết quả thực tế ngày 13/10/2026

| Chiến lược | Occupied IoU | Object IoU | p95 CPU | Quyết định test |
| --- | --- | --- | --- | --- |
| Mặc định 32 kênh / 600k điểm/s | 81,39% | 6,02% | 83,95 ms | 19 |
| PPO được chọn bằng validation | 81,39% | 6,02% | 83,95 ms | 19 |

PPO chọn action 7 ở cả 19 frame và không đổi cấu hình. Cấu hình cố định tốt nhất trên test cũng là action 7. Không tìm thấy cấu hình tốt hơn trong 12 action đã đo; giữ baseline là kết luận thực nghiệm, không phải lời LLM. Test chỉ có một route và object IoU thấp: không gọi agent/model là an toàn hoặc đủ tốt ngoài đời. Cần kiểm tra sâu reference/domain gap và bổ sung route chưa thấy; đổi mật độ sensor không thay thế huấn luyện/kiểm định perception.

Một lượt CARLA bị SIG11 trước khi có frame được thử lại đúng một lần, cùng cấu hình; lỗi gốc `724dbd7839944c7ca6c9852eb7e5346e` được giữ. Không loại frame test để tăng điểm. Audit tách train/validation/test theo route/seed và từ chối pose trùng. Source summary và report thật nằm ở `eval/recovery-mvp-2026-10-13/native-rl-matrix-audit-summary.json` và `native-rl-ppo-report.json`, có seal SHA256.

API mới: `GET /api/v1/experiments/native-rl` và `/native-rl/report`. Mở bot cạnh Lab → **Học tăng cường · 12 cấu hình LiDAR CARLA**. Chỉ mở mục này mới tải/poll evidence; không chạy simulator/training từ việc mở UI. Bảng chính so baseline/PPO; mở rộng để xem đủ 12 cấu hình, SHA và giới hạn.

Reference coverage được đo riêng: trên route test, mỗi frame chỉ có4–9 ô object và2.868–3.231 ô quan sát trong tổng40.000 ô. Chất lượng object vì vậy rất nhạy với sai số vài ô; không suy rộng6,02% hay81,39% thành kết luận cho toàn bộ môi trường. Chi tiết bốn route: `native-rl-reference-coverage.json`. Không lấy điểm pilot một route khác để thay điểm test.

Engineer review native được lưu riêng khỏi nuScenes, gắn hash báo cáo, có ba verdict accept/reject/needs_evidence. Phản hồi chưa tự cập nhật model hoặc tự train policy.

Nút “Xem capture mặc định của test” mở job `bc3ff6b1b0c047dba472ed86b770092e` theo ID đã liên kết với audit, trên workspace cạnh bot. Lịch sử mặc định vẫn ẩn hàng loạt job nghiên cứu; capture được mở cụ thể không bị polling lịch sử làm biến mất. Không tạo capture/inference khi bấm xem.
