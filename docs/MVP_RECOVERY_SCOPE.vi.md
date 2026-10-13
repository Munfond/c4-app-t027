# MVP phục hồi — 13/10/2026

## Khởi động local

Repo sử dụng: `P-027-recovery-20261013`. Mở terminal backend và frontend tại repo:

```bash
bash scripts/run_local_mvp.sh backend
```

```bash
bash scripts/run_local_mvp.sh frontend
```

Truy cập http://127.0.0.1:3111/lab; health http://127.0.0.1:8000/health. Ctrl+C dừng đúng tiến trình ở mỗi terminal. Khi sửa frontend, chạy `bash scripts/run_local_mvp.sh build`, sau khi build thành công thì Ctrl+C frontend và khởi động lại. Script đóng gói release cố định; build kế tiếp không xóa file của release đang phục vụ. `package` chỉ đóng gói build đã thành công, không thay thế bước compile. Runtime phục hồi và `.env` là cấu hình local, không đưa vào Git. Để chạy lượt đo mới, mở terminal thứ ba: `bash scripts/run_local_mvp.sh worker`. Worker không tự cài CARLA; khi `CARLA_SERVER_EXECUTABLE` trỏ runtime sạch, nó khởi động/dừng server cho từng capture và kiểm tra RAM trước launch. Không dùng checkpoint hoặc dữ liệu hỏng để bỏ qua guard.

Sau reboot, ổ backup Windows phải được mount read-only trở lại trước khi dùng raw nuScenes. Không reset repo cũ hoặc xoá backup.

## Luồng trình bày

1. Lab: chọn scene/frame, xem camera và LiDAR/Radar, chuyển các kết quả model. Model là precomputed khi có nhãn đó trên UI.
2. Mở bot cạnh Lab → cấu hình camera FOV 60/90/110 → mở thiết lập để xem và xác nhận. Preset chỉ thay góc nhìn, không tự tạo thí nghiệm hay tự tuyên bố tối ưu. FOV native đã smoke thành công trên runtime phục hồi.
3. Capture cũ phục hồi: 41 cặp ảnh/prediction hợp lệ từ 81 frame. Play/Pause, scrubber và tốc độ giữ timestamp gốc; tuỳ chọn rút ngắn khoảng trống chỉ đổi nhịp xem; khoảng trống do file hỏng không được biến thành frame giả. Kết quả này chỉ để xem, không dùng làm evidence train.
4. Trong bot, mở “Học tăng cường · PPO offline”: xem baseline, quyết định, nguồn dữ liệu và tải report. Engineer có thể lưu review gắn SHA report; tên tự khai báo, chưa có xác thực vai trò hay tự train lại từ review.

## Học tăng cường đã thực hiện

Dataset nuScenes mini đầy đủ: 404 frame, 10 scene, 1.212 outcome đo cho ba mức giữ điểm 100/50/25%. Đo tiền xử lý + inference occupancy LiDAR trên CPU. Đây là thinning phần mềm trên point cloud đã ghi, không điều khiển sensor vật lý, không đo chi phí GPU/điện năng.

Split policy: 6 scene train, 2 validation, 2 test (81 frame). Model occupancy là checkpoint sẵn có; sự giao nhau giữa dữ liệu pretrain checkpoint và các split chưa được audit độc lập. Nhãn static là proxy LiDAR persistence; object dùng footprint annotation, không phải semantic occupancy GT hoàn chỉnh. Bộ kiểm tra xác minh SHA raw, metadata, checkpoint, artifact, nguồn tạo dữ liệu, không dùng raw/sweep chung giữa split và tái chạy 60 outcome.

PPO run: 12.288 timestep thực tế, 384 cập nhật epoch, trọng số trước/sau khác nhau. Chọn checkpoint bằng validation; sau đó đánh giá test một lần. Policy được chọn từ snapshot validation, không nhất thiết là policy ở bước cuối. Đây là RL offline trên ma trận outcome, chưa phải CARLA online hoặc bằng chứng an toàn ngoài đời.

| Cấu hình | Occupied IoU | Object IoU | CPU p95 |
| --- | ---: | ---: | ---: |
| 100% điểm | 41,0% | 16,0% | 95,7 ms |
| 50% điểm | 35,0% | 12,5% | 93,4 ms |
| 25% điểm | 26,4% | 8,2% | 95,5 ms |
| Rule | 36,6% | 13,6% | 93,0 ms |
| PPO | 41,0% | 16,0% | 95,7 ms |

PPO chọn 100% điểm ở cả 81 frame. **Chưa tìm được cấu hình tốt hơn baseline đầy đủ.** Mạng convolution nhận lưới cố định nên giảm điểm ít thay đổi phần tính toán model nhưng làm chất lượng giảm. Timing trong replay dùng lại phép đo; chưa gồm thời gian quyết định policy. Ngưỡng 500 ms theo keyframe chỉ phục vụ nghiên cứu, không là deadline an toàn ADAS. Không tune lại trên test để ép kết quả tốt hơn.

Nguồn: `data/rl-occupancy-proxy-measured-20261013/{replay.json,audit.json}` và `data/rl-occupancy-ppo-20261013/{report.json,report.sha256,policy-seal.json}`. UI/API kiểm tra cả SHA report và selected policy trước khi phục vụ. Các file đo lớn/policy nằm ngoài Git; bản report/audit nhỏ được lưu ở `eval/recovery-mvp-2026-10-13`.

## Phạm vi camera và việc còn lại

FOV 60/90/110 áp dụng khi spawn camera mới. Góc hẹp phóng lớn vật trên ảnh nhưng giảm coverage; không phải autofocus hoặc lens zoom vật lý. Model occupancy LiDAR không dùng camera, nên chưa thể đánh giá FOV bằng metric occupancy này.

FOV native 60/90/110 đã smoke thành công trên Town01 (2 frame/cấu hình). Còn thiếu: online RL và adapter camera/radar được đánh giá; held-out môi trường/thời tiết; visual QA bản UI mới. Công cụ browser hiện chặn truy cập tab local, nên không tuyên bố đã kiểm tra rendering bản cuối. HTTP và JS/CSS production đã kiểm tra; regression API + Active Sensing đã qua.

Nền phục hồi f560457 giữ 21 commit local trên main137b166. Không ghép toàn bộ backup Windows thiếu module. Schema Detection replay cũ vẫn giữ gate quality/protocol/catalog/split; không đổi dữ liệu diagnostic thành validated. GPU mode lịch sử chỉ để tương thích, không là mục tiêu MVP mới.

## Cache cảm biến đã khôi phục

486 ảnh camera cache lịch sử đã xử lý, khác ảnh raw, qua CRC và giải mã ảnh. Radar, Seg3D, occupancy và flow: 81 JSON mỗi task đã qua validator identity/coordinate/schema. Cache được phục hồi từ ZIP Windows; không tuyên bố vừa chạy lại model. Audit từng file và SHA lưu trong `eval/recovery-mvp-2026-10-13`.

## CARLA server phục hồi

Client 0.9.16 cài lại từ PyPI và import thành công. Server cũ có 5 shared library không có ELF header hợp lệ, nên không chạy. Script `scripts/recover_carla_server.py --extract` tải từ URL trên release chính thức vào `data/runtime/carla-server-recovery`; kiểm tra dung lượng và không ghi đè runtime cũ. Hash tự tính để đối chiếu lần sau, không phải chữ ký/hash do nhà phát hành cung cấp. Bản tối thiểu đã giải nén xong: bỏ debug symbols, HDMaps và Python SDK cài riêng. Binary và 14 shared library có ELF header hợp lệ, loader không báo thiếu thư viện. Installer tự tải được dọn sau đối chiếu SHA để trả lại khoảng 7,8 GiB; runtime gốc và backup không bị xoá. Capture native đã thành công trên Town01; xem [evidence và giới hạn](NATIVE_CARLA_EVIDENCE.vi.md).

Managed CARLA có guard tối thiểu 10 GiB RAM khả dụng trước khi spawn để tránh lặp OOM. Không tự hạ ngưỡng trong môi trường vừa phục hồi. Client import được không đồng nghĩa server/capture đã sẵn sàng. Policy PPO được load lại và ra đúng quyết định trên 81 frame, CPU decision p95 khoảng 0,203 ms; phép đo này riêng với inference, không cộng percentile để tuyên bố end-to-end.

Ba action thinning hiện tại là MVP phục hồi sau hỏng dữ liệu/runtime. Đã có pilot 12 profile LiDAR vật lý trên một route, chưa admit cho training. Camera/radar policy và MultiDiscrete của kế hoạch gốc chưa hoàn thành. Bộ test không được dùng để chọn lại reward hoặc retrain cho số đẹp hơn.

`.env` local trỏ `CARLA_SERVER_EXECUTABLE` tới shipping binary sạch. Chạy `python -m scripts.check_carla_runtime` để đọc preflight; phải đủ RAM trước khi chạy worker. Các smoke đã chạy sau khi guard qua; không hạ guard khi RAM thiếu.

Tiến độ capture CARLA: worker ghi snapshot atomic sau khi lưu cặp camera/LiDAR. UI chỉ đọc count hợp lệ của job đang chạy; không suy diễn phần trăm từ thời gian chờ. Đã qua test contract; capture native mới đã xác minh cặp camera/LiDAR và kết quả model.

### Smoke FOV sau khi đủ RAM

Xem cấu hình mà không tạo job: `python -m scripts.smoke_carla --fov 60 --plan` (tương tự 90/110). Chạy thật chỉ sau khi đủ RAM: `python -m scripts.smoke_carla --fov 60 --output data/runtime/fov-60-new`. Mỗi lần dùng folder mới. Smoke chỉ 2 frame; kiểm tra sensor FOV ghi trong manifest, ảnh camera giải mã đúng 640×360 và số frame. Đây là kiểm tra tích hợp, không là bằng chứng FOV cải thiện chất lượng occupancy. Guard RAM chạy trước khi tạo queue/output; các lần FOV 60/90/110 đều thành công sau khi RAM đủ.
