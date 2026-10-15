# Kết quả CARLA + model + LLM agent — 07/10/2026

Study: `cf2a9a32615149cd81371531e7844ac6`. Kết thúc thành công, exit code 0.

LLM thật: `gpt-4o-mini-2024-07-18`. Agent đã tạo study, gọi tools đọc/so sánh và sinh thuyết minh.
CARLA server/client 0.9.11; client Python 3.7.9; worker Python 3.13.15; model occupancy_lidar chạy CPU.
Town01, trời quang, 2 xe, 0 người đi bộ, seed 42, 2 frame mỗi cấu hình; LiDAR 32 kênh, tầm quét 100 m.

| Điểm/giây | Occupied IoU | Giảm IoU | Giảm dữ liệu LiDAR | Latency p50 (ms) |
|---:|---:|---:|---:|---:|
| 600,000 | 0.3321 | 0.0000 | 0.0% | 111.26 |
| 300,000 | 0.2958 | 0.0363 | 50.3% | 126.24 |
| 150,000 | 0.2312 | 0.1009 | 75.0% | 102.13 |

**Lựa chọn tạm thời: baseline 600.000 điểm/giây.** Hai profile giảm điểm đều vượt ngưỡng giảm IoU 0,02.
Cả ba trials succeeded và reference hash khớp nhau.

Đây là thử nghiệm nhỏ trên nhãn occupancy proxy, chưa phải benchmark detection hoặc khuyến nghị cảm biến ngoài thực tế. Latency chỉ có 2 frame/cấu hình; không suy ra chi phí điện hoặc tiền từ lượng dữ liệu.

Lượt đầu bị cắt phần trả lời LLM ở 700 token. Đã tăng lên 1800 và tiếp tục tổng hợp trên study đã lưu. Sau đó sửa UTF-8 cho terminal Windows; lần kết thúc dùng lại summary đã lưu, không capture hoặc gọi LLM lại.

Toàn bộ artifact: `D:\CARLA\runs\llm-agent-20261007-000631`.
Các thư mục theo job ID chứa capture PNG/NPZ/geometry, manifest, prediction và log client.

Các file báo cáo kèm theo: comparison.json, agent-summary.json, study-start.json.
agent-summary.json lưu thuyết minh gốc của LLM; số liệu/điều kiện lựa chọn được kiểm tra bằng báo cáo comparison.json.
