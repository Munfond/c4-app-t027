# Evaluation evidence · Perception Lab MVP

Ngày chạy: **04/10/2026**, Asia/Bangkok (UTC+7). Đây là đánh giá chức năng bằng thao tác trên trình duyệt thật và HTTP request thật, không phải bảng test dự kiến. Các thao tác được thực hiện bởi trợ lý qua browser controls theo quy trình manual bên dưới; script chỉ thu response API bổ trợ, không tự chạy các thao tác UI.

**Kết quả: 12 ca đạt điều kiện mong đợi** (10 ca UI, 2 ca HTTP bổ sung); 30 HTTP responses trong bộ probe chính, **28/28 assertions PASS**. Ca Seg3D thiếu artifact và camera fail-closed là negative cases: PASS chỉ xác nhận cách báo thiếu dữ liệu/bảo vệ ảnh, không xác nhận Seg3D đã hoạt động.

## Môi trường và provenance

| Thuộc tính | Giá trị thực tế |
|---|---|
| Frontend kiểm tra | `http://127.0.0.1:3111`, production Next build |
| Backend kiểm tra | `http://127.0.0.1:8001`, FastAPI |
| Branch | `feat/lab-timeline` |
| Base HEAD | `a456546325ddf70ef9c80d5b2c1afdf31a92a795` |
| Trạng thái source | **Dirty working tree** gồm các thay đổi UI/perception chưa commit; không đồng nhất với base HEAD. |
| Frontend build ID | `ictMb4Dig3jqqYYjWVkuo` |
| Python dùng thu output | 3.12.14, `.venv-spatial` |
| Node yêu cầu của repo | 22.x. `node --version` trên shell thu evidence trả 24.21.0; phiên bản executable của server đang chạy chưa xác minh. Không coi lần này là chứng nhận fresh install trên Node 22. |
| HTTP probes | 17:38:56 UTC+7; UI screenshots có timestamp riêng trong file `.txt`. |
| Fixture | `scene-0103`, index **41**, token `3e8750f331d7499e9b5123e9eb70f2e2`, trừ ca playback. |
| Dataset | mini_val: scene-0103 40 frame, scene-0916 41 frame. |
| Camera negative case | Backend tạm riêng `127.0.0.1:8012`, cache trống, anonymizer tắt; đã dừng sau kiểm tra. |

[Source fingerprints](../evidence/2026-10-04/source-fingerprints.json) ghi SHA256 các source trọng yếu để nhận diện phần thay đổi chưa commit. [API outputs](../evidence/2026-10-04/api-probes.json) gồm URL, status, headers, thời điểm, số byte, elapsed và SHA256 response. Array lớn chỉ trích 3 phần tử/count; hash/byte count áp dụng cho body HTTP đầy đủ. Thời gian mỗi request là **một mẫu local**, không phải p95 hay FPS.

## Ca kiểm thử manual và output

### M01 · Camera 360 đồng bộ frame — PASS

**Bước:** Mở `/lab` → Cảm biến → scene-0103 → frame #41 → Camera 360° → Lưới 6 Camera. Gọi từng channel qua endpoint camera cùng token.

**Mong đợi:** 6 ảnh processed, cùng token; không error card; API JPEG 200.

**Thực tế:** UI ghi token `3e8750f3`, hiển thị Front Left/Center/Right và Back Left/Center/Right. Cả 6 request trả **200**, JPEG **1600×900**, `X-Camera-Cache: HIT`, `X-Anonymized: true`. Camera cache HIT không chứng minh bộ lọc đạt recall 100%; chưa đánh giá chất lượng privacy trong ca này.

Bằng chứng: [ảnh UI](../evidence/2026-10-04/M01-camera.png), [DOM/timestamp](../evidence/2026-10-04/M01-camera.txt), sáu responses `/cameras/` trong API outputs.

### M02 · LiDAR/Radar và tick ẩn sensor — PASS

**Bước:** Cùng fixture M01 → LiDAR + Radar → quan sát 2 lớp → bỏ tick Radar → kiểm tra checkbox/point cloud → bật lại.

**Mong đợi:** Điểm đo cùng ego frame; Radar layer ẩn khi unchecked; không thay model hoặc frame.

**Thực tế:** UI/API có **6.763 LiDAR points**, **226 Radar points**. Checkbox Radar chuyển từ checked sang unchecked, điểm Radar không còn trong hình; scene/frame giữ nguyên. Count `Radar · 226` vẫn là tổng dữ liệu đã tải, không giảm về 0 và không có ý nghĩa inference ablation.

Bằng chứng: [hai sensor](../evidence/2026-10-04/M02-sensors-both.png), [Radar ẩn](../evidence/2026-10-04/M02-radar-hidden.png), [DOM checkbox](../evidence/2026-10-04/M02-radar-hidden.txt), responses `/environment` và `/perception/radar`.

### M03 · Detection threshold và hình đại diện 3D — PASS

**Bước:** Kết quả mô hình → Detection 3D → PointPillars → lần lượt ngưỡng **0.30**, **0.70**.

**Mong đợi:** Lọc đúng score, số box không tăng khi tăng threshold; UI có mô tả LiDAR tham chiếu/proxy.

**Thực tế:** **9 → 2 box**, API và UI khớp. Hai score còn lại `0.7787899375`, `0.7074798942`, đều ≥0.7. Tâm gần nhất **5.7 m**; hình 3D ở ngưỡng 0.7 ghi 1 xe, 1 người, 20 mảng mặt dựng. Đây là hình đại diện/nội suy theo output, không nhãn Seg3D.

Bằng chứng: [0.30](../evidence/2026-10-04/M03-detection-030.png), [0.70](../evidence/2026-10-04/M03-detection-070.png), [DOM cuối](../evidence/2026-10-04/M03-detection-070.txt); hai responses `official_lidar`.

### M04 · BEV Occupancy đúng frame/geometry — PASS

**Bước:** Giữ scene/frame → Bài toán Occupancy → kiểm tra grid/legend/source và gọi perception API.

**Mong đợi:** Dữ liệu thật 200×200; cùng token, 0.5 m/cell, đủ legend và giới hạn pseudo-GT.

**Thực tế:** HTTP **200**, `model=BEV Occupancy U-Net`, `shape=[200,200]`, **40.000 cells**, extent 50 m. Count lớp: free **38.720**, static **1.040**, object **240**, tổng 40.000. UI có cảnh báo free chứa vùng chưa quan sát, không phải bản đồ 3D đầy đủ; catalog báo 81/81 artifact.

Output trích từ body thực:

```json
{"task":"occupancy","shape":[200,200],"resolution_m":0.5,"extent_m":50,
 "cells_count":40000,"class_counts":{"0":38720,"1":1040,"2":240}}
```

Bằng chứng: [ảnh](../evidence/2026-10-04/M04-occupancy.png), [DOM](../evidence/2026-10-04/M04-occupancy.txt), response `/perception/occupancy` có checkpoint SHA256.

### M05 · Flow output T4 và giới hạn — PASS

**Bước:** Đổi bài toán Flow → đọc tên model, hướng mũi tên và cảnh báo → gọi perception API.

**Mong đợi:** Vector thuộc cùng frame, model/source công khai; không diễn giải thành chuyển động đã xác nhận.

**Thực tế:** HTTP **200**, Temporal U-Net T4, **34 vectors**, `velocity_unit=m/s`, input LiDAR + Radar; vector đầu `[-49.75,4.25,-0.589,-1.638]`. UI ghi “Flow thử nghiệm · Chất lượng còn hạn chế”, catalog 81/81. Ca này không đo EPE lại.

Bằng chứng: [ảnh](../evidence/2026-10-04/M05-flow.png), [DOM](../evidence/2026-10-04/M05-flow.txt), response `/perception/flow` có source/checkpoint hash.

### M06 · Seg3D chưa có dữ liệu — PASS cho empty state; tính năng chưa sẵn sàng

**Bước:** Đổi bài toán Seg3D; kiểm tra thông báo và trạng thái nút Phát. Gọi `/perception/seg3d` cho fixture.

**Mong đợi:** Báo thiếu output, không dùng detection proxy giả làm segmentation, không phát dữ liệu thiếu.

**Thực tế:** Catalog **0/81**, UI “Chưa có phân đoạn 3D cho frame này.”, nút Phát disabled; API **503**:

```json
{"detail":"Required dataset/artifact is not installed"}
```

Bằng chứng: [ảnh](../evidence/2026-10-04/M06-seg3d-unavailable.png), [DOM](../evidence/2026-10-04/M06-seg3d-unavailable.txt), responses catalog và Seg3D.

### M07 · Chuyển nguồn Risk — PASS

**Bước:** Tab Risk, cùng frame → Classical LiDAR, vmax 0.3 → Oracle GT reference, giữ vmax.

**Mong đợi:** Heatmap tải được, phản ánh nguồn đã chọn, nói rõ uncalibrated và độc lập với Detection.

**Thực tế:** Cả hai **200 PNG 600×600**, `X-Risk-Uncalibrated: true`. Header `X-Risk-System` lần lượt classical/oracle, hai SHA256 khác nhau: `cfee6932…ccf9a7` / `5b44a320…58359`. UI chuyển nguồn/ảnh đúng và hiển thị cảnh báo không phải xác suất va chạm.

Bằng chứng: [Classical](../evidence/2026-10-04/M07-risk-classical.png), [Oracle](../evidence/2026-10-04/M07-risk-oracle.png), [DOM Oracle](../evidence/2026-10-04/M07-risk-oracle.txt), hai responses `/risk?`.

### M08 · Compare cùng điều kiện — PASS

**Bước:** `/compare` → scene-0103, frame #41 → A PointPillars, B BEVFusion → ngưỡng 0.30.

**Mong đợi:** Cùng frame/token/threshold/coordinates, có cả hai viewer và nguồn sensor đúng.

**Thực tế:** A **9** box, B **16** box, token `3e8750f3`; hai panel có 6.763 LiDAR points tham chiếu; sensor ghi A LiDAR, B Camera + LiDAR. Cảnh báo pretraining overlap hiện bên dưới. Đây là đối chiếu trực quan, không phép thử thống kê model A/B.

Bằng chứng: [ảnh](../evidence/2026-10-04/M08-compare.png), [DOM](../evidence/2026-10-04/M08-compare.txt), responses official_lidar/official_cl.

### M09 · Benchmark filters và metric provenance — PASS

**Bước:** `/benchmarks` → đọc 81 frames và giới hạn → chọn Occupancy 02 → chọn Flow 03.

**Mong đợi:** Tab nhóm chỉ số lọc bảng đúng, số liệu artifact được thể hiện nhất quán và kèm giới hạn.

**Thực tế:** Occupancy tab hiển thị bảng Occupancy, learned LiDAR+Radar IoU **42.30%**; Flow tab hiển thị bảng Flow, T4 EPE **3.518 m/s**, median angle **49.7°**. API báo bốn section available và đường nguồn metrics. Các số này **đọc từ artifact hiện có**, không retrain/recompute trong đợt này, không phải số liệu của checkpoint mở rộng khác mà người dùng gửi trước đó.

Bằng chứng: [Occupancy](../evidence/2026-10-04/M09-benchmarks-occupancy.png), [Flow](../evidence/2026-10-04/M09-benchmarks-flow.png), [DOM Flow](../evidence/2026-10-04/M09-benchmarks-flow.txt), response `/benchmarks`.

### M10 · Playback và dừng ở cuối scene — PASS

**Bước:** Lab → Cảm biến / LiDAR + Radar, scene-0103 → frame #41 → Phát ở 1×, Lặp unchecked; quan sát sau khi tới cuối scene.

**Mong đợi:** Timeline đổi frame/điểm cùng nhau, không vượt frame cuối; tự tạm dừng khi không loop.

**Thực tế:** Ban đầu frame **#41**, slider **0**, `FRAME 01 / 40`; sau playback frame **#80 / +19.4s**, slider **39**, `FRAME 40 / 40`, status **Đã tạm dừng**, Frame sau disabled. Point set cuối **9.334 LiDAR**, **170 Radar**. Snapshot trước 17:51:54 và cuối 17:52:40 UTC+7. Chưa đo FPS, dropped frames hoặc độ chính xác tốc độ playback.

Bằng chứng: [trước](../evidence/2026-10-04/M10-timeline-before.png), [cuối](../evidence/2026-10-04/M10-timeline-end.png), [DOM/timestamp cuối](../evidence/2026-10-04/M10-timeline-end.txt).

### M11 · Camera fail-closed khi cache miss — PASS

**Bước:** Khởi động backend local tạm riêng ở 8012 với raw dataset có sẵn, `CAMERA_CACHE_DIR` trỏ thư mục trống, `ANONYMIZER_ENABLED=false`. Gọi CAM_FRONT của fixture; dừng backend tạm. Không thay đổi cache của app chính.

**Mong đợi:** Không có processed cache/bộ lọc thì từ chối, không trả ảnh raw dù raw có sẵn.

**Thực tế:** **503**, `Content-Type: application/json`, `original_returned=false`:

```json
{"detail":"Processed camera image unavailable"}
```

Bằng chứng: [response thực, cấu hình tình huống và timestamp](../evidence/2026-10-04/M11-camera-failclosed.json). Đây là kiểm thử đường HTTP bằng terminal, không screenshot UI và không chứng minh chất lượng blur.

### M12 · Invalid inputs không trả dữ liệu giả — PASS

**Bước:** Qua Next rewrite, GET scene `not-a-scene`, frame `not-a-frame`, model `not-a-model`, threshold `1.1`, task `not-a-task`.

**Mong đợi:** 404 cho unknown scene/frame, 422 cho invalid model/threshold/task.

**Thực tế:** Theo thứ tự **404, 404, 422, 422, 422**. Output scene: `{"detail":"Scene not found"}`; frame: `{"detail":"Frame not found"}`; model: `{"detail":"Unknown model"}`; task: `{"detail":"Unknown perception task"}`. Threshold validation trả detail `less_than_equal` với bound 1.

Bằng chứng: năm responses cuối [API outputs](../evidence/2026-10-04/api-probes.json). Ca HTTP manual protocol được collector thực hiện lặp lại; không tính là thao tác UI.

## Cách tái lập và giới hạn kết luận

Setup theo [README](../../README.md), cài bộ artifact đúng split; đổi base URL/cổng theo máy. Làm theo từng bước M01–M10 trên browser, lưu screenshot và thời điểm. Thu response bổ trợ từ repo root:

```powershell
.\.venv-lab\Scripts\python.exe scripts/capture_eval_evidence.py --base-url http://127.0.0.1:3000 --backend-url http://127.0.0.1:8000 --output eval/evidence/new-run/api-probes.json
```

M11 cần backend riêng/cache trống và raw thực; không xóa cache production để thử. Bộ HTTP probe cố định kỳ vọng dataset hiện tại (81 frame, 7 models và Seg3D thiếu); nếu artifact/split thay đổi, cập nhật protocol và lưu run mới. Không ghi đè evidence cũ để làm như cùng run.

Chưa kiểm chứng trong lần này: fresh clone/install, Node 22 server runtime, VPS/public HTTPS, concurrent users/uptime, keyboard/mobile audit toàn bộ, p95/FPS, privacy recall, full nuScenes held-out benchmark, model robustness thời tiết và Seg3D inference. Không dùng 12 PASS để kết luận model an toàn hoặc chất lượng Flow đã được cải thiện.

Snapshot trên ghi nhận source chưa commit tại thời điểm chụp. Sau đó bộ evidence được đưa vào Git cùng giao diện/source tương ứng; dataset/video lớn vẫn ngoài Git. [Evidence index](../evidence/2026-10-04/README.md).

## Kiểm tra bổ sung sau tích hợp main

Đã tích hợp main `aa78ba9` với database adapters và cloud configuration, rồi kiểm tra lại bằng Python 3.12/Node **22.23.3**. Backend lint và **20 pytest cases** đạt (gồm benchmark database contract và file fallback); frontend ESLint, TypeScript, webpack production build và **3 geometry tests** đạt. HTTP smoke probe mới có **30 responses / 28 assertions PASS**. Bằng chứng của lần tích hợp được lưu riêng ở [integration evidence](../evidence/2026-10-04-integration/README.md); không sửa timestamp/hash của run manual trước.

Trong browser review bổ sung, chọn lại cùng scene từng làm xóa frames mà không kích hoạt tải lại. Handler nay bỏ qua lựa chọn không đổi, và refresh tải lại danh sách frames. Đây là sửa lỗi chức năng sau run manual gốc; không phải thay đổi model/metrics. Bản build Node 22 mới được kiểm tra riêng, không xác nhận Node 22 runtime của preview cũ hay VPS.
