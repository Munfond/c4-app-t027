# Chạy Experiments: checkpoint hiện có, CARLA và agent

Ngày: 05/10/2026.

## Đã triển khai

- API /api/v1/experiments: registry, validate, tạo/list/poll/cancel job, draft bằng agent, prediction và ảnh simulator.
- SQLite queue tại EXPERIMENT_ROOT/jobs.sqlite3, owner/heartbeat, idempotency key, giới hạn pending jobs; worker chạy riêng.
- Registry bảy checkpoint occupancy/flow. SHA256 phải khớp data/lab/models/CHECKPOINTS.sha256 trước khi nạp.
- Inference thật bằng PyTorch, evaluator occupancy/flow, prediction cache, preview BEV và report ở /experiments.
- LangGraph planner gọi LLM một lần để đề xuất spec. Lập cấu hình không tạo job; nút Tạo thí nghiệm/API POST là thao tác thực thi riêng.
- Runner CARLA synchronous: RGB/LiDAR/semantic LiDAR, weather, actor population, frame-ID synchronization, GT proxy và cleanup.

CARLA client/server chưa có trên máy tại thời điểm triển khai; code simulator chưa được nghiệm thu với server thật. Không gọi bản này là đã hoàn thành toàn bộ kế hoạch CARLA.

## Checkpoint và giới hạn

| Model ID | Task | Nguồn chạy được |
|---|---|---|
| occupancy_lidar | BEV occupancy | nuScenes và adapter CARLA experimental |
| occupancy_radar | BEV occupancy | nuScenes |
| occupancy_lidar_radar | BEV occupancy | nuScenes |
| flow_t1, flow_t2, flow_t4, flow_t4_nowarp | occupancy + flow | nuScenes |

Các checkpoint này không tạo hộp detection và không dùng camera. Metric là occupied IoU/class IoU/object-cell recall/flow EPE, không phải mAP/NDS/pedestrian detection recall.

CARLA radar không cung cấp trực tiếp input contract của checkpoint (RCS và compensated planar speed). API từ chối model radar/flow trên CARLA thay vì thêm radar giả. CARLA adapter chỉ cấp LiDAR cho occupancy_lidar; RGB phục vụ kiểm tra bằng mắt. Đổi weather RGB không chứng minh robustness thời tiết của model này. Cần checkpoint camera hoặc corruption LiDAR có kiểm chứng để nghiên cứu đó.

CARLA labels: static-height proxy và box footprint của actors được semantic LiDAR thấy; chấm điểm chỉ trên observed cells. Chưa phải occupancy ground truth đầy đủ. LiDAR intensity 0..1 được scale sang 0..255 là xấp xỉ chưa hiệu chuẩn với nuScenes. Ground reference gần đúng bằng đáy bounding box ego. Cần QA geometry/intensity trước khi kết luận.

Runner dùng autopilot từ spawn index, chưa có named highway route validation. Actor counts đo ở toàn world; report ghi visible_actor_counts để kiểm tra mật độ gần ego. Chưa có semantic 3D segmentation, complete free-space, fixed actor trajectory across weather hoặc đánh giá điều khiển vòng kín.

## Chạy local bằng checkpoint thật

Web không import torch/CARLA khi startup. Worker cần full repository vì sử dụng kiến trúc/nuScenes adapter hiện có trong legacy/streamlit_lab/tools/local.

Nếu tạo môi trường worker mới:

```powershell
py -m venv .venv-experiments
.\.venv-experiments\Scripts\python.exe -m pip install -r requirements-experiments.txt
```

Môi trường .venv-lab hiện tại đã có PyTorch CPU và chạy được các checkpoint. Không cần cài lại requirements-inference.txt của anonymizer; bộ đó có dependency riêng.

Terminal backend:

```powershell
.\.venv-lab\Scripts\python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Terminal frontend, trong frontend/:

```powershell
npm run dev
```

Terminal worker, tại repo root:

```powershell
.\.venv-lab\Scripts\python.exe -m scripts.experiment_worker
```

Mở http://localhost:3000/experiments. Chọn nuScenes, scene-0103 hoặc scene-0916, 2 frame và các model. Tạo job; worker chạy rồi UI poll report. Raw nuScenes gồm sweeps/metadata phải có tại NUSC_ROOT.

Smoke test bằng CLI, không gọi LLM:

```powershell
.\.venv-lab\Scripts\python.exe -m scripts.smoke_experiments --frames 2
```

Lệnh tạo experiment trong queue rồi chạy một job; chỉ dùng khi queue rỗng, nếu có job trước thì dùng worker thường. Kết quả lưu trên đĩa và hiện trong UI. Hai frame là smoke test, không phải benchmark hay kết luận chọn model ngoài đường thật.

## Chạy CARLA

1. Chuẩn bị CARLA server và map phù hợp. Khóa server/client version sau smoke test, cài Python wheel/client đúng Python và nền tảng. Không tự cài một phiên bản CARLA bất kỳ vào môi trường inference.
2. Dùng server riêng cho Lab; runner có thể load map, đổi world settings và Traffic Manager. Một world chỉ có một tick owner. Không dùng chung world với một app khác.
3. Đặt CARLA_HOST/CARLA_PORT/CARLA_TM_PORT trong .env của backend/worker. Mặc định 127.0.0.1:2000 và TM 8001. Đảm bảo RPC endpoint chỉ trong mạng tin cậy.
4. Trong UI chọn CARLA, occupancy_lidar, map cài sẵn, weather, actor counts, seed và vài frame. Worker sẽ capture rồi inference.
5. Kiểm tra camera, capture/manifest.json, frame JSON boxes/ego matrix và NPZ point cloud/labels. Nghiệm thu overlay và sensor/calibration trước khi tăng số frame/kịch bản.

Chưa có server hoặc thiếu client → job failed rõ ràng, không tạo kết quả mô phỏng giả. Nếu spawn thiếu số actor yêu cầu, job cũng failed. Cancel được xử lý giữa tick/frame/batch; network/driver block có thể chờ timeout trước cleanup.

## Dùng lại capture và prediction

CARLA capture mới được tạo cho mỗi request không có capture_id. Để đánh giá lại đúng dữ liệu, POST spec có capture_id là ID experiment CARLA đã capture thành công, scenario phải giống bản gốc. Frame paths được allowlist, không truyền đường dẫn tùy ý. Model phải vẫn tương thích nguồn.

Prediction cache dùng input/GT/pose hash, checkpoint hash, pipeline version, torch version và device. Latency chỉ đo trên frame inference mới, sau warmup. Cache hit không báo timing mới; nếu tất cả cache hit, latency=null, model không đủ bằng chứng để đạt ràng buộc latency trong lượt đó. Cache không tự xóa; quản trị retention riêng.

Worker lease hết hạn được đánh dấu failed; không tự resume capture đang dở. Kiểm tra/dọn simulator trước khi tạo job mới. Store chỉ serialize worker dùng cùng EXPERIMENT_ROOT; nhiều store không được điều khiển chung CARLA world.

## Agent tiết kiệm chi phí

Mặc định EXPERIMENT_AGENT_ENABLED=false, không phát API request ngay cả khi .env đã có key. Để dùng planner:

```dotenv
OPENAI_API_KEY=<đặt riêng phía server>
EXPERIMENT_AGENT_ENABLED=true
EXPERIMENT_AGENT_MODEL=gpt-4o-mini
```

Restart backend sau đổi .env. Planner có một tool call/request, tối đa 700 output tokens, không gửi ảnh/point cloud, không polling bằng LLM và không tự retry provider. Bảng metric và ranking do Python tính, đọc UI không phát LLM request. Usage tokens được API trả về. Chưa chạy eval chất lượng với provider thật, nên lựa chọn model là baseline để đo, không bảo đảm đáp ứng mọi prompt.

GPT-4o mini giá text công bố tại 05/10/2026: $0.15 input và $0.60 output mỗi triệu tokens. Ví dụ 2,000 input + 500 output tokens khoảng $0.0006/request, chưa tính khác biệt usage thực tế. Nếu chất lượng lập spec không đạt bộ eval tiếng Việt, thử GPT-4.1 mini theo cấu hình, không tự fallback làm tăng chi phí.

Nguồn: https://developers.openai.com/api/docs/models/gpt-4o-mini ; https://developers.openai.com/api/docs/models/gpt-4.1-mini

## Production và công việc tiếp theo

Experiment API mặc định đóng khi APP_ENV=production. Chỉ bật EXPERIMENT_API_ENABLED_IN_PRODUCTION=true sau khi cấu hình gateway authentication, storage ghi được, quota và worker riêng. Mount EXPERIMENT_ROOT read-write, dữ liệu nuScenes/checkpoint có thể read-only. Docker web hiện tại không chứa môi trường simulator/inference/full legacy; chạy worker từ host/full checkout hoặc xây image worker riêng.

Công việc tiếp theo để đạt toàn bộ plan: QA CARLA thật, calibrated radar adapter hoặc checkpoint phù hợp, named routes/controlled trajectories, visibility/density protocol đầy đủ, capture reuse UI, ma trận nhiều seed/route, held-out validation/test và metric trên dữ liệu thật riêng.
