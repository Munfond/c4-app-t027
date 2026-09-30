# Chạy nền lab local

## Python
Môi trường .venv cũ trỏ tới Python 3.10 không còn hoạt động; được giữ nguyên.
Môi trường mới .venv-lab dùng Python 3.12 và requirements.txt (web + dev).

Windows từ repo root:
    powershell -File scripts/setup_lab.ps1 -Python <duong-dan-python-3.12.exe>
    .venv-lab/Scripts/python.exe -m uvicorn src.main:app --reload

Máy hiện tại đã được cài .venv-lab. Swagger: http://127.0.0.1:8000/docs
Frontend:
    cd frontend
    npm ci
    npm run dev
Frontend gọi relative /api/v1/...; rewrite local trỏ http://127.0.0.1:8000.

## Data và cấu hình
Mặc định đường dẫn tính từ repo root, không phụ thuộc working directory:
- data/nuscenes: raw nuScenes-mini đã copy.
- data/lab: model, CSV, JSON, MAT từ main.
- data/sim: số liệu simulation.
Override: NUSC_ROOT, LAB_DATA_ROOT, SIM_DATA_ROOT, PLATE_WEIGHTS bằng đường dẫn tuyệt đối.
    .venv-lab/Scripts/python.exe scripts/check_lab_data.py

Không load .pkl chỉ để xem detection; API dùng CSV và JSON. Không mount data thành public/static.

## API có thật
GET /health
GET /api/v1/lab/capabilities
GET /api/v1/lab/models
GET /api/v1/lab/scenes
GET /api/v1/lab/scenes/{scene_id}/frames
GET /api/v1/lab/frames/{sample_token}/detections?model=our_lidar&threshold=0.3
GET /api/v1/lab/frames/{sample_token}/cameras/{channel}
GET /api/v1/lab/benchmarks
POST /api/v1/anonymize (multipart JPEG/PNG)

404: scene/frame không có. 422: model/channel/threshold không hợp lệ.
503: artifact hoặc bộ xử lý camera chưa sẵn sàng. Không dùng endpoint capabilities như chứng nhận đã kiểm tra toàn bộ raw dataset; chạy check_lab_data.py để kiểm tra đầy đủ.
Live occupancy/flow, GT, point-cloud và tracking API chưa triển khai trong nền này.

## Anonymizer và inference tùy chọn
Web chạy không cần torch, GPU hoặc tải weight. Anonymizer không load khi import app.
Để thử inference, tạo venv riêng, cài requirements-inference.txt. Bộ này ghim torch/torchvision/facenet/Pillow theo constraint cũ, chưa được kiểm thử lại đầy đủ trong đợt chuẩn bị web.
Các môi trường mmdet3d/CRN đóng băng không bị sửa.

Set ANONYMIZER_ENABLED=true và PLATE_WEIGHTS tuyệt đối rồi restart API trong môi trường đã cài inference. MTCNN có thể cần tải weight lần đầu: prewarm trên máy chuẩn bị, kiểm tra thành công trước khi triển khai offline.
Camera và upload dùng chung anonymizer, xử lý trên thread worker, serialize model calls, không trả ảnh gốc khi lỗi.
Đã có unit test validation/fail-closed; cần kiểm thử chất lượng blur trên bộ ảnh thực trước khi bật cho giám khảo. Giải pháp production nên xử lý trước 81 frame x 6 camera và cache kèm provenance/hash; chưa có batch cache trong nền này.

## Kiểm tra
    .venv-lab/Scripts/python.exe -m ruff check src/ tests/
    .venv-lab/Scripts/python.exe -m pytest tests/ -q
    cd frontend
    npm run lint
    npm run build

Các đường dẫn legacy đã chuyển về data/lab và data/nuscenes, MATLAB dùng MATLAB_PROJECT_ROOT; legacy vẫn là công cụ tham chiếu nghiên cứu, không phải web public và chưa được chạy lại toàn bộ.

OpenAPI đã xuất tại docs/lab-openapi.json; frame/detection/model responses có Pydantic schema để frontend sinh type.
