# BEV không gian và camera cho MVP

## Thay đổi

- BEV có nền LiDAR keyframe, chuyển từ hệ sensor sang hệ ego bằng calibration nuScenes. Không dựng nhà giả từ bounding box.
- Điểm nền lấy trong bán kính 65 m, độ cao -2 đến 12 m, voxel 0.25 m, tối đa 24.000 điểm/frame. Nền sáng là điểm cao hơn 0.4 m, không phải nhãn ngữ nghĩa tòa nhà. Vùng không có điểm chưa chắc là vùng trống.
- Hộp giữ kích thước thật, màu theo khoảng cách **tâm hộp** trên mặt phẳng tới gốc tọa độ xe: dưới 10 m, 10–25 m, từ 25 m. Đây không phải clearance hay xác suất va chạm.
- Bấm hộp hoặc mở “Vật cản đang chọn” để xem dài/rộng/cao, vị trí trước/sau/trái/phải. Viền trắng đánh dấu hộp đang chọn. Nhãn khoảng cách mặc định tắt.
- Model dự đoán hộp vẫn có tập lớp giới hạn; nền LiDAR bổ sung bề mặt quan sát được, chưa phải hệ thống phát hiện mọi vật cản hoặc phân đoạn nhà cửa.
- Camera dùng pipeline có sẵn của đội: MTCNN che mặt + `plate_yolov8.pt` cho biển dài/vuông. Không dùng `yolov8n-face.pt` 9 byte bị hỏng ở checkout cũ. Ảnh chỉ được phục vụ qua API sau xử lý; không đưa camera gốc vào `frontend/public`.
- Benchmarks và camera dùng màu surface/line/teal của app; giữ nguyên số liệu và giới hạn đánh giá.

## Tạo media trên máy có raw nuScenes

Chạy PowerShell tại repo. Các biến dưới đây chỉ áp dụng cho terminal hiện tại; thay đường dẫn theo máy.

```powershell
py -3.12 -m venv .venv-inference
.\.venv-inference\Scripts\python.exe -m pip install torch==2.2.2 torchvision==0.17.2 --index-url https://download.pytorch.org/whl/cpu
.\.venv-inference\Scripts\python.exe -m pip install -r requirements-inference.txt
$env:NUSC_ROOT='D:\Workspaces\vinuni-buildphase\P-027\data\nuscenes'
$env:LAB_DATA_ROOT='D:\Workspaces\vinuni-buildphase\P-027-ui-shell\data\lab'
$env:PLATE_WEIGHTS='D:\Workspaces\vinuni-buildphase\P-027\weights\plate_yolov8.pt'
$env:ANONYMIZER_ENABLED='true'
$env:OMP_NUM_THREADS='2'
$env:MKL_NUM_THREADS='2'
.\.venv-inference\Scripts\python.exe -m scripts.prepare_demo_media --cameras
```

Bỏ `--cameras` nếu chỉ tạo nền LiDAR. `--limit 1` dùng smoke-test, `--overwrite` tạo lại cache. Không trộn các phiên bản model trong cache; khi đổi trọng số cần `--overwrite`. Manifest ghi hash của trọng số biển số, hash từng file và lỗi xử lý; script exit 1 nếu có lỗi. Không chép ảnh thô thay cho ảnh lỗi. Pipeline tự động có thể bỏ sót khuôn mặt/biển số, cần kiểm tra ảnh demo trước khi chia sẻ.

## Đưa lên Windows VPS

Media không nằm trong Git. Gói `P-027-demo-media.zip` có thư mục `cache/cameras`, `cache/environment`, `cache/media-manifest.json`. Copy gói từ máy phát triển vào `C:\apps\P-027-demo-media.zip` bằng RDP/transfer đang dùng. Sau đó trên VPS:

```powershell
Expand-Archive -LiteralPath 'C:\apps\P-027-demo-media.zip' -DestinationPath 'C:\apps\lab' -Force
(Get-ChildItem 'C:\apps\lab\cache\cameras' -Filter '*.jpg').Count
(Get-ChildItem 'C:\apps\lab\cache\environment' -Filter '*.json').Count
```

Với đầy đủ mini-val, kết quả mong đợi là **486 ảnh / 81 nền LiDAR**. Kiểm tra `media-manifest.json` có `errors: []`. Root `.env` của backend:

```dotenv
LAB_DATA_ROOT=C:/apps/lab
CAMERA_CACHE_DIR=C:/apps/lab/cache/cameras
ANONYMIZER_ENABLED=false
```

Backend vẫn trả được ảnh cache khi inference tắt. VPS không cần cài Torch/model hoặc raw nuScenes cho hai lớp đã xuất này. Các tính năng khác cần raw dataset vẫn giữ `NUSC_ROOT` hiện có.

Sau khi PR được merge, dừng đúng tiến trình backend/frontend đang phục vụ (giữ Caddy), rồi:

```powershell
Set-Location 'C:\apps\P-027'
git switch main
git pull --ff-only origin main
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
Set-Location frontend
npm ci
npm run build
```

Mở hai terminal hoặc dùng service/start script hiện có để chạy lại:

```powershell
# Terminal backend, tại C:\apps\P-027
.\.venv\Scripts\python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Terminal frontend, tại C:\apps\P-027\frontend
npm run start -- --hostname 127.0.0.1 --port 3000
```

Kiểm tra `/lab` hai scene, đổi frame, mở đủ 6 camera; thử `/compare` và `/benchmarks`. Đừng dừng runner CI thay cho backend/frontend. Deploy trên VPS cần thao tác trực tiếp trên VPS; kiểm thử local không xác nhận domain đã cập nhật.

## Kiểm chứng local ngày 2026-10-03

- 15 backend tests pass; Ruff toàn bộ src/tests pass; TypeScript và ESLint frontend pass; Next production build webpack pass.
- Đã xuất 81 nền LiDAR + 486 JPEG qua MTCNN/YOLO, 0 lỗi; kiểm tra SHA-256 của 567 file theo manifest.
- ASGI smoke test đọc được 81 endpoint environment và 486 endpoint camera với `ANONYMIZER_ENABLED=false` và raw dataset không được cài trong cấu hình kiểm thử; tất cả ảnh giải mã được.
- Kiểm tra trình duyệt local: đổi frame #41 → #42, số điểm/hộp và camera cùng thay đổi; xem lưới 6 camera và chế độ một camera; chọn vật cản cập nhật khoảng cách/kích thước/vị trí; kiểm tra benchmark desktop và BEV màn hình hẹp.
- Kiểm tra này không chứng minh recall che mặt/biển số 100%, chất lượng model đã tăng, hoặc VPS/domain đã cập nhật.
