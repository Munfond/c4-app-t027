# Lời trình bày nhanh trên Lab

“Đây là Lab trực quan dữ liệu cảm biến và kết quả mô hình ADAS. Em chọn scene và frame; ảnh camera giúp nhìn bối cảnh, còn LiDAR và Radar hiển thị vị trí và chuyển động trong hệ tọa độ của xe. Các lớp cảm biến có thể bật hoặc tắt trên cùng một viewer.

Tiếp theo là kết quả occupancy, flow và Seg3D. Giao diện giữ rõ nguồn, mô hình và loại output. Seg3D reference không được gọi là dự đoán. Các frame trong bản này phần lớn là kết quả đã tính sẵn, giúp phát lại ổn định.

Ở bot cạnh workspace, em mở cấu hình camera hoặc xem thí nghiệm. Capture được phát đồng bộ camera và occupancy, có Play, Pause, tốc độ và thanh frame. Dấu ego cùng vòng khoảng cách giúp đọc vị trí; ô vật thể chưa cho phép xác định danh tính người hay xe.

Phần học tăng cường đã chạy PPO thật trên dữ liệu occupancy proxy đo từ nuScenes. Agent chọn một trong ba mức giữ điểm LiDAR: 100%, 50% hoặc 25%. Dữ liệu được chia theo scene và so với baseline trên 81 frame test.

Kết quả hiện tại agent giữ 100% điểm. Giảm điểm làm IoU giảm nhưng thời gian mạng chạy trên lưới cố định chỉ thay đổi ít. Vì vậy hệ thống báo chưa có cấu hình tốt hơn, kèm báo cáo và hash để đối chiếu. Engineer có thể đánh giá kết luận đó.

CARLA sạch đã tạo capture FOV và preview mưa/sương mù. Căn chỉnh intensity thử nghiệm cải thiện trên hai route Town01 mới, nhưng object IoU vẫn thấp ở một route; cần kiểm chứng rộng hơn. Bản hiện tại chưa chứng minh online RL hoặc khả năng an toàn ngoài thực tế.”

## Trình tự demo

1. `/lab`: chọn scene/frame, Camera và LiDAR/Radar; không thay đổi dữ liệu.
2. Bật lớp Seg3D và đọc đúng badge reference/prediction.
3. Mở bot → công cụ CARLA → chọn capture phục hồi → Play/Pause. Bật/tắt rút ngắn khoảng trống để giải thích timestamp.
4. Mở “Học tăng cường · PPO offline”, chỉ vào hàng 50% so với 100% và PPO.
5. Mở nguồn/split/giới hạn, tải report. Chỉ engineer thật mới ghi review.
6. Camera preset 60/90/110: chọn các capture smoke đã chạy; đọc FOV và giới hạn. Chọn capture căn chỉnh thử nghiệm để so Model/Reference, chỉ rõ đây chưa là native RL.

Ba profile thinning là phạm vi MVP phục hồi. Bộ 12–24 profile và MultiDiscrete của kế hoạch Active Sensing ban đầu chưa hoàn thành; không gọi ba profile này là triển khai đầy đủ kế hoạch.
