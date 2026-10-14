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
- Hội thoại LLM cần cấu hình API; luồng đề xuất/tạo study/tóm tắt số đo đã qua OpenRouter thật; xem phần kiểm tra cuối bên dưới. Panel evidence, preset và preview dùng được không cần LLM.
- Mưa/sương mù preview RGB chưa là suy giảm LiDAR/radar vật lý. ROS2, MultiDiscrete, radaradapter và weatherrobustness chưa hoàn tất.
- Seg3D tham chiếu không phải prediction; Risk chưa hiệu chuẩn; checkpoint official có thể đã thấy mini_val. Không khẳng định an toàn ngoài thực tế.
- Town03 hiện lỗi Vulkan pipeline khi loadmap trên runtime này; rootcause chưa xác định. Workaround asyncPSO thử rồi bỏ vì không hiệu quả.
- Đây là nghiệm thu local, chưa kiểm tra deploy domain mới của team trong lượt này. Source đã push qua PR #22; trạng thái PR/merge phải đối chiếu GitHub thực tế.

Thông báo phục hồi sau lỗi đã kiểm tra browser: từ retryTown03failed22e0db05, nút “Xem bản ghi đã hoàn tất” chọn captureTown01 5e811b1f succeeded20frame, camera/occupancy hiện lại. Bảng hiện occupied74,2%,object14,4%,object-cellrecall87,9%; đây là capture khác, không phải cặpPPO20.

## OpenRouter và kiểm tra bổ sung

Kết nối cơ bản tới OpenRouter đã trả modelopenai/gpt-4o-mini và câu “Kết nối OpenRouter đã thành công”,34token. Key nằm trong .envignored, không trong report. Provider routing có test riêng ngăn gửi nhầm key. 284 test và Ruff đã qua trước bổ sung gói cloud/API chỉ đọc; bộ cuối gồm **288 test passed trong 46,25 giây**, Ruff/TypeScript/ESLint và production build đã qua. Các test gọi model được mock; không gọi chúng là liveLLMtool evidence. Người dùng đã xác nhận egress; live plan/study/summary đã kiểm tra, xem kết quả cuối bên dưới.

Đã sửa lỗi RAM9,999GiB bị hiển thị thành10GiB; UI mới hiển thị9,99, giữ nguyên guard10GiB. Tên PointPillars không còn gán cho export chỉ xác minh LiDARpretrained; fusion được ghi rõ hậu xử lý ở mức vật thể.

Toolcalling thật bằng dữ liệu tổng hợp công khai đã qua: add_numbers(2,3) trả5,94token; không gửi metadata dự án. Evidence: `eval/openrouter-mvp-2026-10-14/synthetic-tool.json`. Không dùng bài này thay cho nghiệm thu liveagent của dự án.


## Kiểm chứng thủ công mới và gói cloud

Study `f5961716704a405391c5cf2fc8d10bd2` đã chạy đủ ba capture Town01, clear, seed 42, FOV 90°, mỗi capture 4 frame. Không gọi LLM. Reference SHA bằng nhau cho cả ba lượt; occupied IoU lần lượt **83,18% / 65,17% / 42,90%** cho **600k / 300k / 150k**. 300k vượt mức giảm IoU cho phép; 150k còn dưới ngưỡng occupied và object-cell recall. Evaluator giữ baseline. Browser đã hiện đúng kết luận, số đo và nguồn; preview baseline/300k mở cùng frame cạnh bot. Evidence: `eval/openrouter-mvp-2026-10-14/manual-study.json`.

Gói perception cloud đã bổ sung Seg3D: 324 artifact / 81 frame, API đọc đủ bốn task không cần raw dataset; 4 test bundle qua. Gói native mới giải nén sạch có 226 file; 12 HTTP check trên frame đầu/cuối của hai capture decode được PNG 640×360 và lưới 40.000 ô. Báo cáo native PPO kiểm tra seal thành công mà không import Torch/CARLA/SB3. Production vẫn trả 503 khi POST plan; không gọi LLM. Evidence: `eval/cloud-native-2026-10-14/restore-check.json`. Đây là kiểm chứng gói/runtime local, chưa xác nhận Render đã deploy source mới.


Production chỉ đọc đã kiểm tra **browser thực tế**: bot không có form gọi LLM/tạo capture; mở PPO 20 frame, Play tới 20/20 (9,5 giây sim-time), chuyển Reference, ảnh camera frame 20 decode thành công. Desktop 1280px và mobile 390px không có overflow ngang. Evidence/screenshot: `eval/cloud-native-2026-10-14/browser-check.json`. Backend local được trả về development sau QA; không biến kết quả này thành xác nhận deploy Render.


## OpenRouter live E2E sau xác nhận người dùng

Đã gọi thật qua API backend local: plan HTTP200, tool tạo study HTTP201, đọc số đo và so sánh bằng `read_sensor_study` / `compare_sensor_configs`, summary HTTP200. Plan chỉ đề xuất (`executed=false`), đúng Town01/clear/2frame/seed42/FOV90/occupancy_lidar. Study smoke bị hủy ngay; không chạy CARLA/training hay tạo số đo giả. Summary đọc study đã hoàn tất `f5961716…`, giữ baseline theo occupied IoU83,18% so với65,17%/42,90%; không tuyên bố giảm điện/chi phí hoặc tối ưu toàn cục.

Phát hiện model nhân một môi trường thành hai scenario chỉ khác mật độ LiDAR. Đã thêm guard từ chối trùng môi trường trước khi tạo job và đúng một vòng sửa đề xuất, không retry vô hạn. Kiểm thử live sau sửa trả đúng một scenario baseline600k và một profile300k; study đã hủy. Đây là kiểm chứng lập kế hoạch và đọc evidence thật, không phải chứng minh LLM điều khiển simulator hoặc cải thiện PPO. Evidence: `eval/openrouter-mvp-2026-10-14/live-project-e2e.json`. Không gửi raw ảnh/point cloud/trọng số hoặc credential trong payload dự án.

Bộ kiểm tra cuối sau sửa agent/lịch sử: **294 test passed trong39,91 giây**, Ruff `src tests` qua. Browser bot CARLA đọc được lịch sử cũ, hiện summary OpenRouter với đúng số đo và giữ baseline. Study lịch sử trùng môi trường vẫn đọc được để audit, nhưng không được clone thành lệnh mới. Screenshot: `eval/openrouter-mvp-2026-10-14/live-agent-browser.png`.
