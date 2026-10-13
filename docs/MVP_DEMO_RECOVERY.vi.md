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

Ba profile thinning là phạm vi MVP phục hồi. Đã có pilot 12 profile LiDAR vật lý, nhưng training PPO hiện vẫn là ba action trên nuScenes; split native và MultiDiscrete chưa hoàn thành; không gọi ba profile này là triển khai đầy đủ kế hoạch.

## Đoạn nói thêm khi mở bot

“Ở đây nhóm đã đo 12 cấu hình LiDAR vật lý: 16, 32, 64 kênh với bốn mức điểm mỗi giây. Tất cả dùng cùng reference. Ví dụ giảm từ 600 nghìn xuống 300 nghìn điểm mỗi giây làm occupied IoU giảm từ 83 xuống 65 phần trăm; recall ô vật thể giảm từ 96 xuống 72 phần trăm. Vì vượt ngưỡng chất lượng đã đặt, hệ thống giữ cấu hình gốc và chỉ rõ evidence. Đây là kiểm chứng cấu hình; PPO đã train là phần nuScenes riêng, chưa nối vào CARLA online.”

## Demo clip dài và reference

Trong công cụ CARLA, chọn clip clear route17 seed73 (20 frame): bật Reference, chọn actor phía trước để xem footprint trên BEV và viền geometry trên camera. Bật Lặp capture để chạy liên tục. Clip fog route31 seed97 có 20 frame để review môi trường, không chứng minh độ bền LiDAR trong sương mù. Ở matrix 12 profile, chọn ứng viên rồi “Đối chiếu trên map” để xem đồng bộ với baseline.
