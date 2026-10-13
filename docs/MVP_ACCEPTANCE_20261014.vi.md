# Nghiệm thu MVP local — 14/10/2026

Đây là MVP nghiên cứu để trực quan và kiểm chứng, không phải hệ thống điều khiển xe đã được chứng nhận. Luồng demo: Lab→Cảm biến→Kết quả mô hình→Compare→Benchmarks→botCARLA→đối chiếuPPO20→Reference/trace.

## Output kiểm tra thật

| Test manual | Output thực tế | Kết quả |
| --- | --- | --- |
| Khởi động backend/frontend | /health200, /lab200;14JS/CSS tải được |Pass|
| nuScenes LiDAR/Radar Play/Pause | Frame01→23→30/40; số điểm đổi, mousePause dừng được |Pass|
| Camera360 |6/6ảnh processed1600×900 decode được trênframe3e8750f3|Pass|
| Detection3D |6.763điểmLiDAR,18vật cản; ghi rõ hình đại diện theo box|Pass|
| Seg3D |SalsaNext experimentaltransfer prediction, lớp road/car/building có điểm; lỗi nhãnFlow đã sửa|Pass, nhãn đã kiểm tra browser|
| Guide |3mục, Escape/focus;390×844mobile và1280×900desktop vừa viewport |Pass|
| Compare | Cùng frame3e8750f3: BEVFusion9box, Fusion18; đổi B sang PointPillars6box |Pass|
| Benchmarks |81frame mini_val; Detection, Occupancy, Flow, Risk và cảnh báo hiện đủ |Pass|
| Capture pair20 | Đối chứng/PPO20/20,61.322ô; referenceSHA khớp; occupied78,93%,object30,60% cảhai |Pass|
| PPO20 Play | Tự tới20/20 ở9,5s; camera ghi cùngframe20, kết thúc không ra quyết định tiếp |Pass|
| Reference actor | #1986,1m phía trước/0,1m trái,5×2×1,5m; overlay camera là phép chiếu tham chiếu |Pass|
| Artifact API |40bộcamera/prediction/reference; ảnh640×360 decode, mỗi grid40.000ô |Pass|
| Town03 capture mới |CrashnativeSignal11 khi loadmap,0frame; thửPSOsync vẫn lỗi, giữoriginalvàretry |Fail, chưa nghiệm thu|

EvidenceJSON: `eval/ux-help-2026-10-14/after-reboot-checks.json`, `eval/native-online-2026-10-14/paired20-comparison.json`, `paired20-http-results.json`. Các test API/seal/lifecycle và TS/lint/build đã chạy riêng; bảng trên không thay thế benchmarkFPS.

## Dùng ngay

Xem `HUONG_DAN_SU_DUNG.vi.md` để khởi động backend/frontend. Lab local: http://127.0.0.1:3111/lab. Bot→CARLA→PPOtrongCARLA→XemPPO20frame là bản ghi đã kiểm định, không cần mở simulator hoặc LLM. Các capture Town01 đã nghiệm thu dùng cho demo; không tự đổi map của yêu cầu bị lỗi.

## Giới hạn còn lại

- PPO giữ baseline trong testoffline và lượt inference20frame; chưa tìm được cấu hình tốt hơn được chứng minh. Không tune theo test đã xem.
- Agent chọn một trong12inputLiDAR cho frame tiếp theo; không điều khiển xe.12sensor vẫn chạy, không có bằng chứng tiết kiệm điện.
- CameraFOV60/90/110 chỉnh góc nhìn, không chỉnh điểm lấy nét. Camera chưa vào occupancyLiDAR.
- Hội thoại LLM cần cấu hình API; hiện chưa nghiệm thu hội thoại end-to-end. Panel evidence, preset và preview dùng được không cần LLM.
- Mưa/sương mù preview RGB chưa là suy giảm LiDAR/radar vật lý. ROS2, MultiDiscrete, radaradapter và weatherrobustness chưa hoàn tất.
- Seg3D tham chiếu không phải prediction; Risk chưa hiệu chuẩn; checkpoint official có thể đã thấy mini_val. Không khẳng định an toàn ngoài thực tế.
- Town03 hiện lỗi Vulkan pipeline khi loadmap trên runtime này; rootcause chưa xác định. Workaround asyncPSO thử rồi bỏ vì không hiệu quả.
- Đây là nghiệm thu local, chưa kiểm tra deploy domain mới của team trong lượt này. Source mới lưu local, chưa push/merge.

Thông báo phục hồi sau lỗi đã compile/TS/lint pass; chưa thao tác browser nút “Xem bản ghi đã hoàn tất” trong lượt này vì usage còn3%. Đây là kiểm tra còn chờ, không ghi pass giả.
