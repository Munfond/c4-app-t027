# Phân công UI/UX cho 3 người — P-027

## Kết quả cần bàn giao
Giám khảo truy cập một URL HTTPS, đăng nhập bằng tài khoản demo, chọn scene/frame, xem dữ liệu và so sánh model. Web chạy ổn định bằng artifact tính sẵn; không cần Kaggle, MATLAB hay GPU đang online.

Bản nền hiện có: FastAPI đọc scene/frame/detection/benchmark từ data/lab; raw nuScenes đặt tại data/nuscenes. API camera chỉ trả ảnh qua anonymizer, mặc định chưa bật. UI hiện vẫn là skeleton, chưa phải sản phẩm hoàn chỉnh.

## Ranh giới công việc

| Người | Trách nhiệm chính | File/thư mục chính | Bàn giao |
|---|---|---|---|
| 1 — UI/UX, tích hợp & deploy | Design system, app shell, scene/frame selector, timeline, shared state, CI và triển khai Docker + Cloudflare Tunnel | frontend/src/app/; frontend/src/components/ui/, shell/, scene/; frontend/src/lib/api/, types/; frontend/package.json và lockfile; deploy/; .github/; frontend/Dockerfile | Giao diện chung, điều khiển dữ liệu, URL HTTPS có đăng nhập, kiểm tra bên ngoài và rollback |
| 2 — Viewer & tương tác | BEV/Three.js, boxes, legend, layer controls, split-screen và đồng bộ góc nhìn | frontend/src/components/viewer/; frontend/src/lib/geometry/, viewer/ | Viewer dữ liệu thật, pan/zoom/reset, confidence và compare cùng frame |
| 3 — Backend, camera & benchmark/report | API, dependency Python, dữ liệu, anonymization/cache, camera panel, toàn bộ bảng metric và trang báo cáo | src/; tests/; requirements*.txt; Dockerfile backend; frontend/src/components/camera/, benchmark/, reports/ | Backend chạy được, healthcheck, ảnh đã xử lý, benchmark/report đúng nguồn và hỗ trợ lỗi API khi deploy |

“Trách nhiệm chính” là người chủ trì viết/sửa phần đó, không phải quyền truy cập GitHub. Các thư mục component là cấu trúc dự kiến, tạo khi triển khai. Khi cần sửa phần người khác phụ trách, thống nhất trước.

Người 1 quản lý package.json/lockfile, layout và routing; người 2/3 đề xuất dependency rồi người 1 cập nhật. Người 3 chịu trách nhiệm trọn phần benchmark/report (API lẫn component); người 1 chỉ gắn component vào route. Người 3 cung cấp backend image, biến môi trường, data mount và healthcheck; người 1 tích hợp Compose/gateway/tunnel và CI. Thay đổi Dockerfile backend do người 3 chủ trì, người 1 review khi liên quan deploy.

Nhánh theo công việc: người 1 dùng feat/ui-shell, feat/scene-selector, feat/timeline, feat/demo-deploy; người 2 dùng feat/bev-viewer, feat/model-compare; người 3 dùng feat/camera-anonymization, feat/benchmark-report. Mỗi PR tạo từ main mới sau khi PR nền được merge.

## Giao diện thống nhất trước khi làm song song
- Desktop 1440px: sidebar điều hướng; thanh trên scene/model; giữa viewer; bên phải thông tin và layer; dưới timeline.
- Màn hình nhỏ: panel có thể đóng, không ép hai viewer cạnh nhau khi thiếu chiều rộng.
- Shared selection: sceneId, sampleToken, modelA, modelB, threshold, layers, playbackState.
- Người 1 sở hữu shared selection. Viewer nhận props/onChange, không tự fetch scene hoặc giữ timeline riêng.
- Cùng một sampleToken cho hai phía compare; khi đổi scene phải dừng playback và chọn frame hợp lệ.
- API client dùng relative /api/v1; localhost dev qua Next rewrite, production qua Caddy.
- Giao diện có loading, empty, missing artifact, camera unavailable, error + retry; không thay dữ liệu thiếu bằng số giả.
- Có nhãn “Tính sẵn”, “Official”, “Own”, “Mixed”; split mini-val hiển thị cạnh metric.
- Việc hiển thị 3D từ BEV 2D phải ghi rõ phép biểu diễn; không gọi là voxel occupancy ground truth.
- Risk là điểm không hiệu chuẩn; flow EPE tính m/s, không gọi là ADE/FDE. Không so latency khác phần cứng như cùng điều kiện.

## Mốc bàn giao và phụ thuộc
Ước lượng 5 ngày làm việc, điều chỉnh theo thời gian thực tế của đội.

### Ngày 1 — chốt hợp đồng và dựng khung
- Người 1: wireframe 3 màn Lab / Compare / Benchmarks; theme, layout, API client và state; chọn máy demo, kiểm tra Docker và chuẩn bị phương án tunnel.
- Người 2: component viewer nhận fixture từ detection API, trục ego x tiến/y trái/z lên; test chuyển tọa độ và yaw.
- Người 3: xuất OpenAPI, chuẩn hóa metrics; kiểm thử camera/anonymizer và chọn gói dữ liệu demo; bàn giao dependency, biến môi trường và healthcheck cho người 1.
- Cuối ngày: cả 3 thống nhất props, endpoint, dữ liệu mẫu; không mock thêm endpoint khác contract.

### Ngày 2–3 — tích hợp chiều dọc
- Người 1: scene selector, timeline, keyboard next/previous, playback có hủy request cũ; chạy thử bản Docker và đường truy cập demo sớm.
- Người 2: boxes, compare đồng bộ góc nhìn, score và legend; thống nhất nhu cầu GT/point cloud với người 3, chỉ bổ sung sau khi MVP ổn.
- Người 3: hoàn thiện camera panel, xử lý ảnh trước/cache và manifest ảnh đã kiểm tra; viết toàn bộ benchmark/report. GT và point-cloud endpoint là phần mở rộng sau MVP.
- Gate: một frame thật đi từ backend tới UI; đổi scene không trộn frame; camera chưa xử lý không bị phục vụ qua static.

### Ngày 4 — deploy thử
- Người 1: triển khai Docker + Cloudflare Tunnel trên máy đội, tài khoản demo, kiểm tra URL HTTPS, log và rollback; hoàn thiện UX error/retry và loading.
- Người 3: hỗ trợ cấu hình backend/data, healthcheck và lỗi API; kiểm tra camera, metric và báo cáo trên bản deploy.
- Người 2: đo FPS trên máy demo, giới hạn point budget, cleanup WebGL, tránh memory leak khi scrub timeline.
- Cả đội kiểm tra URL bằng máy không thuộc mạng nội bộ.

### Ngày 5 — nghiệm thu
- Xem hai scene, 81 frame; đổi model, threshold, compare; bảng metric khớp JSON nguồn.
- Test khi thiếu artifact/backend chậm/anonymizer lỗi.
- Chạy lint/test/build trong CI; chụp bằng chứng, ghi phiên bản deploy và quay demo dự phòng.
- Gửi giám khảo URL + tài khoản + hướng dẫn 1 trang. Chỉ ghi tính năng đã chạy thật.

## Danh sách PR và mục tiêu 10 merge
Mốc đã xác minh trước đó: main có 1 merge. Sau PR nền feat/lab-foundation, làm 8 PR sau để đạt tổng 10 merge nếu tất cả được merge:

| PR công việc | Người chính | Điều kiện hoàn thành |
|---|---|---|
| App shell + design system | 1 | Layout, routing, component chung hoạt động |
| Scene/frame selector + typed API client | 1 | Chọn đúng scene/sampleToken, có loading/error |
| Timeline + shared state | 1 | Play/pause/next/previous, không trộn frame |
| BEV detection viewer | 2 | Box dữ liệu thật, đúng tọa độ, pan/zoom/reset |
| Compare hai model | 2 | Cùng frame, đồng bộ góc nhìn, threshold/legend |
| Camera + anonymization | 3 | Camera panel đồng bộ frame, xử lý/cache ảnh, không trả ảnh gốc khi lỗi |
| Benchmark/report | 3 | API và component hiển thị metric, nguồn, split, giới hạn |
| CI + deploy + nghiệm thu | 1; cả đội hỗ trợ test | CI pass, URL HTTPS truy cập từ ngoài mạng, tài khoản demo, có cách khôi phục |

Mỗi PR dùng cùng base main mới, CI xanh, một người khác review. PR chỉ tính sau khi merge; không tạo PR rỗng để đủ số. Nếu tiêu chí đếm merge commit, dùng Create a merge commit khi repo cho phép. Không merge toàn bộ các nhánh một lần cuối ngày demo.

## Phương án demo tiết kiệm
Ưu tiên máy đội chạy Docker + Cloudflare Tunnel, chưa cần thuê VPS. Người 1 giữ máy bật, không sleep, mạng ổn định và kiểm tra bằng 4G trước khi gửi link. Quick Tunnel phù hợp thử/demo ngắn, URL có thể đổi; nếu cần URL cố định thì cấu hình tunnel với tên miền. Nếu giám khảo cần truy cập liên tục nhiều ngày, cân nhắc máy/VM của trường hoặc VPS.

Cấu hình deploy/compose.yml hiện có dành cho VPS/domain. Cấu hình gateway/tunnel local là việc người 1 cần bổ sung trong PR deploy; chưa được triển khai. Giữ đăng nhập và chặn media camera chưa kiểm tra khi chuyển sang tunnel. Xem docs/DEPLOYMENT.vi.md.

## Phạm vi MVP và phần mở rộng
MVP: scene/frame, detection BEV, compare, camera đã xử lý, benchmark có provenance, HTTPS ổn định.
Mở rộng: point cloud 3D, occupancy/flow/risk tương tác từ tensor, live CPU inference, tracking.
Không hứa live BEVFusion/CRN hoặc MATLAB trên VPS CPU. Camera-only và own Camera+Radar chưa có checkpoint trong artifact hiện tại.
