# Thử prompt tìm mức dữ liệu LiDAR thấp nhất

tìm mức  dữ liệu của lidar có thể chấp nhận được thấp nhất cho model đả bảo kết quả

Agent chọn Town01, 2 xe, 2 frame mỗi cấu hình, seed 42. Ngưỡng giảm IoU tối đa: 0.02.

| Điểm/giây | IoU | Giảm IoU | Dữ liệu byte/giây |
|---|---|---|---|
| 600000 | 0.3321 | 0.0000 | 4898720 |
| 300000 | 0.2958 | 0.0363 | 2432640 |
| 150000 | 0.2312 | 0.1009 | 1224480 |

Chọn baseline 600000 điểm/giây trong các mức đã thử. Hai mức giảm dữ liệu đều vượt ngưỡng giảm IoU. Chưa tìm kiếm các mức trung gian 300000–600000; chưa chứng minh đây là mức thấp nhất có thể.

Input/output: dataset-index.json. Metrics: comparison.json. Giải thích LLM: agent-summary.json.
