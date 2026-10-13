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

Sau bổ sung progress, 29 test experiment/session/evidence đã qua. Progress snapshot vượt total hoặc JSON thiếu/hỏng bị bỏ qua; job kết thúc không còn hiển thị capture progress. FOV API: 60/90/110 → HTTP 200; 75 → HTTP 422. CARLA sạch: binary + 14 library ELF hợp lệ, loader không báo thiếu library, native capture vẫn chưa chạy vì guard RAM.

## Native CARLA đã chạy — cập nhật 13/10/2026

Các nhận định “native chưa chạy” ở phần checkpoint phía trên mô tả thời điểm trước khi RAM/runtime được phục hồi; hiện đã có evidence sau đây.

| Case | Output thực tế | Artifact |
| --- | --- | --- |
| FOV 60/90/110 | Mỗi preset 2 frame; sensor FOV đúng, PNG 640×360 giải mã được | `native-fov-captures.json` |
| Native Reference | HTTP 200, 40.000 cells và valid mask; actor là metadata CARLA | `native-api-live-checks.json` |
| Prediction/camera cùng capture | HTTP 200; replay giữ camera/reference của parent | cùng artifact |
| Input alignment hai route mới | Object-cell recall 0% → 85,1%/88,1%; object IoU 16,9%/55,6% | `native-intensity-heldout-evaluation.json` |
| Mưa/sương mù | RGB có preview; cùng LiDAR/metric, không chứng minh weather robustness | `native-input-rain-diagnostic.json`, `native-input-fog-diagnostic.json` |
| Sensor 600k/300k/150k | Occupied IoU 83,2%/65,2%/42,9%; giữ baseline vì vượt drop bound | `native-sensor-study-evidence.json` |
| Pilot 12 cấu hình | `complete_pilot`, 12 profile thực, input/ref/confusion audit khớp; native_rl_admitted=false | `native-12-profile-audit.json` |

135 test hồi quy API/Active Sensing đã qua sau bổ sung study và audit. ESLint, TypeScript, production compile đã qua; lỗi đóng gói do BUILD_ID không có newline đã sửa và release được đóng gói thành công. Browser vẫn ở error page `data:` bị policy chặn, nên chưa tuyên bố visual QA cuối hoặc các thao tác UI mới đã được kiểm tra bằng trình duyệt.

### Bản phục vụ cuối

141 test API/Active Sensing/projection đã qua; ESLint và TypeScript đã qua, production build/release thành công. 10 HTTP check đều 200, gồm frontend proxy, PPO report, profile audit, camera/reference và prediction frame cuối của clip 20 frame: `final-live-api-checks.json`. Projection math có test hướng trục, FOV, world transform chung; API từ chối liên hệ camera/BEV sai pose/frame trong fixture. Raw ảnh native đầu clip đã được view_image xem, khung chiếu geometry khớp vùng actor phía trước. Đây không thay cho visual QA thao tác trên ứng dụng; browser hiện vẫn ở error page bị policy chặn.

Toàn bộ suite của repo phục hồi: **245 passed trong 15,62 s**. Các assets model/policy đã giải nén vào folder mới, xác minh hash và đọc được cả native pilot/PPO report: `portable-assets-check.json`. Source/data/model archive được kiểm CRC và Git bundle verify; không đổi dữ liệu đo hoặc review engineer.
