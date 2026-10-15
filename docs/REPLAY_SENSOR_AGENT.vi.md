# AI Agent Occupancy: chạy local và hiểu kết quả

Luồng đang dùng trên FE là `/experiments`, mục **04 / Agent Occupancy**.
Không cần CARLA. Agent thử biến đổi dữ liệu sensor nuScenes đã ghi sẵn,
chạy checkpoint và tìm cặp model/cấu hình ít dữ liệu nhất đạt ngưỡng chất lượng.
Đây là thí nghiệm occupancy BEV 2D; không phải điều khiển xe hay đánh giá an toàn.

## 1. Phạm vi và giá trị

| Thành phần | Vai trò hiện tại |
|---|---|
| LLM, mặc định `gpt-4o-mini` | Đọc yêu cầu, gọi tool lập kế hoạch, giải thích báo cáo khi được yêu cầu |
| `occupancy_lidar` | Inference occupancy từ LiDAR |
| `occupancy_radar` | Inference occupancy từ radar |
| `occupancy_lidar_radar` | Inference occupancy từ LiDAR + radar |
| Camera | Chất lượng ảnh/dung lượng; optional ONNX detector consistency |
| Flow, detection, risk | Chưa là mục tiêu của agent replay; xem các kết quả riêng trong Lab/Compare |

LLM giúp chuyển mục tiêu thành thí nghiệm hữu hạn. Python chọn phương án bằng
số đo, không để LLM tự bịa metric hoặc thay đổi lựa chọn. Chưa có vòng tự tìm kiếm
nhiều lượt dựa trên kết quả; tối đa 3 điều kiện và 3 ứng viên mỗi study.

LiDAR/radar: tỷ lệ điểm giữ lại `(0,1]`, khoảng cách 5–100 m, góc ngang 10–360°,
nhiễu tọa độ 0–0.5 m. Camera: scale 0.25–1, JPEG 20–95, blur 0–4.
Không mô phỏng số tia, tần số quét, vị trí lắp, tăng tầm đo hay sensor mới.

nuScenes-mini có 10 scene (8 train, 2 val), nhưng agent hiện chỉ dùng mini-val:
`scene-0103` (40 frames), `scene-0916` (41 frames); 1–20 frames/điều kiện.
`crowded/sparse` lọc theo median số đối tượng annotation trong scene, không đếm riêng
người đi bộ hoặc tạo thêm xe/người. Mưa/sương mù chỉ biến đổi ảnh; LiDAR/radar không
bị suy giảm vật lý. Scene không có trong catalog bị từ chối trước khi gọi LLM.

## 2. Chuẩn bị máy và dữ liệu

Python 3.12, Node.js 22.x, Git; CPU đủ để smoke test 2 frames.
Repo có 7 checkpoint occupancy/flow, SHA256 trong `data/lab/models/CHECKPOINTS.sha256`.
Agent replay chỉ cho phép 3 checkpoint occupancy. Không tự tải weights khác.

Từ repo root, PowerShell:

```powershell
py -3.12 -m venv .venv-lab
.\.venv-lab\Scripts\python.exe -m pip install -r requirements-experiments.txt
# Cần pytest/ruff cho kiểm thử development:
.\.venv-lab\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item '.env.example' '.env' }
```

Sửa `.env` tại repo root (không commit key hoặc đường dẫn máy):

```dotenv
APP_ENV=development
NUSC_ROOT=D:/datasets/nuscenes-mini
EXPERIMENT_ROOT=C:/apps/p027-experiments
EXPERIMENT_DEVICE=cpu
EXPERIMENT_CPU_THREADS=2
EXPERIMENT_AGENT_ENABLED=true
EXPERIMENT_AGENT_MODEL=gpt-4o-mini
OPENAI_API_KEY=<key của anh, chỉ lưu local>
```

Giữ `LAB_DATA_ROOT` mặc định nếu dùng checkpoint trong repo. Raw dataset tải riêng
ở [nuScenes](https://www.nuscenes.org/nuscenes). `NUSC_ROOT` phải chứa `v1.0-mini/`
(metadata JSON), `samples/`, `sweeps/`, `maps/`. Chú ý không trỏ nhầm thư mục cha.
LiDAR sweeps dùng tạo nhãn occupancy tham chiếu: thiếu sweeps không được bỏ qua.
Catalog chỉ kiểm tra sensor ở frame đầu; tạo study kiểm tra tất cả file cần cho
các frame yêu cầu. CSV prediction và camera demo không thay raw sensor.

```powershell
.\.venv-lab\Scripts\python.exe -c "from src.services.dataset_replay import catalog; import json; print(json.dumps(catalog(), indent=2))"
```

Lab đọc output tính sẵn ở vị trí riêng. Nếu Lab thiếu occupancy/flow/radar:

```powershell
.\.venv-lab\Scripts\python.exe -m scripts.perception_bundle install --lab-root data/lab
```

Lệnh kiểm tra hash rồi cài bundle `deploy/artifacts/perception-mini-val.zip`, không
thay thế cache có nội dung khác. Đổi `--lab-root` theo `LAB_DATA_ROOT` thực tế.
Bundle không đủ để chạy agent vì không chứa raw sensors.

## 3. Khởi động FE, API, worker

Ba terminal dùng cùng repo và cùng `.env`. API và worker phải cùng `EXPERIMENT_ROOT`.

Terminal 1 — backend:

```powershell
.\.venv-lab\Scripts\python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8008
```

Terminal 2 — worker:

```powershell
.\.venv-lab\Scripts\python.exe -m scripts.experiment_worker
```

Terminal 3 — frontend:

```powershell
cd frontend
npm ci
$env:API_INTERNAL_URL='http://127.0.0.1:8008'
npm run dev -- --hostname 127.0.0.1 --port 3011
```

Mở http://127.0.0.1:3011/experiments ; Swagger http://127.0.0.1:8008/docs .
Đổi `.env` backend cần restart API/worker; đổi API_INTERNAL_URL cần restart FE.
Không có worker thì kế hoạch vẫn tạo được nhưng inference không tiến triển.
Nút agent bị vô hiệu hóa nếu dataset/key/cờ enabled chưa sẵn sàng.
FE chỉ dùng agent, không có form cấu hình thủ công hay màn hình CARLA cũ.

## 4. Luồng và cách đọc kết quả

1. Nhập yêu cầu → kiểm tra scene → LLM gọi `create_replay_study`.
2. Validate schema/cấu hình/scene/checkpoint/raw files; không tạo job nếu không hợp lệ.
3. Worker chạy baseline tự động và các ứng viên trên cùng tập frame.
4. Python so sánh IoU, dung lượng, PSNR; FE hiển thị kế hoạch và kết quả.
5. Nút giải thích gọi `read_sensor_study`, `compare_sensor_configs`, rồi LLM tổng hợp.

Đọc **kế hoạch thực tế** để xác nhận yêu cầu đã được chuyển đúng. Backend kiểm tra
scene chỉ định, nhưng chưa có ràng buộc đầy đủ cho mọi thông số trong văn bản.
Nếu chỉ tối ưu LiDAR, nói rõ chỉ thay LiDAR, giữ nguyên radar/camera và chỉ chạy
`occupancy_lidar`. Pipeline vẫn đọc các sensor được khai báo.

Chọn cấu hình xem trước, model và frame để xem:

- Điểm LiDAR/radar baseline và ứng viên trong BEV ±100 m; số điểm thật và thông số lọc.
  Tối đa 6.000 điểm/sensor, mật độ vẽ ứng viên điều chỉnh theo tỷ lệ giảm. Đây là
  hình lấy mẫu, không phải đối chiếu từng điểm bị loại. Radar tô độ lớn tốc độ, không hướng.
- Occupancy hai bên và các ô khác nhau tô hồng: cùng frame, cùng checkpoint,
  miền ±50 m, 0.5 m/cell. Ô khác baseline không đồng nghĩa ô sai.
- Camera: độ phân giải, dung lượng và PSNR, ảnh tham chiếu/ảnh ứng viên. Hai ảnh
  được vẽ trong khung cùng kích thước nên có thể trông giống dù độ phân giải giảm.
- Nếu chọn baseline, hai bên giống nhau và UI báo rõ. Thay lựa chọn xem trước
  không gọi LLM, không chạy inference lại.

Mỗi checkpoint so ứng viên với baseline riêng. Ứng viên phải đạt IoU tối thiểu
(mặc định 0.3) và mức giảm tuyệt đối tối đa (mặc định 0.02 = 2 điểm phần trăm).
Cặp model/profile được đề xuất còn phải gần **baseline tốt nhất của các model**
trong ngưỡng đó. Trong các cặp hợp lệ, chọn payload sensor nhỏ nhất; IoU dùng phá hòa.
Nếu không có cặp đạt ngưỡng, không ép chọn. Không gộp IoU với PSNR tùy ý.

Camera chọn riêng theo PSNR và thêm detection retention nếu có detector.
Camera không là đầu vào của ba checkpoint occupancy. Byte/frame là payload:
LiDAR 20 byte/point, radar 72 byte/point, JPEG camera. Chưa đo tiền, điện, chi phí
GPU, overhead mạng hoặc tối ưu latency. Nhãn static occupancy là pseudo-GT;
free gồm vùng chưa quan sát. Kết quả chỉ mang tính thử nghiệm trên frame đã chọn.

## 5. Lịch sử phiên và token

FE giữ session ID trong `sessionStorage`; refresh giữ phiên. Kết thúc phiên hủy
job và dọn DB/ảnh/predictions/cache sau khi worker/request đang giữ file nhả ra.
Đóng tab gửi beacon: dọn sau khoảng 30 giây; không nhận beacon thì TTL 180 giây.
Heartbeat 20 giây; backend janitor 5 giây. Mất kết nối lâu/tab bị đóng băng có thể
hết phiên. Nếu API/worker tắt, dọn khi khởi động lại. Tải báo cáo JSON trước khi đóng
nếu muốn giữ kết quả. File tạm: `EXPERIMENT_ROOT/browser-sessions/<session-id>`.

FE gửi `?session=<id>` hoặc `X-Experiment-Session` để cách ly study/preview.
CLI và API không session giữ artifacts bền vững phục vụ resume; không xuất hiện trong FE.
Gửi yêu cầu mới ẩn kết quả cũ ngay, kể cả khi yêu cầu lỗi; chọn lịch sử để xem lại.
Cùng input/checkpoint/seed thường cho cùng inference; cache không khóa theo câu chữ.

Planning dùng 1 request LLM (trần 2.500 output tokens). Giải thích khi người dùng
bấm nút dùng thêm 3 requests; summary thành công được cache. Polling, inference,
so sánh và visualization không dùng LLM. Không retry provider tự động.
Không cố định giá tiền trong docs: chi phí theo model, token usage và bảng giá provider.

## 6. Kiểm thử không key và với LLM thật

```powershell
# Chạy cả ba checkpoint CPU, baseline/half, không LLM:
.\.venv-lab\Scripts\python.exe -m scripts.test_replay_agent --deterministic --scene scene-0103 --frames 2
# Với key và agent đã bật; gọi cả lập kế hoạch và giải thích:
.\.venv-lab\Scripts\python.exe -m scripts.test_replay_agent --message "So sánh baseline và half cho cả ba model occupancy ở scene-0103, 2 frames"
```

CLI tạo root riêng `EXPERIMENT_ROOT/replay-tests/<run-id>`, lưu comparison JSON,
summary/usage nếu gọi LLM và `agent-plan.json` (không chứa key). Có `--spec` JSON,
`--root` và `--study-id` để resume; `--deterministic` bỏ mọi LLM call.
Không dùng CLI inline worker cùng root với workflow FE/API.

```powershell
.\.venv-lab\Scripts\python.exe -m ruff check src tests
.\.venv-lab\Scripts\python.exe -m pytest tests -q
cd frontend
npm run lint
npm run build -- --webpack
```

Tests provider/ONNX mock không phát sinh token và không chứng minh model camera thật.
Smoke inference dùng checkpoint thật; chưa là benchmark/đánh giá an toàn.
[Prompt kiểm thử và kết quả mong đợi](AGENT_TEST_PROMPTS.vi.md).

## 7. ONNX camera tùy chọn và API

Repo chưa cung cấp detector camera được cấu hình. Nếu có model phù hợp:

```powershell
.\.venv-lab\Scripts\python.exe -m pip install -r requirements-camera-replay.txt
```

Đặt `REPLAY_CAMERA_ONNX`, `REPLAY_CAMERA_INPUT_SIZE` (mặc định 640),
`REPLAY_CAMERA_SCORE_THRESHOLD` (0.25) trong backend `.env`.
Contract: một input float32 RGB NCHW `[1,3,H,W]`, 0–1, resize trực tiếp không letterbox;
output đầu tiên `[N,6]` hoặc `[1,N,6]` post-NMS: `x1,y1,x2,y2,score,class_id` trong
pixel ảnh input. Raw YOLO/fusion exports cần wrapper, không nạp trực tiếp.
Detector hash/settings khóa theo study. Retention ghép cùng class, box IoU ≥0.5,
so với prediction baseline, không GT accuracy/mAP. Baseline không có detection
thì retention null, không tạo bằng chứng giả. Không ONNX vẫn có PSNR/dung lượng.

Endpoint chính dưới `/api/v1/experiments`:

| Endpoint | Ý nghĩa |
|---|---|
| GET `/replay/catalog`, `/registry` | Scene, checkpoint, khả năng agent |
| POST `/replay/agent/start` | `{"message":"..."}`, lập kế hoạch và tạo study |
| POST/GET `/replay/studies` | JSON study cho QA / lịch sử trong scope |
| GET `/sensor-agent/{id}`, `/sensor-agent/{id}/comparison` | Trạng thái / report (409 khi chưa complete) |
| POST `/sensor-agent/{id}/cancel`, `/sensor-agent/{id}/summarize` | Hủy / giải thích |
| GET `/{job}/sensor-preview?index=0` | Điểm và metadata camera theo frame |
| GET `/{job}/predictions/{model}/0` | Occupancy theo frame |
| GET `/{job}/camera?index=0&channel=CAM_FRONT&reference=true` | Ảnh tham chiếu; false cho ảnh ứng viên |
| POST `/sessions`, `/sessions/{id}/touch`, `/suspend`, `/end` | Quản lý phiên; các suffix đều sau `{id}` |

## 8. Lỗi và triển khai

| Triệu chứng | Xử lý |
|---|---|
| Raw sensor/sweep missing | Giải nén đầy đủ bản mini đúng NUSC_ROOT; không bỏ kiểm tra nhãn |
| Study không tiến triển | Worker đang chạy và cùng EXPERIMENT_ROOT? Xem log worker |
| Không đủ frame đông/ít đối tượng | Giảm frames hoặc chọn tất cả đối tượng |
| Yêu cầu mới lỗi nhưng muốn xem cũ | Chọn lượt cũ trong lịch sử; không đọc đó là kết quả mới |
| Lab không xem được occupancy/flow | Cài perception bundle đúng LAB_DATA_ROOT; độc lập với artifact của agent |
| 401/429 provider | Kiểm tra key/billing/quota; không đưa key lên FE, Git hoặc ảnh chụp |
| Checkpoint đổi hoặc reference lệch | Tạo study mới; không so kết quả khác tham chiếu |
| Camera hai ảnh giống nhau | Kiểm tra profile baseline, scale/JPEG và kích thước/dung lượng |
| Phiên 410 | Bắt đầu phiên mới; kết quả hết hạn không khôi phục tự động |

Cloud cần API, worker có PyTorch/raw/checkpoints, FE và vùng lưu tạm dùng chung.
Chỉ deploy FE không đủ chạy agent. Không bắt buộc GPU/CARLA; xem
[deployment của dự án](DEPLOYMENT.vi.md). API experiments ở production mặc định tắt;
cần chủ động bật `EXPERIMENT_API_ENABLED_IN_PRODUCTION` và kiểm soát truy cập/quota.
Phiên không thay thế xác thực. Raw camera preview của experiments không qua
anonymizer của Lab: local hoặc môi trường có quyền truy cập phù hợp, không publish raw.

Các adapter/API CARLA và generic nuScenes còn giữ để tương thích/test; chúng không
được gọi bởi FE mục 04. Hướng dẫn CARLA ban đầu và UI/CLI thử CARLA đã được dọn;
không cần cài CARLA để dùng nhánh hiện tại. Flow checkpoint vẫn giữ trong repo.
