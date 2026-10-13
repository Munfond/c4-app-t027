# Hướng dẫn sử dụng Perception Lab

Bấm **Hướng dẫn** ở đầu trang để đọc ngay trên web. Mục tiêu của Lab là xem dữ liệu cảm biến, hiểu kết quả mô hình và kiểm tra đề xuất cấu hình bằng bằng chứng.

## Xem một đoạn đường trong 1 phút

1. Mở **Lab**. Chọn **Scene** (một đoạn đường) và **Frame** (một thời điểm). Trên màn hình nhỏ, mở **Thiết lập** trước.
2. Mở **Cảm biến → Camera 360°** để xem cảnh. Chuyển sang **LiDAR + Radar** để xem điểm đo trong không gian. Bỏ tick LiDAR hoặc Radar để ẩn từng lớp; bật lại để đối chiếu.
3. Đổi **Màu LiDAR → Phân đoạn** nếu muốn xem nhóm điểm ngữ nghĩa. Radar giữ màu theo tốc độ, không được gán lớp người/xe.
4. Mở **Kết quả mô hình** và chọn bài toán. Camera và kết quả dùng chung frame; đọc tên model và sensor đầu vào.
5. Bấm **Phát** để xem liên tục. Dùng **Tạm dừng**, thanh thời gian, frame trước/sau, tốc độ và **Lặp** để kiểm tra một chi tiết.

## Mỗi kết quả có ý nghĩa gì?

- **Detection 3D:** hộp cho biết vị trí, hướng và kích thước vật thể. Hình xe minh họa từ box không phải segmentation.
- **Seg3D:** màu phân loại trên từng điểm; ví dụ đường, xe, người. Model chuyển từ dataset khác vẫn là thử nghiệm.
- **Occupancy:** lưới ô trống/nền tĩnh/vật thể nhìn từ trên xuống. Bản hiện tại chưa là bản đồ 3D đầy đủ.
- **Flow:** chuyển động ước lượng giữa các thời điểm, còn hạn chế.
- **Risk:** điểm rủi ro chưa hiệu chuẩn, không phải xác suất va chạm.

**Model** là dự đoán; **Reference** là nhãn/hình học tham chiếu để kiểm tra. Trong preview CARLA, màu xám là vùng reference chưa quan sát. Dấu + là gốc xe mình; hướng trước lên trên. Chọn actor ở chế độ Reference để xem khoảng cách/kích thước và phép chiếu hình học trên camera; đó không phải model đã nhận đúng actor.

## Dùng agent / CARLA

1. Mở nút **Agent** ở góc dưới; bot nằm cạnh workspace. Chọn **nuScenes replay** hoặc **CARLA**.
2. Muốn xem ngay: CARLA → **PPO trong CARLA · xem quyết định từng frame** → **Xem capture & quyết định**. Play phát lại capture đã ghi, không mở mô phỏng mới.
3. Muốn xem kết quả học: mở **Học tăng cường · 12 cấu hình LiDAR CARLA**. So PPO với cấu hình cố định, đọc chỉ số, nguồn và giới hạn. Nếu không tốt hơn, giữ baseline; không ép đổi sensor cho đẹp demo.
4. Muốn tạo lượt mới: **Cấu hình nâng cao** → chọn map/weather/frame/FOV → **Tạo thí nghiệm**. Xem thông báo GPU/RAM trước. Preset đã thử: Town01, 2 xe, 0 người. Cấu hình khác cần kiểm chứng.
5. Engineer có thể ghi đánh giá gắn với báo cáo. Phản hồi chưa tự train lại policy.

**PPO** là Proximal Policy Optimization, một thuật toán học tăng cường. Policy hiện chọn input LiDAR cho frame kế tiếp, không điều khiển xe hoặc tự thay model/camera/radar. Clip lịch cố định kiểm tra chuyển sensor không phải khả năng thích nghi của PPO.

FOV là **góc nhìn** camera: 60° hẹp, 90° cân bằng, 110° rộng. Đây chưa phải chỉnh điểm lấy nét. Model occupancy LiDAR hiện không dùng ảnh camera; ảnh mưa/sương mù chưa chứng minh độ bền của model LiDAR.

## Khi giao diện chưa có kết quả

| Trạng thái | Nghĩa là gì? | Làm gì? |
| --- | --- | --- |
| queued | Chờ worker xử lý | Kiểm tra worker và thông báo runtime; chọn lượt succeeded để xem trước. |
| running · capture | Đang thu frame | Theo dõi số frame và log; kết quả hoàn tất cần capture + inference + đánh giá. |
| succeeded | Đã hoàn tất | Chọn model, Play và Model/Reference để đối chiếu. |
| GPU chưa sẵn sàng | Preflight không nhận GPU | Kiểm tra nvidia-smi; không ép chạy hoặc hạ guard để né lỗi GPU. |
| Chưa đủ RAM | RAM khả dụng chưa đạt ngưỡng | Đóng bớt ứng dụng; guard hiện10GiB, không phải yêu cầu RAM tổng của máy. |
| Thiếu ảnh / dữ liệu | Artifact hoặc đường dẫn chưa đủ | Kiểm tra dataset/cache/export; không tạo kết quả giả hoặc mở ảnh thô để né bộ lọc riêng tư. |

Xem các bản ghi hoàn tất không cần GPU CARLA. Mở hướng dẫn sẽ tạm dừng playback, giữ frame để không bị đổi cảnh trong lúc đọc.

## Khởi động local trên máy phục hồi hiện tại

Trong hai terminal riêng:

```bash
cd /home/lam/WorkSpace/vinuni-buildphase/P-027-recovery-20261013
bash scripts/run_local_mvp.sh backend
```

```bash
cd /home/lam/WorkSpace/vinuni-buildphase/P-027-recovery-20261013
bash scripts/run_local_mvp.sh frontend
```

Mở `http://127.0.0.1:3111/lab`. Worker là tiến trình riêng, chỉ khởi động sau khi runtime GPU/RAM đã đủ để xử lý capture mới. Không bật hai worker/collector cạnh tranh. Launcher trên là cho runtime phục hồi ở máy này, không phải installer chung cho mọi máy.
