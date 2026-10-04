# Chuẩn bị Lab artifacts offline

Clone, venv, Node, env và chạy web: [README](../README.md). Không giả định dữ liệu hoặc môi trường của một máy cũ đã tồn tại sau clone.

## Kiểm tra nguồn

```powershell
# Repo root; dùng Python web venv và đường dẫn thực tế
.\.venv-lab\Scripts\python.exe scripts/check_lab_data.py --nusc-root 'C:/apps/nuscenes' --lab-root 'C:/apps/lab'
```

`capabilities` chỉ kiểm tra một số file/cache tồn tại, không thay thế kiểm tra raw files. Không load PKL để xem detection; API dùng CSV/JSON. Không mount raw thành public.

## LiDAR environment và processed cameras

Root `.env` đặt `NUSC_ROOT`, `LAB_DATA_ROOT`, tùy chọn `CAMERA_CACHE_DIR`. Environment cache không cần Torch:

```powershell
.\.venv-lab\Scripts\python.exe -m scripts.prepare_demo_media --limit 1
.\.venv-lab\Scripts\python.exe -m scripts.prepare_demo_media
```

Camera cần môi trường riêng và weights của đội:

```powershell
py -3.12 -m venv .venv-inference
.\.venv-inference\Scripts\python.exe -m pip install -r requirements-inference.txt
$env:ANONYMIZER_ENABLED = 'true'
$env:PLATE_WEIGHTS = 'C:/apps/weights/plate_yolov8.pt'
.\.venv-inference\Scripts\python.exe -m scripts.prepare_demo_media --cameras --limit 1
# Review ảnh thử trước khi xử lý tất cả
.\.venv-inference\Scripts\python.exe -m scripts.prepare_demo_media --cameras
```

MTCNN có thể tải weights lần đầu; prewarm trên máy chuẩn bị. Script xuất `cache/media-manifest.json` với hash/lỗi. Review blur và lỗi trước khi chuyển 81×6 ảnh lên server; không copy raw JPEG vào processed cache. Web có đủ cache dùng `ANONYMIZER_ENABLED=false`.

## Radar, BEV Occupancy, Flow

Exporter cần raw và checkpoints `models/occupancy/our_occupancy.pth`, `models/temporal_flow/our_flow.pth`. Dùng môi trường inference phù hợp; thử một frame trước:

```powershell
.\.venv-inference\Scripts\python.exe scripts/export_perception.py --nusc-root 'C:/apps/nuscenes' --lab-root 'C:/apps/lab' --tasks radar occupancy flow --limit 1
.\.venv-inference\Scripts\python.exe scripts/export_perception.py --nusc-root 'C:/apps/nuscenes' --lab-root 'C:/apps/lab' --tasks radar occupancy flow
```

Xuất `cache/perception/{task}/{token}.json`, checkpoint/source hash và ego coordinates. Radar đồng bộ về frame tham chiếu. Occupancy 200×200 là BEV 2D; Flow dùng temporal model T4.

Seg3D không nằm trong exporter hiện tại. Cần semantic model/ground truth thật và [contract Seg3D](LAB_PERCEPTION_WORKSPACE.vi.md); hiện có 0/81 artifact. Detection proxy không thay thế Seg3D.

Sau khi chuyển cache lên server, kiểm tra `/api/v1/lab/perception/tasks` và chạy lại [manual cases](../eval/results/report.md) trên môi trường đích. Read-only data mount trong Compose yêu cầu chuẩn bị cache trước.
