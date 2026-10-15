# Rà soát remote CARLA worker — 15/10/2026

## Kết luận

Code đã có đường chạy remote CARLA Occupancy LiDAR để đưa vào smoke test.
Production chưa sẵn sàng nhận yêu cầu agent/worker: API hiện vẫn playback-only.
Không coi test giao thức thành công là đã chạy CARLA + R2 + LLM thật đầu-cuối.

## Bằng chứng production tại thời điểm kiểm tra

- Render service `p027-deploy`: commit live `8f0a49a`.
- `/health`: HTTP 200, `env=production`.
- `/api/v1/evidence/capabilities`: HTTP 200, `execution_mode=local`,
  `interactive_enabled=false`, `playback_only=true`, `access_required=false`.
- Dashboard Environment đã có tên đủ 6 biến `REMOTE_STORAGE_ENDPOINT`,
  `REMOTE_STORAGE_REGION`, `REMOTE_STORAGE_BUCKET`, `REMOTE_STORAGE_ACCESS_KEY`,
  `REMOTE_STORAGE_SECRET_KEY`, `REMOTE_STORAGE_PREFIX`.
- Chỉ kiểm tra tên biến; không mở secret, chưa xác minh giá trị/quyền R2.
- Không có linked environment groups hoặc secret files được liệt kê.

## Còn thiếu cấu hình trên Render

| Nhóm | Biến / hành động |
| --- | --- |
| Queue | `REMOTE_DATABASE_URL`; có thể cùng giá trị PostgreSQL với `DATABASE_URL` |
| Migration | Chạy `python -m scripts.init_remote_worker` trên đúng remote DB trước khi bật remote |
| Chế độ | `EXPERIMENT_EXECUTION_MODE=remote` |
| Opt-in | `EXPERIMENT_API_ENABLED_IN_PRODUCTION=true` |
| Người vận hành | `EXPERIMENT_ACCESS_TOKEN` riêng, tối thiểu 32 ký tự |
| Worker | `REMOTE_WORKER_TOKENS` JSON map worker ID sang token riêng tối thiểu 32 ký tự |
| LLM | `LLM_PROVIDER`, key theo provider, `EXPERIMENT_AGENT_MODEL`, `EXPERIMENT_AGENT_ENABLED=true` |

Migration production chưa được xác minh. Có `DATABASE_URL` không tự cấu hình
`REMOTE_DATABASE_URL`. Nhóm LLM cần nếu dùng prompt; thủ công không cần LLM.
Không có nhóm biến trên trong danh sách Environment đầy đủ khi kiểm tra.
Đây là trạng thái tại thời điểm rà soát; kiểm tra lại sau mỗi lần lưu/redeploy.

LLM OpenRouter dùng `OPENROUTER_API_KEY`; OpenAI dùng `OPENAI_API_KEY`.
Không có biến `LLM_API_KEY` chung trong Settings hiện tại.

## Đã xử lý trong code

- Operator cookie/Bearer và token riêng từng worker; checkpoint hash phải khớp.
- Queue/study/review PostgreSQL, schema additive khởi tạo tường minh.
- Claim có khóa tránh nhận trùng; lease/heartbeat/progress; hủy và hết lease.
- Worker Ubuntu chạy trial riêng, quản lý CARLA local qua binary cấu hình.
- Upload URL ký có hạn, kích thước/hash/đường dẫn có giới hạn, retry hữu hạn.
- Backend xác minh artifact, tính lại metric từ prediction/reference trước publish.
- Study baseline/candidate, đối chiếu cấu hình, FE trạng thái và đọc artifact.
- Upload resume tường minh khi output local hoàn tất và lease vẫn còn hợp lệ.

## Kiểm tra đã chạy lại trong lần rà soát này

- Remote worker/API/storage client: 10 passed, 1 skipped.
- Sensor agent, CARLA runtime và public evidence: 25 passed.
- Test PostgreSQL opt-in được skip trong lượt này vì không cấp test DB URL.
- Không dùng API key thật, không phát sinh lượt gọi LLM thật, không mở CARLA GPU.
- S3 được kiểm tra bằng stub/mock, không xác nhận bucket production đã đọc/ghi được.

## Giới hạn hiện tại

- Remote v1 chỉ fresh CARLA Occupancy LiDAR, chưa camera/radar/Flow/PPO online.
- Một trial toàn hệ thống tại một thời điểm. Thêm worker chưa giúp chạy song song.
- Không có UI đăng ký/duyệt worker; quản trị cấp/thu hồi token trên backend.
- Mất lease không tự recapture; resume không phục hồi job đã expired/failed/cancelled.
- Chưa có tác vụ tự dọn scratch/object cũ. Cần quản trị quota/retention.
- Lưu CARLA remote lâu dài; không phải lịch sử replay tự xóa khi đóng tab.
- Chưa đo tiền/điện thực tế; IoU là occupancy proxy, weather RGB chưa là suy hao
  LiDAR vật lý được hiệu chuẩn. Worker được cấp token là máy tin cậy.

## Thứ tự để nghiệm thu

1. Thu hồi key R2 đã lộ trong hội thoại; tạo key mới và cập nhật trực tiếp Render.
2. Bổ sung queue URL, chạy migration, thêm token và nhóm LLM nếu dùng prompt.
3. Bật remote/interactive, redeploy. Kiểm tra capabilities đổi sang remote và interactive.
4. Setup Ubuntu theo [runbook](WORKER_UBUNTU_STEP_BY_STEP.vi.md), preflight rồi bật worker.
5. Trial Town01 2 frame: CARLA thật → checkpoint → R2 thật → FE xem artifact.
6. Study baseline/candidate, kiểm tra so sánh và phần giải thích bằng LLM thật.
7. Thử hủy/mất worker và mở lại kết quả đã completed.

Chưa thực hiện bước 1–7 thay người quản trị trong lần rà soát này. Không thay
cấu hình cloud, không dùng secret được đăng trong chat để thử truy cập.
