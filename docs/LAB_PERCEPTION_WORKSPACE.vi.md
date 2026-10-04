# Lab: cảm biến, kết quả mô hình và Risk

Lab giữ chung scene/frame/timeline khi chuyển giữa ba chế độ. Tab dùng phím mũi tên, Home/End; chỉ tải viewer đang mở. Playback đợi đầu ra của frame hiện tại, tạm dừng khi đổi chế độ hoặc khi tab trình duyệt bị ẩn.

- **Cảm biến:** Camera 360° hoặc điểm LiDAR + Radar. Checkbox chỉ ẩn lớp, không tạo ablation hay chạy lại model. Camera tham chiếu phía trước mở rộng sang Camera 360°. Ảnh giữ chính sách processed-only.
- **Kết quả mô hình:** chọn Detection 3D, Seg3D, Occupancy hoặc Flow. Detection chọn model riêng, hiển thị đầu vào và phân biệt với nền LiDAR tham chiếu. Hình đại diện xe/người không phải Seg3D.
- **Risk:** Classical LiDAR hoặc Oracle GT reference; không tự nối với model Detection. Điểm risk chưa hiệu chuẩn.

## Chuẩn bị dữ liệu ngoài Git

Máy có raw nuScenes và runtime Torch của lab chạy offline từ gốc repo:

```powershell
$env:LAB_DATA_ROOT = 'C:\apps\lab'
.\.venv\Scripts\python.exe scripts\export_perception.py --nusc-root 'C:\apps\nuscenes' --lab-root 'C:\apps\lab'
```

Lệnh mặc định xuất Radar, Occupancy và Flow; thêm `--tasks radar` nếu chỉ cần Radar, `--limit 1` để smoke-test, `--overwrite` để xuất lại. Không inference trong request HTTP. Torch/SciPy phục vụ bước xuất offline; web đọc JSON. Nếu VPS không có Torch/raw, copy `cache\perception` từ máy xuất vào `LAB_DATA_ROOT` trên VPS. Nền LiDAR cần `cache\environment` riêng. Trọng số và raw data không đưa vào Git.

- Radar: 5 keyframe sensor, lọc invalid/ambiguity, chuyển qua world pose của từng sensor rồi về ego pose keyframe LiDAR. Tọa độ mét; vận tốc đã bù ego-motion xoay về cùng hệ trục.
- Occupancy: checkpoint `models/occupancy/our_occupancy.pth`; grid **BEV 2D** 200×200, 0.5m, x forward/y left trong ±50m. Flat cells theo row-major; 0 free, 1 static, 2 object. Free có thể bao gồm vùng chưa quan sát; static dùng pseudo-GT khi huấn luyện.
- Flow: `models/temporal_flow/our_flow.pth`, history và warp theo checkpoint. Vector `[x,y,vx,vy]` ở predicted object cells, lấy mẫu 1m; đơn vị m/s. Mũi tên biểu diễn dịch chuyển dự đoán 1 giây. Chất lượng learned flow vẫn hạn chế; không được coi là chuyển động chắc chắn.
- Đầu ra chứa tên model, sensor đầu vào, token frame và nguồn checkpoint kèm SHA256. Xuất lại không phải huấn luyện lại và không chứng minh tăng metric.

## Đầu ra Seg3D

Repo chưa có checkpoint/nhãn Seg3D theo từng điểm. UI hiển thị trạng thái này thay vì lấy detection box, heuristic height hoặc hình minh họa làm segmentation.

Để nối kết quả thật, đặt `LAB_DATA_ROOT/cache/perception/seg3d/<sample_token>.json`:

```json
{
  "schema_version": "1.0",
  "task": "seg3d",
  "sample_token": "<token trong samples.csv>",
  "coordinates": {"frame": "ego", "x": "forward", "y": "left", "z": "up", "length_unit": "m"},
  "kind": "prediction",
  "model": "Tên model thực tế",
  "sensors": ["lidar"],
  "source": "Checkpoint và bản xuất thực tế",
  "classes": [{"id": 1, "name": "road", "color": "#80abaa"}],
  "points": [[10.0, 2.0, -1.5, 1]]
}
```

Ví dụ chỉ mô tả contract, không phải dữ liệu demo. `kind` là `prediction` hoặc `ground_truth`; mỗi point `[forward,left,up,class_id]` phải có nhãn trong `classes`. Viewer có màu/chú giải và checkbox từng lớp. Không dựng nhà/phần bị khuất khi không có quan sát hay dự đoán.

API: `/api/v1/lab/perception/tasks` đếm số frame có artifact; `/api/v1/lab/frames/{token}/perception/{task}` đọc artifact khớp frame. 404 cho frame lạ, 422 cho task lạ, 503 cho thiếu/hỏng đầu ra. Sau khi thêm cache, dùng “Tải lại dữ liệu” để làm mới trạng thái; nếu cập nhật code cần restart backend và build/restart frontend như quy trình deploy hiện tại.
