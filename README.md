# Perception Lab · Team 27

Agent mở dưới dạng bot cạnh Lab; công cụ CARLA/nuScenes nằm trong workspace thay vì thêm tab riêng. LLM lập kế hoạch khi có cấu hình API; inference/evaluation và quyết định được kiểm chứng bằng artifact, không dùng lời LLM làm metric.

Bản phục hồi có PPO offline thực tế trên ba mức giữ điểm LiDAR 100/50/25%. Kết quả test hiện chưa tốt hơn baseline đầy đủ; UI báo đúng điều đó và cho tải evidence, lưu engineer review. Đây là occupancy proxy research, chưa phải CARLA online. CARLA đã có pilot 12 cấu hình LiDAR vật lý (16/32/64 kênh × bốn mức điểm/s), cùng reference và audit input; pilot một route chưa được dùng để train PPO native. Bộ native độc lập tiếp theo đã hoàn tất 48 capture / 960 outcome, chia route 2 train / 1 validation / 1 test, rồi chạy PPO 12 action đủ 8.192 bước. Native PPO chọn cấu hình mặc định ở cả 19 quyết định test; chưa tốt hơn baseline. Đây vẫn là replay nghiên cứu, chưa chuyển sensor online.

- [Khởi động local, phạm vi phục hồi và giới hạn](docs/MVP_RECOVERY_SCOPE.vi.md)
- [Chuyển assets native/PPO sang máy khác](docs/MVP_PORTABLE_ASSETS.vi.md)
- [CARLA native, 12 profile và evidence](docs/NATIVE_CARLA_EVIDENCE.vi.md)
- [Giao thức RL 12 cấu hình CARLA; điều kiện được train](docs/NATIVE_RL_RESEARCH.vi.md)
- [Lời trình bày nhanh theo giao diện](docs/MVP_DEMO_RECOVERY.vi.md)
- [Evidence kiểm tra thực tế](eval/recovery-mvp-2026-10-13/EVIDENCE.vi.md)
- [Hướng dẫn AI Agent: setup, FE/worker, phiên tạm, API](docs/REPLAY_SENSOR_AGENT.vi.md)
- [Prompt kiểm thử](docs/AGENT_TEST_PROMPTS.vi.md)

Demo: [c4-app-t027.vercel.app/lab](https://c4-app-t027.vercel.app/lab).
Frontend Vercel gọi backend qua `/api/...`; deployment được kiểm tra riêng với local evidence.

Lab trực quan hóa ADAS trên nuScenes mini: quan sát Camera/LiDAR/Radar, đối chiếu Detection, BEV Occupancy và Flow theo cùng một frame, rồi xem Risk và nguồn số liệu đánh giá. Đây là công cụ phân tích dữ liệu, không điều khiển xe.

**MVP phục vụ kết quả tính sẵn (precomputed)** qua Next.js + FastAPI. Web không chạy checkpoint mỗi lần đổi frame; máy phục vụ không cần GPU nếu đã chuẩn bị đủ artifact.

- [Architecture: components và data flow](ARCHITECTURE.md)
- [Request sequence và hợp đồng dữ liệu](docs/architecture_diagram.md)
- [Manual evaluation: bước thực hiện, output và ảnh thật](eval/results/report.md)
- [Chuẩn bị dữ liệu/cache offline](docs/LAB_SETUP.vi.md)
- [Deploy và cập nhật VPS](docs/DEPLOYMENT.vi.md)
- [Cloud PaaS/database deployment](docs/DEPLOY_PAAS_GUIDE.vi.md)

## User flow và trạng thái MVP

| Trang | Luồng sử dụng |
|---|---|
| `/lab` | Chọn scene/frame → Cảm biến (6 camera hoặc LiDAR/Radar) → Kết quả mô hình (Detection/Seg3D/Occupancy/Flow) → Risk. Timeline dùng chung trong Lab. |
| `/compare` | Cùng scene, frame và ngưỡng điểm; so sánh hai mô hình Detection trong BEV. |
| `/benchmarks` | Bốn nhóm số liệu, nguồn artifact và giới hạn thực nghiệm. |
| `/experiments` | Agent Occupancy: yêu cầu → baseline/ứng viên → IoU/dung lượng → đối chiếu điểm, occupancy và ảnh trước/sau; lịch sử trong phiên. |

LiDAR tham chiếu hiển thị độc lập với đầu vào mô hình. **CRN sử dụng Camera + Radar**, không có LiDAR. Tick ẩn cảm biến chỉ đổi hình hiển thị, không thực hiện ablation. Timeline phát keyframe dataset, không phải video/inference thời gian thực.

Kiểm chứng local 04/10/2026: 81 frame thuộc 2 scene; Occupancy, Flow và Radar có 81/81 artifact; **Seg3D có 0/81**. Seg3D có UI/API contract, chưa có dữ liệu. Xe/người 3D là hình đại diện theo detection box; mặt nền/mặt dựng nội suy từ LiDAR, không phải semantic segmentation hoặc bản đồ 3D đầy đủ.

## Yêu cầu và dữ liệu

- Python **3.12**, Node.js **22.x** (theo `frontend/package.json`), npm, Git.
- Trình duyệt hỗ trợ WebGL cho Three.js viewer.
- Bộ artifact của đội; nuScenes mini khi đọc cảm biến gốc hoặc chuẩn bị cache. **Clone repo không tự tải raw dataset/cache.** Bảy checkpoint occupancy/flow hiện được Git track; raw dataset, cache lớn và `.env` giữ ngoài Git. Agent cần raw nuScenes và PyTorch; xem runbook riêng ở trên.

Cấu trúc phục vụ đầy đủ MVP, tính từ `LAB_DATA_ROOT`:

```text
lab/
├── exports/L3E/
│   ├── samples.csv
│   ├── pred_lidar_only_ego.csv
│   ├── pred_lidar_camera_ego.csv
│   └── pred_camera_radar_ego.csv
├── fusion/unified/unified_pretrained_ego.csv
├── models/{our_bevfusion_mini,occupancy,temporal_flow}/metrics.json
├── stage_h/risk_out.mat
├── stage_h/results/risk_metrics.json
└── cache/
    ├── cameras/<sample_token>_<CAM_CHANNEL>.jpg
    ├── environment/<sample_token>.json
    └── perception/{radar,occupancy,flow}/<sample_token>.json
```

Own-model CSV bổ sung: `pred_our_lidar_ego.csv`, `pred_our_bevfusion_ego.csv`, `fusion/unified/unified_ours_ego.csv`. Thiếu CSV thì model đó không available. NuScenes root có `v1.0-mini/`, `samples/`, `sweeps/`, `maps/`. Xin bộ artifact từ đội, giữ token/split đồng nhất. Đủ environment/radar/perception/camera cache thì web đọc cache; raw cần cho kiểm tra nguồn, fallback LiDAR và chuẩn bị media. Thiếu artifact cần thiết trả **503**, không tạo kết quả giả.

## Setup local · Windows PowerShell

### Backend

```powershell
git clone https://github.com/AI20K-Build-Phase-Cohort-4/P-027.git
Set-Location P-027
py -3.12 -m venv .venv-lab
.\.venv-lab\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item '.env.example' '.env' }
```

Sửa root `.env` theo máy, ví dụ dữ liệu bên ngoài checkout:

```dotenv
APP_ENV=development
NUSC_ROOT=C:/apps/nuscenes
LAB_DATA_ROOT=C:/apps/lab
SIM_DATA_ROOT=C:/apps/sim
ANONYMIZER_ENABLED=false
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

`ANONYMIZER_ENABLED=false` phù hợp khi processed camera cache đầy đủ. Cache miss khi đó trả 503. **Không cần OpenAI key, PostgreSQL, ChromaDB, CUDA hoặc MATLAB** để xem MVP.

```powershell
.\.venv-lab\Scripts\python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Giữ terminal chạy. Health: `http://127.0.0.1:8000/health`; Swagger: `http://127.0.0.1:8000/docs`. Cổng/bind thực tế do tham số **uvicorn** quyết định; `APP_PORT` không tự đổi cổng lệnh này.

### Frontend · terminal khác

```powershell
Set-Location 'C:/duong-dan/P-027/frontend' # thay bằng checkout của bạn
node --version                        # 22.x
npm ci
if (-not (Test-Path -LiteralPath '.env.local')) { Copy-Item '.env.example' '.env.local' }
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Mở `http://127.0.0.1:3000/lab`. Frontend `.env.local` dùng `API_INTERNAL_URL=http://127.0.0.1:8000`. Trình duyệt gọi `/api/...` cùng origin; Next rewrite tới backend. Đổi địa chỉ backend cần restart dev hoặc build/restart production.

Production build, thay cho dev:

```powershell
npm run build -- --webpack
npm run start -- --hostname 127.0.0.1 --port 3000
```

Linux/macOS: `python3.12 -m venv .venv-lab`, dùng `.venv-lab/bin/python` thay cho đường dẫn Windows; npm tương tự. Webpack tránh vấn đề Turbopack nếu `node_modules` symlink từ worktree khác.

## Environment variables

| Biến / nơi đặt | Mặc định hoặc ý nghĩa |
|---|---|
| `APP_ENV` · root `.env` | `development`; chọn `production` khi deploy. |
| `NUSC_ROOT` | `<repo>/data/nuscenes`; root nuScenes mini. |
| `LAB_DATA_ROOT` | `<repo>/data/lab`; CSV, JSON, MAT, checkpoints/cache. |
| `SIM_DATA_ROOT` | `<repo>/data/sim`; simulation artifacts tùy chọn, không phải thời tiết live. |
| `CAMERA_CACHE_DIR` | `<LAB_DATA_ROOT>/cache/cameras`; chỉ ảnh đã xử lý. |
| `ANONYMIZER_ENABLED` | `false`; `true` cần inference dependencies và weights. |
| `PLATE_WEIGHTS` | `<repo>/weights/plate_yolov8.pt`; YOLO biển số khi tạo cache. |
| `MAX_UPLOAD_BYTES` / `MAX_IMAGE_PIXELS` | `10485760` / `12000000`. |
| `CORS_ORIGINS` | Origin phân cách dấu phẩy; same-origin rewrite không cần browser gọi backend trực tiếp. |
| `LOG_LEVEL` | `INFO`. |
| `API_INTERNAL_URL` · frontend `.env.local` | `http://127.0.0.1:8000`; server rewrite, không phải `NEXT_PUBLIC_*`. |
| `LAB_DOMAIN`, `LAB_VOLUME`, `JUDGE_USER`, `JUDGE_PASSWORD_HASH` · deploy `.env` | Compose/Caddy; hash mật khẩu không commit. |
| `DATABASE_URL` · root `.env` | `sqlite:///./data/app.db`; backend có database adapter (SQLAlchemy), hỗ trợ PostgreSQL cho cloud. File exports/cache vẫn là fallback. |

Database adapter trên `main` hỗ trợ frames/detections, processed cameras, environment và benchmark reports. Với dataset tại đường dẫn tùy chỉnh, catalog/benchmark ưu tiên file; chỉ dùng DB của đúng dataset. Perception JSON và risk MAT vẫn cần artifact; seed database không thay thế chúng. LLM/vector-store/LangSmith là scaffold tùy chọn, không nằm trên luồng Lab. AI-log có cấu hình riêng; không đặt secret trong evidence.

Nếu cần database deployment, đặt `DATABASE_URL` cục bộ rồi chạy `python scripts/seed_database.py` trong venv có `requirements.txt`. Lệnh tạo bảng/nạp frames, detections và metrics; review dữ liệu trước khi seed. `seed_media_database.py` nạp processed camera/environment nhưng xóa các camera rows cũ, chỉ chạy khi chủ động thay bộ media. Không cần seed để chạy file-based local.

Backend Docker tự cài [gói output mini_val](deploy/artifacts/README.md) cho Radar,
Occupancy và Flow (81 frame/task, 243 JSON; khoảng 0.5 MB nén). Gói chứa output thật
đã tính sẵn và hash nguồn, không chứa raw dataset/checkpoint. Seg3D chưa có artifact.
Nếu dùng `LAB_DATA_ROOT` khác `/app/data/lab` hoặc mount volume đè thư mục này, phải
cài bundle vào `LAB_DATA_ROOT/cache/perception` của chính dataset tương ứng.

## Sample queries · PowerShell

Sau khi app chạy và artifact đã cài:

```powershell
$labUrl = 'http://127.0.0.1:3000'
Invoke-RestMethod 'http://127.0.0.1:8000/health'
Invoke-RestMethod "$labUrl/api/v1/lab/models"
Invoke-RestMethod "$labUrl/api/v1/lab/scenes"
$labFrames = Invoke-RestMethod "$labUrl/api/v1/lab/scenes/scene-0103/frames"
$sampleToken = $labFrames.items[0].sample_token
$frameUrl = "$labUrl/api/v1/lab/frames/$sampleToken"
$detections = Invoke-RestMethod "$frameUrl/detections?model=official_lidar&threshold=0.3"
$detections.boxes.Count
Invoke-RestMethod "$frameUrl/perception/occupancy" | Select-Object task,model,shape,resolution_m
Invoke-RestMethod "$frameUrl/perception/flow" | Select-Object task,model,sample_token
Invoke-RestMethod "$labUrl/api/v1/lab/perception/tasks"
Invoke-RestMethod "$labUrl/api/v1/lab/benchmarks" | Select-Object split,frame_count,limitations
Invoke-WebRequest "$frameUrl/cameras/CAM_FRONT" -UseBasicParsing -OutFile "$env:TEMP/lab-camera.jpg"
Invoke-WebRequest "$frameUrl/risk?system=classical&vmax=0.3" -UseBasicParsing -OutFile "$env:TEMP/lab-risk.png"
```

Output thực tế 04/10/2026: scene-0103 có 40 frame; token đầu `3e8750f331d7499e9b5123e9eb70f2e2`, frame index 41; PointPillars threshold 0.3 trả **9** box, threshold 0.7 trả **2**. Risk PNG 600×600, `X-Risk-Uncalibrated: true`. [HTTP evidence có timestamp/hash](eval/evidence/2026-10-04/api-probes.json).

| HTTP | Xử lý |
|---|---|
| 404 | Scene/frame không tồn tại; chọn từ catalog. |
| 422 | Model/task/channel/threshold không hợp lệ. |
| 503 | Artifact thiếu/incompatible hoặc camera không xử lý được; kiểm tra roots/cache. |
| 502 qua Caddy | Upstream chưa chạy/sai cổng; kiểm tra frontend 3000, backend 8000, Caddy 80/443. |

## Checks và thu evidence

```powershell
# Từ repo root, thay đường dẫn dữ liệu theo máy
.\.venv-lab\Scripts\python.exe scripts/check_lab_data.py --nusc-root 'C:/apps/nuscenes' --lab-root 'C:/apps/lab'
.\.venv-lab\Scripts\python.exe -m ruff check src/ tests/
.\.venv-lab\Scripts\python.exe -m pytest tests/ -q
Set-Location frontend
npm run lint
npm run build -- --webpack
```

`requirements.txt` = web + dev; dùng venv riêng với `requirements-inference.txt` cho PyTorch/anonymizer. Chuẩn bị offline trước khi phục vụ. Thu lại HTTP output (không thay thế thao tác manual trong report):

```powershell
# Repo root; đặt cổng theo máy
.\.venv-lab\Scripts\python.exe scripts/capture_eval_evidence.py --base-url http://127.0.0.1:3000 --backend-url http://127.0.0.1:8000 --output eval/evidence/new-run/api-probes.json
```

## Code structure và giới hạn

```text
frontend/src/app/             Next routes: lab, compare, benchmarks
frontend/src/components/      Shell, timeline, cameras, Three.js/BEV viewers, reports
frontend/src/lib/             API clients, bounded caches, render helpers
src/api/                     FastAPI routes / HTTP validation
src/services/                Artifact adapters, camera filter, perception/risk
scripts/                     Offline exports, data/evidence checks
legacy/streamlit_lab/         Research reference, không phải frontend public
deploy/                      Compose + Caddy
eval/                        Manual report và evidence nhỏ được version control
```

81 frame mini_val không phải full benchmark. Official pretraining trùng mini scenes; fusion là object-level late fusion. Occupancy là **BEV 2D**, static dùng pseudo-GT, free chứa vùng chưa quan sát. Learned Flow còn yếu. Risk chưa hiệu chuẩn, không phải xác suất va chạm. Runtime artifacts có thể dùng phần cứng khác nhau. Manual cases chứng minh chức năng và xử lý lỗi, không chứng minh cải thiện độ chính xác ML.

CI chạy backend lint/tests và frontend lint/build trên runner Windows của đội. **CI xanh không tự deploy VPS**; merge rồi pull/build/restart riêng. Evidence local không xác nhận domain public đang hoạt động.

## Agents: CARLA và replay dataset

Trên Ubuntu 22.04, dùng [CARLA Linux setup](docs/CARLA_LINUX_SETUP.vi.md)
để cài driver, chạy server 0.9.16 và kiểm tra capture không cần LLM.

Thành viên mới bắt đầu từ [CARLA + Sensor Agent quickstart](docs/CARLA_AGENT_QUICKSTART.vi.md)
(cài đặt, nghiệm thu, chạy bằng prompt, xử lý sự cố).
Bot mở rộng ngay cạnh workspace để chat, đọc evidence và đối chiếu baseline/ứng viên.
Xem [Bot + evidence + engineer review](docs/AGENT_EVIDENCE.vi.md); `/agent` cũ chuyển về `/carla`.

Xem [Experiments runbook](docs/EXPERIMENTS_RUNBOOK.vi.md) để chạy giao diện `/carla`,
worker bền vững, bảy checkpoint occupancy/flow hiện có và LLM planner tùy chọn.
Adapter CARLA LiDAR đang ở mức experimental và cần server/client cấu hình riêng.
CARLA 0.9.11 trên Windows/GPU 4 GB dùng client Python 3.7 riêng và worker Python mới;
xem [cấu hình CARLA 0.9.11 + agent](docs/CARLA_0911_AGENT_SETUP.vi.md).
Luồng prompt → dữ liệu LiDAR → checkpoint/output có [hướng dẫn dataset](docs/PROMPT_LIDAR_DATASET.vi.md)
và `dataset-index.json` để liên kết từng cấu hình/frame với input và prediction.
Checkpoint radar/flow hiện chạy trên nuScenes; đầu vào CARLA chưa tương thích bị từ chối.

Luồng agent chạy inference trong worker riêng; Lab/Compare vẫn đọc output tính sẵn.
Không dùng kết quả agent để thay thế `cache/perception` của Lab. API key chỉ cần
planning và giải thích, không cần cho xem Lab hoặc CLI replay deterministic.

Replay giữ lịch sử phiên: refresh giữ, đóng tab/Kết thúc phiên dọn
artifacts tạm theo lease. Tải báo cáo để giữ lâu dài. CLI QA giữ output riêng để resume.
Engineer review lưu snapshot độc lập tại `EXPERIMENT_ROOT/engineer-feedback.sqlite3`;
chưa tự dùng feedback để train lại hoặc thay đổi kết quả đo.
Backend/worker phải dùng cùng EXPERIMENT_ROOT. Xem
[runbook hiện tại](docs/REPLAY_SENSOR_AGENT.vi.md) trước khi chạy hoặc deploy.

CARLA dùng form `/carla`; `/experiments` giữ kết quả replay. Cả hai dùng chung panel bot,
với nguồn dữ liệu được chọn rõ ràng trong panel.
Không cần GPU/Vulkan/CARLA để chạy agent replay. Flow có checkpoint và output Lab,
nhưng chưa được hỗ trợ trong agent replay. Cấu hình đạt occupancy không chứng minh
chất lượng detection, flow hoặc risk.

Đối chiếu hai branch và lộ trình RL: [Agent branch audit](docs/AGENT_BRANCH_AUDIT.vi.md), [Active Sensing](docs/ACTIVE_SENSING.vi.md).
