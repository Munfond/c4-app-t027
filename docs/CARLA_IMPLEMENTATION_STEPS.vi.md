# Các bước triển khai CARLA + AI agent cho P-027

Ngày: 05/10/2026. Đây là kế hoạch thực hiện cho hai người; chưa triển khai code.

## Phạm vi đã thống nhất

Luồng: yêu cầu tiếng Việt → ScenarioSpec/ExperimentSpec → CARLA capture hoặc dùng capture đã có → adapter → inference các checkpoint → evaluator → agent giải thích → viewer.

Người 1: CARLA, cảm biến/GT, adapter và inference. Người 2: schema/API/DB/job orchestration, evaluator, agent và frontend. Cả hai chốt metric, GT policy và review giao diện dữ liệu chung.

MVP dùng hai checkpoint detection: LiDAR-only và Camera+LiDAR; hai nhóm route đô thị đông người/cao tốc ít người; ba điều kiện clear/rain/fog. Đây là sáu kịch bản và 12 lượt đánh giá mỗi bộ route/seed. Số lượt này kiểm tra pipeline, chưa đủ kết luận tổng quát.

Hiện workspace có tài liệu/config hai checkpoint detection nhưng thiếu our_lidar.pth và our_bevfusion.pth. Bảy checkpoint occupancy/flow đang có không thay thế hai checkpoint detection. File implementation plan cũ không hiện diện trong workspace tại lần kiểm tra này; tài liệu này giữ phạm vi CARLA bắt buộc đã thống nhất trong cuộc trò chuyện.

## Bước 1 — Chốt điều kiện đầu vào và tiêu chí

Phụ trách: cả hai. Ước lượng: 1–2 ngày.

- Chốt tên checkpoint, nơi lấy artifact, máy GPU, target hardware và nơi lưu capture.
- Chốt input contract từng model: camera count/order, resolution/FOV, intrinsics/extrinsics, LiDAR features, sweeps/history, class mapping và preprocessing.
- Chốt hai map/route có geometry phù hợp, thời lượng capture, timestep/cadence, actor counts và weather parameters. Không gọi tuyến đô thị là cao tốc nếu geometry không phù hợp.
- Chốt metric ưu tiên, operating point, giới hạn latency/memory và cách trả “không model nào đạt”.
- Chốt MVP offline perception evaluation; không gồm train, tự xây map hoặc điều khiển phanh/lái bằng prediction.

Đầu ra: scope, acceptance checklist và JSON fixtures ScenarioSpec/ExperimentSpec/Prediction/EvaluationResult. Người 2 sở hữu schema, người 1 review.

## Bước 2 — Khôi phục checkpoint và dựng môi trường inference

Phụ trách: người 1. Người 2 bắt đầu schema/API bằng mock.

- Lấy our_lidar.pth, our_bevfusion.pth cùng checkpoint hash từ artifact gốc; đối chiếu manifest data/lab/models/CHECKPOINTS.sha256.
- Khôi phục đúng source commit/dependency/env theo README/environment/config hiện có. Kiểm tra đường dẫn config _base_, environment variables và plugin imports; không mặc định config train dùng nguyên xi để inference.
- Tạo inference-only config, chuyển eval mode và preprocessing xác định; kiểm soát yếu tố ngẫu nhiên.
- Chạy một số frame nuScenes mẫu trước, so với prediction đã xuất nếu cấu hình tương đương; kiểm tra boxes/classes/score và ghi dung sai.
- Ghi VRAM, runtime, preprocessing version và lệnh chạy thành công.

Cổng nghiệm thu: cả hai checkpoint nạp và chạy được, không key mismatch/input mismatch. Nếu thiếu checkpoint, CARLA/API vẫn làm song song nhưng không coi inference hoàn tất.

## Bước 3 — Dựng CARLA server và capture baseline

Phụ trách: người 1. Người 2 tạo registry và fake simulator service.

- Khóa bản server/Python client tương thích sau smoke test; kiểm tra map assets và rendering trên máy thật.
- Spawn ego và vài actor tĩnh; lắp camera/LiDAR theo input contract. Radar chỉ cần khi checkpoint yêu cầu, không bắt buộc với hai model khởi đầu.
- Cấu hình synchronous mode, fixed timestep, Traffic Manager sync và seed. Một client sở hữu world.tick mỗi world.
- Thu sensor queues theo frame ID với timeout, kèm world snapshot/ego pose; tránh ghép theo thời điểm callback.
- Camera cần rendering; không dùng no_rendering_mode cho lượt thu camera. Kiểm thử offscreen rendering nếu chạy server không màn hình.

Cổng nghiệm thu: capture ngắn clear baseline có ảnh, point cloud, pose và timestamp đầy đủ; phát hiện được missing sensor/frame.

## Bước 4 — Xuất calibration/GT và làm adapter CARLA

Phụ trách: người 1; người 2 bắt đầu evaluator bằng fixture.

- Xuất sensor transforms, camera intrinsics, actor boxes/classes/velocity và object IDs cùng frame.
- Chốt GT ROI/visibility/ignore policy: không yêu cầu model phát hiện mọi actor trên toàn world.
- Chuyển CARLA x-forward/y-right/z-up sang Lab ego x-forward/y-left/z-up. Kiểm tra transform đầy đủ, local box offsets/rotation, yaw và velocity trong frame thích hợp.
- Chuẩn hóa camera order, RGB/BGR, ảnh, point cloud feature layout và temporal sweeps. Nếu model cần intensity/history không tương đương CARLA, công bố mapping/giới hạn và nghiệm thu input trước khi chạy diện rộng.
- Dùng depth/semantic sensor để kiểm tra hoặc tạo GT khi cần; không đưa GT channels vào model input ngoài khai báo.
- Vẽ GT boxes trên camera và point cloud; test vật thể trước/trái/phải và ego quay/chuyển động bằng fixture biết trước.

Cổng nghiệm thu: overlay và input schema đúng; một checkpoint chạy trên capture CARLA và viewer render đúng. Chưa mở rộng sáu kịch bản nếu cổng này không đạt.

## Bước 5 — Xây thư viện sáu kịch bản

Phụ trách: người 1. Người 2 hoàn thiện scenario registry và validation UI/API.

- Hai nhóm route: urban_crowded và highway_sparse; tách mật độ người/xe thành tham số, đo lại bằng GT trong ROI sau spawn/warmup.
- Mỗi nhóm có clear/rain/fog với tham số cụ thể; lưu spawn blueprints, routes, traffic/pedestrian seeds, weather, rig, capture cadence và simulator/map versions.
- Thu một capture mỗi kịch bản, dùng chung cho mọi checkpoint. Không chạy simulator mới cho từng model rồi mặc định input giống nhau.
- Lưu capture manifest và checksums; kiểm tra độ tái lập trên environment đã khóa. Seed không bảo đảm ảnh bit-identical giữa mọi phần cứng/runtime.
- Lưu requested và realized actor counts; spawn lỗi hoặc thiếu mật độ phải được báo, không im lặng gắn nhãn crowded.
- WeatherParameters mặc định tác động camera RGB, không tự tạo suy giảm vật lý LiDAR/radar. Ghi giới hạn; corruption riêng chỉ thêm khi có mô hình kiểm chứng.

Cổng nghiệm thu: sáu capture đủ sensor/GT, metadata và QA report. Capture hợp lệ được publish manifest sau khi hoàn tất, không dùng file ghi dở.

## Bước 6 — Experiment service và worker bền vững

Phụ trách: người 2 sở hữu DB/API/job DAG; người 1 nối simulator/inference workers.

- Migration registry, experiments, jobs, captures, predictions, metrics, artifacts và agent tool events.
- Pipeline validate → capture/reuse → adapt → inference từng model → evaluate → report; trạng thái từng stage, heartbeat/lease, cancel/retry và idempotency key.
- MVP DB-backed queue, polling UI; không chạy job dài trong request chat. Agent/HTTP disconnect không làm mất job.
- Simulator lease riêng và một owner mỗi world; inference concurrency ban đầu một job/GPU. Trên một GPU ưu tiên capture xong, đóng simulator rồi inference/timing.
- Capture cache theo config/map/rig/version/seed; prediction cache theo capture checksum/checkpoint/preprocessing/runtime. Lặp cùng input dùng lại prediction; đo timing mới bypass cache.
- Cleanup actors/sensors/world settings và lease khi cancel/lỗi; restart simulator/capture job không nối file sai timestamp.

Cổng nghiệm thu: restart/retry không nhân đôi experiment, artifacts hoàn tất có checksum, stage lỗi được thể hiện rõ.

## Bước 7 — Evaluator và lựa chọn model

Phụ trách: người 2 implement, người 1 review hình học/protocol.

- Metric detection theo class/range, recall pedestrian tại operating point đã chốt, lỗi vị trí/vận tốc; giao thức có fixture khớp kết quả kỳ vọng.
- Không gọi metric CARLA tùy chỉnh là nuScenes benchmark chính thức. Chỉ báo NDS nếu đủ thành phần/giao thức tương ứng.
- Đo model-only/end-to-end latency riêng, batch/warmup/GPU synchronization thống nhất, p50/p95 và peak VRAM. Thời gian tạo scene không tính vào latency model.
- Lọc ràng buộc bắt buộc, sau đó xếp hạng bằng metric ưu tiên/Pareto hoặc trọng số đã chuẩn hóa và được chốt; không để LLM tự tính ranking.
- Lưu frame lỗi và evidence. Metric missing/failed không thay bằng 0; kết quả partial không xếp hạng như đầy đủ.
- Tách validation route/seed dùng chọn model/threshold với held-out test. Tăng route/seed và báo số scene/frame, độ bất định trước kết luận cuối.

Cổng nghiệm thu: bảng so sánh tái tạo bằng CLI trên cùng captures, recommendation truy được về GT/prediction/metric.

## Bước 8 — Agent LangGraph

Phụ trách: người 2. Phát triển bằng fixture từ bước 1, nối dữ liệu thật sau bước 6–7.

- Cấu hình một LLM provider cho MVP: API key/model ID phía server hoặc local endpoint có tool calling; không cần fine-tune LLM/vector DB.
- Tools: list_models/maps/rigs/scenarios, validate_experiment, create_experiment, get_status/results, get_failure_frames.
- Agent chuyển yêu cầu tiếng Việt thành spec, backend validate map/rig/model compatibility, quota và actor limits trước khi tạo job.
- LLM chỉ dùng ID/parameters allowlist; không phát shell commands, path checkpoint tùy ý hoặc trực tiếp world.tick.
- Câu hỏi đọc report không tự chạy thí nghiệm. Agent giải thích từ metric/evidence, báo thiếu dữ liệu thay vì bịa.
- Lưu experiment ID/tool events; job chạy tiếp nếu LLM timeout. Không trả suy luận nội bộ làm “analysis”.

Cổng nghiệm thu: bộ 20–30 yêu cầu tiếng Việt gồm thiếu model/map, vượt quota, partial job và không có model đạt; spec/tool calls đúng và không bịa số.

## Bước 9 — UI, viewer và nguồn simulator

Phụ trách: người 2. Người 1 bàn giao capture/prediction mẫu.

- Form map/route/weather/density/rig/seed/duration và checkpoint selection; panel chat chia sẻ context.
- Trang Experiments hiển thị từng stage, cache status, nguồn dữ liệu, cấu hình và bảng metric.
- Định danh simulator bằng source/capture_id/frame_id, không gán nhầm sample_token nuScenes.
- Mở camera/point cloud/GT/prediction đúng capture/model từ frame lỗi. Adapt API nguồn mới thay vì truy vấn CSV nuScenes bằng frame CARLA.
- Không dùng risk/occupancy artifacts nuScenes cho CARLA; chỉ bật lớp nếu có artifact tính thật cho capture đó.
- UI dùng capture đã thu, không cần live stream cửa sổ CARLA. Form vẫn dùng được nếu LLM lỗi.

Cổng nghiệm thu: chọn model/frame không hiển thị stale result; kết quả simulator/real và giới hạn thời tiết thể hiện rõ.

## Bước 10 — Kiểm chứng, đối chiếu thực và bàn giao

Phụ trách: cả hai.

- Demo một yêu cầu → sáu captures/reuse → 12 lượt đánh giá → report → frame tương ứng.
- Kiểm tra cancel simulator, thiếu sensor, restart worker, LLM timeout, cache hit/miss, lỗi một checkpoint và DB recovery.
- Unit/integration CI dùng fake simulator/worker; CARLA/GPU smoke suite chạy trên host thật. Không commit simulator assets/capture lớn vào Git.
- Đối chiếu trên dữ liệu thật theo báo cáo riêng. Thứ hạng CARLA không mặc nhiên xác nhận model tốt trên đường thật.
- Bàn giao lệnh setup/start/stop, API/env configuration, checkpoint/capture manifests, kết quả eval, giới hạn và runbook khôi phục.

## Lịch và điều kiện chuẩn bị

Ước lượng sơ bộ 6–8 tuần cho hai người, map có sẵn, checkpoint và máy GPU sẵn sàng; không gồm train, tạo map mới hoặc corruption vật lý LiDAR/radar.

| Mốc | Người 1 | Người 2 | Cổng chung |
|---|---|---|---|
| Tuần 1 | Bước 2–3 | Schema, DB/API mock | Checkpoint và capture baseline chạy được |
| Tuần 2 | Bước 4 | Evaluator fixtures, registry/DAG | Calibration/GT/input đúng |
| Tuần 3–4 | Bước 5, workers bước 6 | Service bước 6, evaluator bước 7, agent mock | Sáu captures và 12 lượt đánh giá |
| Tuần 5–6 | QA/cancel/resource, hỗ trợ viewer | Bước 8–9, report | Chat tạo thí nghiệm và mở đúng frame |
| Tuần 7–8 dự phòng | Sửa adapter/simulator | Sửa tích hợp/agent/UI | Bước 10, nghiệm thu và bàn giao |

Chuẩn bị ngay: hai trọng số detection, config/source/dependency; CARLA server/client/maps; GPU rendering/inference và storage; LLM API key hoặc local endpoint; DB/artifact root; metric và latency policy. CARLA dùng endpoint nội bộ, không cần API key nhà cung cấp LLM.

## Tài liệu tham chiếu

- Model inventory: data/lab/models/MODEL_ZOO.md và CHECKPOINTS.sha256.
- CARLA synchrony: https://carla.readthedocs.io/en/latest/adv_synchrony_timestep/
- Sensor reference: https://carla.readthedocs.io/en/latest/ref_sensors/
- Bounding boxes: https://carla.readthedocs.io/en/latest/tuto_G_bounding_boxes/
- WeatherParameters: https://carla.readthedocs.io/en/latest/python_api/#carlaweatherparameters

Khi khóa phiên bản CARLA, đối chiếu tài liệu của đúng bản và kiểm chứng sensor/weather behavior trên host triển khai.
