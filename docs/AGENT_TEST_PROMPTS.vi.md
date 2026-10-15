# Prompt kiểm thử AI Agent Occupancy

Chạy theo hướng dẫn [local](REPLAY_SENSOR_AGENT.vi.md). Bắt đầu 2 frames.
Mỗi lần lập kế hoạch dùng LLM thật nếu key/agent được bật; xem hình không gọi LLM.
Kiểm tra kế hoạch thực tế trước khi diễn giải số đo. Các ngưỡng là ngưỡng thử nghiệm.

## 1. Cả ba sensor, thông số rõ

> Ở scene-0103, 2 frames, ảnh gốc, chạy cả ba model occupancy. So sánh baseline với half: LiDAR/radar giữ 50% điểm, camera scale 0.5, JPEG 80; IoU giảm tối đa 0.02.

Mong đợi: baseline + half; ba checkpoint; điểm/ảnh giảm, hình đối chiếu cùng frame.
Không bắt buộc mọi model đều được đề xuất nếu không đạt ngưỡng.

## 2. Chỉ tối ưu LiDAR

> Chỉ tối ưu LiDAR ở scene-0103, 2 frames, chỉ chạy occupancy_lidar. Thử lidar_75 và lidar_50 giữ 75% và 50% điểm LiDAR. Khoảng cách 100 m, góc ngang 360 độ, không nhiễu. Giữ nguyên radar và camera. IoU giảm tối đa 0.02.

Mong đợi: chỉ checkpoint LiDAR, radar/camera giữ nguyên. Kiểm tra kế hoạch: backend
hiện chưa cưỡng chế đầy đủ phạm vi sensor từ văn bản, có thể LLM lập sai.

## 3. Lọc điểm radar

> Ở scene-0916, 2 frames, chỉ chạy occupancy_radar. So sánh baseline với radar_front: radar giữ 50% điểm trong khoảng cách 40 m, góc ngang 120 độ, không nhiễu. Giữ nguyên LiDAR/camera. IoU giảm tối đa 0.02, IoU tối thiểu 0.3.

Mong đợi: hình radar thưa/cắt vùng. Radar có thể không đạt IoU tối thiểu; báo chưa đủ
bằng chứng chọn là kết quả hợp lệ, không phải lỗi.

## 4. Mục tiêu để agent tự đề xuất

> Tìm cấu hình ít dữ liệu nhất cho cảnh đông đối tượng ở scene-0916, 2 frames, cả ba model occupancy. Đề xuất tối đa 3 ứng viên; IoU giảm không quá 0.02 và IoU tối thiểu 0.3.

Mong đợi: traffic crowded, phương án hữu hạn. Không hứa tự tối ưu nhiều vòng.

## 5. Điều kiện ảnh

> Scene-0103, mỗi điều kiện 2 frames: ảnh gốc, mưa và sương mù, seed 42. Mỗi điều kiện thử baseline và half: LiDAR/radar 50%, camera scale 0.5, JPEG 80. Cả ba model occupancy; IoU giảm tối đa 0.02.

Mong đợi: 6 trials. LiDAR/radar IoU có thể giống giữa các điều kiện vì chỉ ảnh đổi.

## 6. Ứng viên không đạt ngưỡng

> Scene-0103, 2 frames, cả ba model occupancy. Thử quarter giữ 25% điểm LiDAR/radar; camera scale 0.25, JPEG 40. IoU giảm tối đa 0.01, IoU tối thiểu 0.3, PSNR tối thiểu 35 dB.

Mong đợi: dùng baseline hoặc không chọn nếu ứng viên không đạt; không tự nới ngưỡng.

## 7. Từ chối scene và lịch sử phiên

> Thử cả ba sensor ở scene 40, 2 frames.

Mong đợi: scene-0040 không có, 422 trước LLM, không tạo job/tiêu token; kết quả cũ
ẩn, vẫn xem lại được từ lịch sử. Không nhầm scene 40 với 40 frames.
Refresh giữ lịch sử; Kết thúc phiên hoặc đóng tab dọn theo thời hạn trong runbook.

## 8. Tính ổn định

Chạy lại cùng prompt ở mục 1: có thể cùng spec/số đo do cùng dữ liệu/checkpoint/seed.
Metadata/UI báo kế hoạch trùng. Đổi tỷ lệ xuống 25% để kiểm tra cấu hình và payload
thay đổi; khác cấu hình không bắt buộc mọi metric đều khác.
