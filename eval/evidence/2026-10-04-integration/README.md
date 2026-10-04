# Integration verification · 2026-10-04

Tích hợp `origin/main` tại `aa78ba9` vào UI branch. [Original manual protocol](../../results/report.md) vẫn giữ evidence trước tích hợp; thư mục này lưu smoke check và screenshot mới.

- Python **3.12.14**; Node **22.23.3**, archive chính thức nodejs.org được đối chiếu SHA256 trước khi dùng.
- Backend Ruff: PASS; pytest **20 passed**. Hai case mới kiểm tra benchmark JSON từ database và fallback files khi DB unavailable; dùng SQLite test riêng, không ghi database production.
- Frontend ESLint + TypeScript: PASS; Next.js **16.3.8** production webpack build: PASS.
- Spatial geometry tests: **3 passed**, không dựng nhà từ điểm cô lập và proxy giữ trong kích thước detection.
- HTTP probes tại frontend **3112** / backend **8013**: **30 responses, 28 assertions PASS**; output/status/header/count/hash trong `api-probes.json`.
- Browser regression: chọn lại cùng scene giữ frame #41; Occupancy tải được với token gốc, ảnh và DOM/timestamp trong `occupancy-node22.png` / `.txt`.
- `manifest.json` ghi byte count và SHA256 các file trong thư mục.

Database của server kiểm thử là SQLite riêng không seed; HTTP case này xác nhận file fallback. Database benchmark contract được kiểm tra bằng pytest với seeded in-memory SQLite. Không thực hiện cloud deploy hoặc đo lại độ chính xác ML.
