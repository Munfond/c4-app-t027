# Architecture · Perception Lab

Đối chiếu code ngày 04/10/2026: **offline inference → artifact theo frame → read-only API → browser renderer**. Model perception không chạy trong mỗi HTTP request. Máy chuẩn bị và máy phục vụ có thể cùng máy trong local.

## Components và data flow

```mermaid
flowchart LR
  subgraph OFF[Offline preparation / research machine]
    RAW[(nuScenes mini raw)]
    CKPT[(Pretrained / team checkpoints)]
    DET[Detection export + late fusion]
    PERC[export_perception.py / Radar + Occupancy + Flow]
    MEDIA[prepare_demo_media.py / LiDAR + camera anonymization]
    EVAL[Research evaluation]
    RAW --> DET
    CKPT --> DET
    RAW --> PERC
    CKPT --> PERC
    RAW --> MEDIA
    CKPT --> MEDIA
    DET --> EVAL
    PERC --> EVAL
  end
  subgraph STORE[Artifact storage / LAB_DATA_ROOT]
    CSV[(Frame catalog + detection CSV)]
    JSON[(Perception + environment JSON)]
    JPG[(Processed camera JPEG)]
    MET[(Metrics JSON + risk MAT)]
  end
  DB[(SQLite / PostgreSQL seeded records)]
  DET --> CSV
  PERC --> JSON
  MEDIA --> JSON
  MEDIA --> JPG
  EVAL --> MET
  subgraph SERVER[Serving machine / CPU with caches]
    API[FastAPI / src.main:app]
    NEXT[Next.js / pages + API rewrite]
    GATE[Caddy / HTTPS + judge authentication]
  end
  CSV --> API
  JSON --> API
  JPG --> API
  MET --> API
  CSV -.->|seed_database.py| DB
  MET -.->|seed benchmark reports| DB
  JPG -.->|seed processed media| DB
  JSON -.->|seed environment only| DB
  DB -->|Frames / detections / media / benchmark reports| API
  API -->|Local JSON / JPEG / PNG| NEXT
  NEXT --> GATE
  API -->|Deployed API responses| GATE
  GATE --> UI[Browser / React + Three.js + BEV canvas]
  UI -->|Scene / token / task / model / threshold| GATE
```

Mũi tên về browser là response data flow. Request routing: [sequence diagram](docs/architecture_diagram.md). Local không cần Caddy: browser → Next `/api/*` rewrite → FastAPI. Compose: Caddy route `/api/*` trực tiếp tới backend, trang tới Next.

## Components thực tế

| Code | Trách nhiệm |
|---|---|
| `frontend/src/components/shell/app-shell.tsx` | Navigation Lab/Compare/Benchmarks/Agent Occupancy, layout. |
| `components/lab/perception-workspace.tsx`, `scene-timeline.tsx` | Shared scene/frame, modes, playback chờ dữ liệu và dừng khi đổi mode/tab ẩn. |
| `sensor-workspace.tsx`, `viewer/PointCloudCanvas.tsx` | Camera 360 và point clouds; tick sensor chỉ ẩn lớp. |
| `viewer/SpatialViewer.tsx`, `BevViewer.tsx`, `PerceptionGrid.tsx` | Detection proxy 3D, BEV, occupancy/flow/semantic points. Seg3D cần artifact thật. |
| `frontend/src/lib/lab-frame-cache.ts` | Bounded browser caches/prefetch; không database. |
| `src/api/lab.py` | HTTP validation, 404/422/503, camera processed-only, risk PNG. |
| `src/services/lab.py` | Catalog/model/CSV adapters, mtime cache, metrics, risk MAT → PNG. |
| `src/database.py`, `src/models/db_models.py` | SQLAlchemy SQLite/PostgreSQL adapters từ main; seeded frames/detections/processed media/benchmark reports và file fallback. |
| `src/services/environment.py`, `perception.py` | Environment và validation token/task/coordinates/geometry/provenance. |
| `src/services/anonymizer.py` | MTCNN face + YOLO plate khi được bật; unavailable thì fail-closed. |
| `scripts/export_perception.py` | Radar alignment, offline occupancy/flow inference và checkpoint provenance. |
| `deploy/compose.yml`, `Caddyfile` | HTTPS/auth gateway, internal services, read-only data mount. |

`src/agent/` và `/api/v1/chat` là scaffold riêng; LLM/LangGraph/ChromaDB không trên critical path Lab. Database là nguồn bổ sung cho cloud; file-based local không cần PostgreSQL server. Perception và risk vẫn dùng file artifacts. Agent chọn trọng số theo thời tiết và mô phỏng thời tiết chưa là tính năng online hiện tại.

## Đồng bộ và diễn giải output

- `exports/L3E/samples.csv` cung cấp scene/index/token/timestamp. Token liên kết các output theo frame.
- **Ego coordinates**: x trước, y trái, z lên; mét; yaw radian CCW. Radar biến đổi calibration/ego pose về frame tham chiếu.
- Detection CSV: `x,y,z,w,l,h,yaw,vx,vy,score,class_name`. API lọc score, không inference lại. CRN camera/radar; LiDAR nền là tham chiếu riêng.
- Occupancy grid 200×200, 0.5 m/cell, extent ±50 m; free/static/object. BEV 2D, không dense voxel 3D.
- Flow vectors `(x,y,vx,vy)` từ temporal checkpoint T4; chất lượng còn yếu.
- Seg3D points `(x,y,z,class_id)`, bảng lớp, `kind=prediction|ground_truth`. Chưa có artifact: 503 và empty state, không dùng proxy thay thế.
- Risk đọc `stage_h/risk_out.mat`, classical/oracle: cùng frame nhưng **không tính lại từ Detection đang chọn**.

## Cache, camera và vận hành

Raw ảnh không mount public/static. Camera chỉ trả processed cache hoặc anonymizer result; không xử lý được thì 503. `X-Anonymized` biểu thị đường phục vụ processed, không chứng minh 100% khuôn mặt/biển số được phát hiện. Review cache trước khi chia sẻ.

Environment cache miss có thể đọc raw LiDAR khi request; camera miss có thể inference khi được bật. Precompute environment và 81×6 camera để tránh tải frame chậm. Raw dataset/cache giữ ngoài Git; bảy checkpoint occupancy/flow được track trong repo. CI không tự deploy; pull/build/restart riêng. [Actual evaluation](eval/results/report.md) chỉ xác nhận môi trường local.

## Nhánh AI Agent Occupancy (mục 04)

Lab/Compare giữ mô hình phục vụ precomputed ở trên. `/experiments` là nhánh riêng:

```mermaid
flowchart LR
  REQUEST[Yêu cầu và session tab] --> APIREPLAY[API replay + kiểm tra scene]
  APIREPLAY --> LLM[LLM create_replay_study]
  LLM --> VALIDATE[Validate raw files / schema / checkpoint]
  VALIDATE --> QUEUE[SQLite queue trong scope phiên]
  QUEUE --> WORKER[Worker CPU / baseline và ứng viên]
  RAWREPLAY[Raw LiDAR / radar / camera] --> WORKER
  CKPTREPLAY[Ba checkpoint occupancy] --> WORKER
  WORKER --> RESULTS[Predictions + metrics + captured points / ảnh]
  RESULTS --> COMPARE[Python so IoU và payload]
  COMPARE --> FE[FE đề xuất + visualization trước/sau]
  COMPARE --> SUMMARY[LLM giải thích theo yêu cầu]
```

`src/agents/replay_agent.py` giới hạn tool/schema và scene; `dataset_replay.py`
biến đổi sensor trước tạo features, giữ nhãn từ raw sweeps; `replay_comparison.py`
chọn cặp model/profile bằng số đo. `experiment_sessions.py` cách ly và dọn phiên;
worker/API dùng ContextVar scoped root. Không LLM polling, không automatic retry.
Camera không vào checkpoint occupancy; ONNX detector là plugin local tùy chọn.
Flow checkpoints và CARLA adapters vẫn có trong repo nhưng không chạy qua FE này.
Chi tiết vận hành: [AI Agent runbook](docs/REPLAY_SENSOR_AGENT.vi.md).
