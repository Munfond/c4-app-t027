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

Ba profile thinning nuScenes là một thí nghiệm riêng. Native PPO tiếp theo đã train 12 action từ 48 capture độc lập, chia route 2/1/1. Cả hai đều là replay offline; CARLA online switching và MultiDiscrete chưa hoàn thành.

## Đoạn nói thêm khi mở bot

“Ở đây nhóm đã đo 12 cấu hình LiDAR vật lý: 16, 32, 64 kênh với bốn mức điểm mỗi giây. Tất cả dùng cùng reference. Ví dụ giảm từ 600 nghìn xuống 300 nghìn điểm mỗi giây làm occupied IoU giảm từ 83 xuống 65 phần trăm; recall ô vật thể giảm từ 96 xuống 72 phần trăm. Vì vượt ngưỡng chất lượng đã đặt, hệ thống giữ cấu hình gốc và chỉ rõ evidence. Đây là kiểm chứng cấu hình; PPO đã train là phần nuScenes riêng, chưa nối vào CARLA online.”

## Demo clip dài và reference

Trong công cụ CARLA, chọn clip clear route17 seed73 (20 frame): bật Reference, chọn actor phía trước để xem footprint trên BEV và viền geometry trên camera. Bật Lặp capture để chạy liên tục. Clip fog route31 seed97 có 20 frame để review môi trường, không chứng minh độ bền LiDAR trong sương mù. Ở matrix 12 profile, chọn ứng viên rồi “Đối chiếu trên map” để xem đồng bộ với baseline.

## Native RL mới — lời nói khoảng 30 giây

“Nhóm đã thu 12 cấu hình LiDAR thật trong CARLA, tổng 48 lượt và 960 outcome. Dữ liệu chia route train, validation và test riêng, kiểm tra reference khớp trước khi train. Agent quan sát frame hiện tại và chọn cấu hình cho frame kế tiếp, không được nhìn đáp án của cấu hình chưa chọn.

PPO chạy 8.192 bước; checkpoint chọn bằng validation ở bước 4.096. Trên route test, agent giữ 32 kênh và 600 nghìn điểm mỗi giây ở cả 19 quyết định. Occupied IoU là 81,4%, nhưng Object IoU chỉ 6%; nhóm báo đúng giới hạn đó. Không có cấu hình tốt hơn thì agent giữ mặc định và cung cấp evidence, thay vì đổi sensor cho có vẻ thông minh. Đây chưa là sensor-control online.”

Mở bot → “Học tăng cường · 12 cấu hình LiDAR CARLA” → baseline/PPO → bảng đủ 12 cấu hình → nguồn/split → tải report. Không ghi engineer review giả.

Từ mục native PPO, bấm “Xem capture mặc định của test · 20frame” để mở chính capture route72 ở workspace cạnh bot. Bật Play/Reference, xem camera và occupancy theo cùng frame; đây là đọc kết quả đã ghi, không tạo job CARLA mới. Policy giữ mặc định ở19/19 quyết định, nên clip này minh họa baseline đã chấm, không giả lập agent đang đổi sensor.
