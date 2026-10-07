# Bot cạnh workspace và evidence của cấu hình

Ngày kiểm tra: 08/10/2026. Đây là agent lập thí nghiệm/đọc báo cáo; chưa phải RL
điều chỉnh sensor trong vòng kín. Lộ trình Discrete 12–24 profile → offline BC/PPO
→ online evaluation → MultiDiscrete vẫn giữ trong ACTIVE_SENSING.vi.md.

## Luồng người dùng

1. Mở Lab, CARLA Lab hoặc Experiments. Bấm bot ở góc phải để mở panel cạnh workspace.
   Không còn CARLA Agent/Replay Agent riêng trong navigation. URL `/agent` cũ chuyển về CARLA Lab.
2. Chọn rõ **CARLA** hoặc **nuScenes replay**. Hai nguồn có capability khác nhau;
   không coi replay là mô phỏng CARLA. Chuyển nguồn không chuyển một study sang nguồn khác.
3. Gửi yêu cầu để tạo lượt đo. LLM cần được bật/API key ở backend; khi chưa có key,
   form CARLA thủ công vẫn dùng được, và panel vẫn đọc evidence đã có.
   “Chỉ lập cấu hình” không chạy thí nghiệm; cấu hình điền vào form CARLA để người dùng kiểm tra.
4. Chọn study trong lịch sử. Worker thực thi tuần tự, độc lập việc thu gọn panel.
   Đọc evidence không gọi LLM; yêu cầu diễn giải LLM là thao tác riêng có dùng token.
5. Mở từng ứng viên để xem **IoU, mức giảm IoU, payload, lý do loại, số frame,
   vật trong ROI, config thực chạy, run ID, reference SHA và checkpoint SHA**.
6. Bấm “Đối chiếu trên map” để xem baseline và ứng viên cùng frame cạnh panel.
   Đây là occupancy 2D; không gắn nhãn Seg3D. Quay lại workspace giữ form/lịch sử cũ.
7. Engineer ghi verdict và lý do. Tải evidence + review JSON để bàn giao hoặc review tiếp.

Desktop rộng bố trí map/panel cạnh nhau. Tablet/mobile dùng panel thu gọn để giữ diện tích
workspace. Có nút đóng và Escape trả focus về launcher. Chưa hoàn tất kiểm tra render trực quan:
công cụ browser từ chối URL local do chính sách truy cập; lint/build không thay thế visual QA.

## Điều kiện kết luận

Evaluator bằng Python quyết định, LLM chỉ diễn giải:

- `improved`: ứng viên giảm payload, đạt ngưỡng IoU tối thiểu, không vượt mức giảm
  cho phép và có tham chiếu khớp. Không suy diễn bytes thành GPU/điện/chi phí tiền.
- `no_improvement`: không tìm được phương án giảm dữ liệu tốt hơn trong **tập đã thử**
  theo các ngưỡng đã đặt. Không nói baseline kém hoặc đã tối ưu toàn cục.
- `inconclusive`: thiếu số đo, lỗi/hủy, tham chiếu không khớp hoặc không cấu hình đạt ngưỡng.
  Không coi thiếu dữ liệu là bằng chứng rằng mọi phương án đều không cải thiện được.

Replay so từng model với baseline tương ứng; camera vẫn được chọn riêng trong báo cáo
comparison, theo fidelity/consistency, không gọi đó là GT detection accuracy.
CARLA byte rate là **ước tính payload LiDAR từ các tick đã lấy mẫu**; không phải lưu lượng
network đầy đủ. p95 model chỉ có khi chạy inference mới, không gán timing cho cache hit.
Reference hash khớp là điều kiện so sánh trong pipeline, không chứng nhận GT đúng hay sim-to-real.

## Review và archive

- `GET /api/v1/experiments/sensor-agent/{id}/evidence`
- `GET/POST /api/v1/experiments/sensor-agent/{id}/reviews`
- Review gửi `evidence_sha256`, reviewer tự khai báo, verdict `accept/reject/needs_evidence`, notes.
- Hash không khớp evidence hiện tại → HTTP 409; study chưa hoàn tất chưa được review.
- Review append-only; lưu cả snapshot evidence tại
  `<EXPERIMENT_ROOT>/engineer-feedback.sqlite3`, độc lập cleanup capture của phiên replay.
- Truy cập API review vẫn cần truy cập study gốc. Replay session hết hạn thì tải evidence/review
  trước khi đóng; engineer có archive trên backend để phân tích sau.
- Review chưa được xác minh danh tính và **không tự thay metric, trọng số, shield hoặc policy**.
  Bước cải thiện sau phải review feedback, sửa giả thuyết/cấu hình, chạy lại trên dữ liệu phù hợp
  và đối chiếu held-out test; không lấy feedback làm ground truth tự động.
- Các route experiment vẫn opt-in khi production; dùng access control có sẵn khi deploy.

## Lượt đo thật ngày 08/10/2026

Study `64ce880a9abd4b66a3b0f1c5c7b766cc`: Town01, clear, seed 42, hai xe nền,
hai frame mỗi cấu hình, checkpoint occupancy_lidar, CPU. Không gọi LLM.
Ba lượt đều thành công và reference SHA khớp. Không có actor trong ROI ở hai frame này.

| Cấu hình | Occupied IoU | Payload LiDAR ước tính/s | Giảm dữ liệu | Kết luận |
|---|---:|---:|---:|---|
| baseline 600k điểm/s | 36,37% | 4.906.720 bytes | 0% | Giữ baseline |
| 300k điểm/s | 32,35% | 2.453.920 bytes | 49,99% | Giảm IoU 4,02 điểm %, vượt giới hạn 2 |
| 150k điểm/s | 25,74% | 1.224.160 bytes | 75,05% | Dưới IoU tối thiểu 30%, giảm IoU quá mức |

**Kết quả: `no_improvement`.** Không phải baseline tốt trên đường thật: nhãn static là
height proxy, chỉ hai frame, không có vật động trong ROI. Chưa dùng study này train RL.

Evidence và response thực tế ở [eval/agent-evidence-2026-10-08](../eval/agent-evidence-2026-10-08/):
evidence.json, comparison.json, run-baseline/300k/150k.json, api-checks.json.
Các kiểm tra HTTP xác nhận study/evidence/reviews 200, stale review 409, study không tồn tại 404,
và sáu ảnh camera cùng frame 200. Đây là kiểm tra API/CLI thật, không gán thành manual browser test.
153 software tests passed; lint/build frontend và Ruff passed. Provider được mock trong test LLM.
