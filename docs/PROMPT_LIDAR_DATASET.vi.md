# Tạo dữ liệu từ prompt để chọn cấu hình LiDAR

Luồng hiện có: prompt → LLM gọi create_sensor_study → baseline và các profiles
→ CARLA tạo dữ liệu thật → adapter BEV → checkpoint occupancy_lidar → output
→ metric/so sánh → lựa chọn tạm thời và giải thích của LLM.

Bạn chỉ cần mô tả cảnh, mục tiêu và ngưỡng chất lượng; agent đề xuất các cấu hình
LiDAR trong phạm vi schema. Cấu hình phù hợp được chọn dựa trên kết quả đo:
lượng dữ liệu LiDAR thấp nhất, giảm occupied IoU không vượt ngưỡng, và reference
hash khớp baseline. Không chọn cấu hình chỉ từ nhận xét của LLM.

Ví dụ, chạy trong PowerShell tại repo với CARLA 0.9.11 đang mở:

```powershell
<VENV>\Scripts\python.exe -m scripts.test_sensor_agent --watch --message "Tối ưu LiDAR để giảm dữ liệu nhưng giữ chất lượng checkpoint occupancy_lidar. Town01 trời quang, 4 xe, 0 người đi bộ, seed 42, 20 frame mỗi cấu hình. Baseline 32 kênh, 600000 điểm/giây, tầm quét 100m. Đề xuất tối đa 3 profiles đổi số điểm, số kênh hoặc tầm quét; giữ FOV và vị trí lắp. Chấp nhận IoU giảm tối đa 0.02."
```

`--watch` cho góc nhìn bám theo xe và điều tiết tick theo thời gian thực. Cửa sổ
CARLA cần được mở/hiện trên desktop. CLI tự điều phối worker; chỉ dùng một worker
điều khiển simulator tại một thời điểm.

Prompt cao tốc được hỗ trợ: "Tôi muốn tạo xe chạy trên đường cao tốc với nhiều xe
và thay đổi làn liên tục". Agent chọn Town04, `route_kind=highway`, 15 xe giao thông,
0 người đi bộ và `lane_change_interval_seconds=2.5`. Runner chọn đoạn đường ngoài
giao lộ dài ít nhất 300 m, có ít nhất 3 làn cùng chiều. `capture/manifest.json`
ghi `route_evidence`, `ego_actor_id`, `lane_change_requests` và
`observed_lane_changes`; lệnh đổi làn chưa đảm bảo xe đã hoàn thành đổi làn.

Để quan sát và thu dữ liệu lâu hơn, chạy riêng sau khi study kết thúc:

```powershell
<VENV>\Scripts\python.exe -m scripts.watch_carla --highway --vehicles 15 --lane-change-seconds 2.5 --frames 81
```

Lệnh này thu khoảng 40 giây mô phỏng và chạy checkpoint với LiDAR baseline.

Trong thư mục Artifacts được in ra:

| File | Nội dung |
|---|---|
| study-start.json | Prompt gốc, cấu hình do agent đề xuất, checkpoint và jobs |
| dataset-index.json | Mỗi record liên kết cấu hình LiDAR, frame, input và output |
| comparison.json | IoU, lượng dữ liệu, latency, reference match và lựa chọn |
| agent-summary.json | Thuyết minh gốc của LLM cùng trace các tool đọc/so sánh |
| JOB_ID/capture/frame_NNNN.npz | x, points, labels, valid, rotation, translation |
| JOB_ID/capture/frame_NNNN.png | Camera RGB cùng frame để kiểm tra bằng mắt |
| JOB_ID/capture/frame_NNNN.json | Geometry/box proxy và pose ego |
| JOB_ID/predictions/occupancy_lidar/NNNN.json | Output occupancy checkpoint |

Input checkpoint là `x[[0,1,2,3]]` từ NPZ: 4 kênh BEV trên lưới 200×200.
Mảng `x` lưu 7 kênh để giữ contract chung; 3 kênh radar không được dùng bởi
checkpoint LiDAR. Output JSON có `shape=[200,200]`, `cells` là mảng phẳng gồm
40.000 class IDs và `classes=[free,static,object]` tương ứng IDs 0,1,2.

Ví dụ đọc input và output từ một record (Python backend):

```python
import json
from pathlib import Path
import numpy as np

root = Path("DUONG_DAN_ARTIFACTS")
index = json.loads((root / "dataset-index.json").read_text(encoding="utf-8"))
record = index["records"][0]
with np.load(root / record["input_npz"], allow_pickle=False) as data:
    model_input = data["x"][[0, 1, 2, 3]][None]  # (1, 4, 200, 200)
prediction = json.loads((root / record["prediction_json"]).read_text(encoding="utf-8"))
model_output = np.asarray(prediction["cells"]).reshape(prediction["shape"])
```

Đây là dữ liệu để chạy inference/đánh giá checkpoint có sẵn. Labels là occupancy
proxy trên các ô semantic LiDAR quan sát được; không phải GT đầy đủ. Cấu hình
được chọn chỉ là tạm thời trong các cảnh/seed đã thử. Với CARLA 0.9.11 hiện tại,
dùng 0 người đi bộ. Mỗi study tối đa 3 cảnh, 3 profiles ngoài baseline và 20 frame
mỗi trial. Chỉ checkpoint LiDAR được hỗ trợ trên nguồn CARLA.
