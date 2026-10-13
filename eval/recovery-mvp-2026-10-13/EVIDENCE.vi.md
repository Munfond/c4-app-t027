# Evidence phục hồi MVP (13/10/2026)

Các kiểm tra HTTP dưới đây được chạy trên backend/frontend local, không thay cho visual QA. Bản rendered UI cuối chưa được xem vì công cụ browser bị chính sách chặn. Các review trong unit test là fixture trong thư mục tạm; không ghi vào lịch sử engineer thật.

| Test case | Thao tác đã thực hiện | Output thực tế | File evidence |
| --- | --- | --- | --- |
| Backend hoạt động | GET `/health` | HTTP 200, `status=ok` | `http-final-checks.json` |
| Trang/asset production | GET `/lab`, `/compare`, `/benchmarks` và JS/CSS | HTTP 200; không thiếu chunk trong các request đã kiểm tra | `http-final-checks.json` |
| Camera được xử lý | GET CAM_FRONT/CAM_BACK tại frame đầu/cuối hai scene, giải mã JPEG | 8 request HTTP 200; ảnh cache phục hồi, không trả raw fallback | `sensor-final-checks.json` |
| LiDAR environment | GET environment tại cùng bốn frame | 4 request HTTP 200 với tọa độ ego và points | `sensor-final-checks.json` |
| Perception | GET Radar/Seg3D/occupancy/flow ở bốn frame | 16 request HTTP 200 sau khôi phục cache | `perception-final-checks.json` |
| PPO thực tế | Load selected policy, chạy deterministic trên 81 frame test | 81 quyết định giữ 100%; p95 decision CPU khoảng 0,203 ms | `policy-decision-timing.json` |
| Toàn vẹn evidence | Thay report/policy trong fixture, gọi service/API | Từ chối checksum sai; HTTP 503; review sai SHA bị HTTP 409 | `tests/active_sensing/test_recovery_evidence.py` |
| Chặn OOM trước launch | Fixture MemAvailable 9/11 GiB với ngưỡng 10 | 9 GiB bị từ chối trước launch; 11 GiB được chấp nhận | cùng file unit test |

Regression tổng: 105 passed trước bổ sung memory guard; 8 test evidence/guard đã qua sau bổ sung. ESLint các component sửa và production build đã qua. Không tuyên bố native CARLA FOV, online RL hoặc thời tiết đã được kiểm định.

Cache lịch sử: 486 ảnh JPEG, 81 artifact mỗi task Radar/Seg3D/occupancy/flow. Đã kiểm tra CRC, SHA, ảnh giải mã hoặc schema/coordinate/identity. Metadata/model/kind từ artifact giữ nguyên; Seg3D ground truth phải được trình bày là reference, không đổi nhãn thành prediction.
