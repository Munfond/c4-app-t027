# VINFAST ADAS BEV/4D OCCUPANCY BENCHMARKING LAB

> Tóm tắt 1 câu: Xây dựng môi trường thực nghiệm và đánh giá trực quan (Benchmarking & Visualization Lab) cho mô hình nhận thức BEV và lưới chiếm dụng 4D đa cảm biến (Camera, LiDAR, Radar) dành cho kỹ sư ADAS VinFast.

## Vấn đề (Problem)

Mô tả pain point cụ thể với data/số liệu:
- Ai đang gặp vấn đề? Đội ngũ kỹ sư phát triển ADAS (Perception & Motion Planning) của VinFast.
- Tại sao các giải pháp hiện tại chưa đủ? Phương pháp nhận diện Hộp bao 3D (3D Bounding Box) đơn lẻ thường xuyên gặp hiện tượng bỏ sót vật thể dị hình, thiếu thông tin về không gian trống/chiếm dụng và dễ bị ảnh hưởng khi cảm biến đơn lẻ suy giảm chất lượng (mưa, sương mù, ngược sáng). Khó khăn trong việc ra quyết định lựa chọn cấu hình cảm biến (Camera vs LiDAR vs Radar) tối ưu chi phí và độ an toàn.

## Giải pháp (Solution)

Sản phẩm giải quyết vấn đề bằng cách cung cấp một công cụ Lab trực quan:
- Xử lý Dữ liệu Thực tế: Parse và đồng bộ (timestamp sync) luồng dữ liệu đa cảm biến từ bộ `nuScenes-mini`.
- Trực quan hóa 3D WebGL: Render lưới 3D Voxel (Occupancy Grid), vector dòng chảy 4D (Occupancy Flow) và Point cloud trên nền tảng Web 3D (Next.js + Three.js).
- Benchmark Cấu hình Cảm biến: So sánh đối chiếu trực tiếp hiệu quả của mô hình AI khi sử dụng các cụm cảm biến khác nhau, hiển thị các metric mAP, IoU, ADE/FDE và độ trễ.
- Ẩn danh Dữ liệu (Anonymization): Tự động phát hiện và làm mờ khuôn mặt, biển số xe trên các luồng video trước khi đẩy lên trình duyệt.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Agent & Pipeline | LangGraph + PyTorch (BEVFusion / OccNet) |
| Backend | FastAPI + Python 3.10+ |
| Frontend | React/Next.js + TypeScript + Three.js (WebGL) |
| Data Processing | OpenCV, NumPy, Point Cloud Library (PCL) |
| DevOps | Docker + GitHub Actions |

## Quick Start

```bash
# 1. Clone repo
git clone https://github.com/<ORG-CỦA-KHOÁ>/<MÃ-ĐỘI>.git
cd <MÃ-ĐỘI>

# 2. Setup environment
cp .env.example .env
# Edit .env with your API keys

# 3. Install dependencies
py -m venv .venv
.\.venv\Scripts\Activate.ps1 # Hoặc source .venv/bin/activate
pip install -r requirements.txt

# 4. Setup AI Logs
powershell -ExecutionPolicy Bypass -File scripts\setup_hooks.ps1

# 5. Run development server
uvicorn src.main:app --reload
```

## Project Structure

```
├── src/
│   ├── agents/          # LangGraph agent definitions
│   ├── api/             # FastAPI routes
│   ├── models/          # Pydantic schemas
│   ├── services/        # Business logic (Anonymization, Data Processing)
│   ├── config.py        # Settings
│   └── main.py          # App entry point
├── frontend/            # Next.js & Three.js Web UI
├── tests/               # Test suite
├── docs/                # Documentation
├── eval/                # Evaluation results
├── Dockerfile           # Multi-stage build
└── docker-compose.yml   # Full stack
```

## Team

| Member | Role | Background |
|--------|------|-----------|
| Thành viên 1 | Core AI & System Architect | Ngành Robot & Trí tuệ Nhân tạo |
| Thành viên 2 | Sensor & Geometry Data Engineer | Ngành Cơ điện tử |
| Thành viên 3 | Vision, System Framework & Hardware (Phase 2) | Ngành Điện tử Viễn thông |
| Thành viên 4 | Dataset & Data Loader Engineer | Ngành Kỹ thuật máy tính |

## License

MIT
