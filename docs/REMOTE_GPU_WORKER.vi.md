# Worker CARLA trên máy GPU cá nhân, backend Render

Tài liệu đi cùng chế độ `EXPERIMENT_EXECUTION_MODE=remote`. Đọc hết phần backend
và chọn **một** cách cài worker theo hệ điều hành. Source có remote protocol;
credentials, database, bucket và GPU phải được chuẩn bị trên môi trường thật.

## 1. Phạm vi và kiến trúc

```text
Vercel → Render/API + LLM → PostgreSQL queue/studies
                  ↑
       GPU worker chủ động gọi HTTPS
           ↓ CARLA + U-Net LiDAR
           ↓ upload bằng URL ký có hạn
        Private S3-compatible bucket → Render kiểm tra → Vercel xem kết quả
```

- Remote v1 chạy **study CARLA Occupancy LiDAR**, baseline và candidate lần lượt.
- Không điều khiển xe bằng LLM/PPO; Traffic Manager vẫn lái xe theo scenario.
- Đây không phải endpoint khởi chạy native PPO online hoặc train RL. Playback PPO
  đã deploy vẫn độc lập và không cần worker/API key.
- Chưa chạy remote nuScenes replay/capture reuse/camera-radar fusion/Flow. Những
  yêu cầu này bị từ chối; chế độ local cũ vẫn giữ nguyên.
- Worker không cần public IP, port forwarding hoặc mở CARLA ra Internet.
- Backend giữ queue/study/review trong PostgreSQL; artifact trong bucket. Tắt máy
  worker hoặc restart Render không xóa kết quả đã hoàn tất.
- Đây là lưu trữ CARLA lâu dài theo cấu hình bucket, không phải lịch sử replay
  tạm theo phiên tab. Code không tự xóa dữ liệu máy worker/bucket sau upload.

## 2. Ai cần chuẩn bị gì?

| Nơi | Chuẩn bị |
| --- | --- |
| Render | Source mới, PostgreSQL, bucket credentials, operator access code, worker tokens; key LLM nếu dùng prompt |
| Vercel | Source mới, `API_INTERNAL_URL` như deployment hiện có |
| Máy GPU | Source cùng phiên bản, CARLA/client, Python/Torch, checkpoint, worker ID/token và thư mục scratch |
| Người dùng | Mã truy cập thí nghiệm do đội cấp; không nhập API key LLM vào form này |

Ba loại secret **khác nhau**: API key LLM, `EXPERIMENT_ACCESS_TOKEN` của người vận
hành và token riêng cho từng worker. Worker không nhận DB password, S3 secret
hoặc LLM key. Không commit `.env`, `.env.worker`, assignment hoặc log có secret.

## 3. Chuẩn bị PostgreSQL và bucket ở backend

### PostgreSQL

Dùng database PostgreSQL hiện có hoặc database riêng, nhưng role phải được tạo
các bảng `remote_*`. Không thay/xóa bảng Lab. Đặt `REMOTE_DATABASE_URL` trên
Render (có thể cùng connection string với `DATABASE_URL`). Không dùng SQLite
trên filesystem Render cho remote queue production.

Migration v1 additive, chạy lại được. Chạy từ local với source mới và cùng URL
queue production trong môi trường được bảo vệ; Render Free không cần shell:

```powershell
# Repo root, Python 3.12. Đặt REMOTE_DATABASE_URL trong .env local được ignore.
.\.venv-lab\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-lab\Scripts\python.exe -m scripts.init_remote_worker
```

Linux dùng `.venv-lab/bin/python`. Output mong đợi:
`Remote queue schema v1 ready. Lab tables were not modified.`

Không chạy seed media: remote migration không cần seed lại dữ liệu Lab và không
xóa camera rows. Backup database theo quy trình của đội trước thay đổi production.

### Private S3-compatible bucket

Tạo bucket private ở S3 hoặc dịch vụ tương thích S3, ví dụ R2. Backend cần quyền
PutObject/GetObject cho prefix dành riêng, không cần bật public bucket. Cấu hình:

```dotenv
REMOTE_STORAGE_ENDPOINT=https://<S3-compatible-api-endpoint>
REMOTE_STORAGE_REGION=auto
REMOTE_STORAGE_BUCKET=p027-experiments
REMOTE_STORAGE_ACCESS_KEY=<backend-only-access-key>
REMOTE_STORAGE_SECRET_KEY=<backend-only-secret-key>
REMOTE_STORAGE_PREFIX=p027-jobs
```

AWS S3 có thể để endpoint rỗng, đặt region AWS thật. Dịch vụ khác dùng endpoint
API S3, không phải URL giao diện dashboard hoặc URL public download.

Worker nhận presigned PUT URL có hạn 15 phút, gắn tên file, kích thước và metadata
SHA; credential backend không được gửi sang worker. Backend stream kiểm tra SHA
từng object trước khi publish, decode PNG, kiểm tra prediction/reference và tính
lại confusion/IoU/recall. Timing và provenance phần cứng vẫn do worker báo cáo;
không coi hash là chứng minh chất lượng model hoặc an toàn thực tế.

Không cần bucket CORS cho upload: upload đi từ Python worker, không từ browser.
FE đọc qua API đã xác thực. Mặc định mỗi file tối đa 32 MiB, tổng trial 512 MiB.
Bucket/DB phải có chính sách quota, backup và retention của đội. Trial lỗi có
thể để lại object chưa publish; chỉ dọn sau khi chắc chắn job đã kết thúc, không
xóa namespace của job đang chạy. Hiện chưa có tác vụ tự garbage-collect bucket.

## 4. Cấu hình Render, sau đó mới bật interactive

Giữ `DATABASE_URL`, `LAB_DATA_ROOT` và các bundle playback đang hoạt động.
Đặt các secret sau trên Render, không đưa vào Vercel:

```dotenv
APP_ENV=production
EXPERIMENT_EXECUTION_MODE=remote
EXPERIMENT_API_ENABLED_IN_PRODUCTION=true
EXPERIMENT_ACCESS_TOKEN=<random-operator-code-at-least-32-characters>
REMOTE_DATABASE_URL=<postgresql-connection-string>
REMOTE_WORKER_TOKENS={"gpu-worker-01":"<different-random-token-at-least-32-characters>"}
REMOTE_LEASE_SECONDS=120
REMOTE_ARTIFACT_MAX_BYTES=33554432
REMOTE_JOB_MAX_BYTES=536870912
EXPERIMENT_MAX_PENDING=5
# Thêm REMOTE_STORAGE_* ở mục 3.
```

Tạo token trên máy tin cậy, mỗi lần tạo dùng cho một mục đích:

```powershell
.\.venv-lab\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy vào secret dashboard, không gửi token vào chat/report/Git. `WORKER_ID` phải
khớp key trong JSON `REMOTE_WORKER_TOKENS`, dùng chữ/số/gạch dưới/gạch ngang,
tối đa 64 ký tự. Thu hồi worker bằng xóa/đổi token tương ứng rồi restart backend.

Nếu dùng OpenRouter:

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<backend-only-key>
EXPERIMENT_AGENT_MODEL=openai/gpt-4o-mini
EXPERIMENT_AGENT_ENABLED=true
```

Hoặc OpenAI: `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, model phù hợp. Không có key
thì vẫn chạy job bằng form/API cấu hình thủ công; prompt và tóm tắt không hoạt động.

Triển khai Render/Vercel từ cùng source mới. Vercel giữ
`API_INTERNAL_URL=https://<backend>.onrender.com`. Người vận hành mở bot, nhập
operator code. API tạo cookie HttpOnly, có hạn 8 giờ, không lưu token trong
localStorage. Xóa cookie hoặc gọi `DELETE /api/v1/experiment-access` để đăng xuất.
Bearer operator token cũng dùng được cho CLI; token worker không mở được UI.

Không bật remote mode trước khi migration và bucket đã chuẩn bị. Render Free
có cold start; đây là phương án demo, chưa bảo đảm SLA. Heartbeat mất mạng làm
worker dừng an toàn; backend/API luôn hoạt động sẽ ổn định hơn cho capture dài.

## 5. Máy GPU: yêu cầu chung

- Python 3.12, Git, source cùng protocol/pipeline với backend.
- CARLA **0.9.16**, Python package **carla==0.9.16** cùng server version.
- Driver NVIDIA và Vulkan hoạt động. `nvidia-smi` chạy được chưa chứng minh Vulkan.
- Chuẩn bị đủ SSD cho runtime và capture, giữ thêm dung lượng trống. Worker giữ
  raw và log khi lỗi; định kỳ kiểm tra dung lượng sau mỗi phiên.
- Managed Linux có guard **10 GiB RAM khả dụng**, không phải tổng RAM. Đóng ứng
  dụng trước khi chạy; không tự hạ guard để vượt lỗi thiếu RAM.
- GPU chạy simulator; inference có thể dùng CPU với `EXPERIMENT_DEVICE=cpu`.
  Chỉ chọn `cuda` khi PyTorch CUDA thực sự hoạt động và đủ VRAM cho cả hai.

Checkpoint bắt buộc:

```text
<LAB_DATA_ROOT>/models/CHECKPOINTS.sha256
<LAB_DATA_ROOT>/models/occupancy/variants/our_occupancy_lidar.pth
```

Source hiện có các checkpoint đã track; vẫn phải verify sau clone/copy. Nếu dùng
adapter thử nghiệm, giữ thêm cặp
`eval/recovery-mvp-2026-10-13/native-input-adapter.{json,sha256}` và cấu hình đúng
`NATIVE_INPUT_ADAPTER_MANIFEST`. Backend/worker phải cùng fingerprint. Adapter
không có hoặc khác hash: worker vẫn nhận raw job nhưng không nhận aligned job.

Không cần nuScenes raw, ROS 2, stable-baselines3 hoặc model LLM local để chạy
study CARLA remote này. Chúng chỉ cần cho những luồng khác.

## 6. Cài worker trên Ubuntu 22.04 — ưu tiên

### Cài source và môi trường

```bash
git clone https://github.com/Munfond/c4-app-t027.git
cd c4-app-t027
python3.12 -m venv .venv-worker
.venv-worker/bin/python -m pip install --upgrade pip
.venv-worker/bin/python -m pip install -r requirements-worker.txt
cp -n .env.worker.example .env.worker
chmod 600 .env.worker
```

Nếu cài Torch từ index CUDA riêng, làm theo bản PyTorch phù hợp driver trước khi
cài requirements; không cài đè driver NVIDIA ngẫu nhiên. Worker CPU inference
cũng dùng được. Không cần cài dependency training RL.

Giải nén bản CARLA Linux chính thức vào `/opt/carla` hoặc thư mục của user. Chạy
worker bằng user thông thường, không chạy Unreal dưới root. Kiểm tra GPU/Vulkan
theo `docs/CARLA_LINUX_SETUP.vi.md`; đừng tự chạy script setup hệ thống nếu chưa
đọc vì có thể thay package/driver.

### Sửa `.env.worker`

Chạy từ terminal mới; biến môi trường đã đặt trong shell được ưu tiên hơn file
dotenv. Không copy nguyên `.env` của backend sang worker.

```dotenv
REMOTE_API_URL=https://p027-deploy.onrender.com
WORKER_ID=gpu-worker-01
WORKER_TOKEN=<token-cua-worker-nay-trong-Render>
WORKER_WORK_DIR=/home/USER/c4-app-t027/data/remote-worker
LAB_DATA_ROOT=/home/USER/c4-app-t027/data/lab
EXPERIMENT_DEVICE=cpu
EXPERIMENT_CPU_THREADS=2
CARLA_SERVER_EXECUTABLE=/opt/carla/CarlaUE4/Binaries/Linux/CarlaUE4-Linux-Shipping
CARLA_HOST=127.0.0.1
CARLA_PORT=2000
CARLA_TM_PORT=8001
CARLA_TIMEOUT_SECONDS=120
CARLA_BRIDGE_TIMEOUT_SECONDS=600
CARLA_MIN_AVAILABLE_MEMORY_GIB=10
```

Thay USER và đường dẫn thật; không copy đường dẫn `/home/USER` nguyên văn. URL
Render là origin HTTPS, không thêm `/api/v1`, không dùng URL Vercel. Thư mục
model và scratch nên dùng đường dẫn tuyệt đối để tránh phụ thuộc cwd.

### Kiểm tra trước chạy

```bash
nvidia-smi
vulkaninfo --summary
.venv-worker/bin/python -m scripts.remote_worker --env-file .env.worker --check
```

`--check` không nhận job, không khởi động simulator. Nó kiểm tra checkpoint,
client, executable, GPU/RAM; không chứng minh capture thành công. `ready=true`
mới chuyển sang bước tiếp. Với managed Linux, không cần mở CARLA trước.

```bash
.venv-worker/bin/python -m scripts.remote_worker --env-file .env.worker
```

Giữ terminal mở. Worker đăng ký và poll khoảng 10 giây khi idle; nhận job thì
runner tự khởi động CARLA, capture, dọn simulator, inference và upload.

## 7. Windows — dùng CARLA server chạy riêng

Chế độ lifecycle tự mở/tắt trong code hiện tại dành cho **Linux**. Trên Windows,
worker remote chạy được nhưng dùng external server; không đặt
`CARLA_SERVER_EXECUTABLE` trỏ `.exe` vì managed preflight sẽ từ chối.

```powershell
git clone https://github.com/Munfond/c4-app-t027.git
Set-Location c4-app-t027
py -3.12 -m venv .venv-worker
.\.venv-worker\Scripts\python.exe -m pip install -r requirements-worker.txt
if (-not (Test-Path .env.worker)) { Copy-Item .env.worker.example .env.worker }
```

Requirements pin client 0.9.16. Nếu wheel CARLA không có cho Python/OS đang dùng, dùng client Python riêng được
hỗ trợ qua `CARLA_PYTHON_EXECUTABLE`, hoặc chuyển Ubuntu; không ép cài wheel
khác ABI. Chưa gọi đây là smoke GPU Windows đã nghiệm thu.

Trong `.env.worker`, dùng root thực tế, ví dụ:

```dotenv
WORKER_WORK_DIR=D:/P027-worker/jobs
LAB_DATA_ROOT=C:/Users/YOU/c4-app-t027/data/lab
CARLA_HOST=127.0.0.1
CARLA_PORT=2000
CARLA_TM_PORT=8001
# Không đặt CARLA_SERVER_EXECUTABLE.
```

Đặt URL/worker ID/token như mục Ubuntu. Khởi động server từ thư mục CARLA:

```powershell
.\CarlaUE4.exe -RenderOffScreen -quality-level=Low -carla-rpc-port=2000
```

Tên executable phụ thuộc gói giải nén. Sau khi server sẵn sàng, tại repo:

```powershell
.\.venv-worker\Scripts\python.exe -m scripts.remote_worker --env-file .env.worker --check
.\.venv-worker\Scripts\python.exe -m scripts.remote_worker --env-file .env.worker
```

External server là simulator dành riêng cho worker, không chạy collector/client
khác cùng lúc. Mỗi trial reset world; không dùng chung với công việc của người khác.
Server external không bị worker tự tắt sau job; người vận hành đóng khi hết phiên.

## 8. Nghiệm thu đầu-cuối

1. Backend `/health` trả 200; public evidence playback vẫn đọc được.
2. Mở bot trên Vercel, nhập operator code. Nguồn remote mặc định CARLA; replay
   bị khóa vì worker v1 không hỗ trợ nguồn này.
3. Bật worker; runtime notice báo online. Nếu offline, vẫn được xếp hàng nhưng
   không có tiến độ giả. Tắt worker idle rồi kiểm tra chuyển offline sau lease.
4. Dùng form thủ công tạo capture Town01/clear/2 frame, 2 xe/0 người trước; không
   bắt đầu bằng Town03 hoặc đông người. Town03 từng có SIG11 ở máy nghiên cứu.
5. Khi smoke qua, dùng prompt: `So sánh baseline LiDAR 32 kênh 600000 điểm/s với
   profile half 300000 điểm/s trong Town01 trời quang, 2 frame, seed42; IoU giảm
   tối đa 0.02.` Đây là thí nghiệm mới, có chi phí LLM nếu key được bật.
6. Chờ baseline và candidate; xem IoU, dung lượng, lý do giữ/chọn và hình đúng frame.
   Không bắt buộc candidate phải tốt hơn; không đổi nhãn/metric để ép kết luận.
7. Tắt worker sau khi backend xác nhận upload. Refresh Vercel, mở lịch sử và xem
   camera/reference/prediction; restart backend rồi kiểm tra lại để chứng minh
   queue/artifact không phụ thuộc filesystem tạm của Render.
8. Tạo job khi worker offline, bật worker để nhận. Thử hủy giữa capture; kiểm tra
   worker dừng và không chạy tiếp candidate của study đã hủy.

Worker giữ model inference cố định. Weather RGB chưa là mô phỏng suy hao LiDAR;
object-cell recall không phải pedestrian detection recall; giảm bytes chưa là
giảm GPU, điện hoặc tiền.

## 9. Vận hành hằng ngày, lỗi và resume

```text
<WORKER_WORK_DIR>/<job-id>/
  assignment.json          # Có lease riêng tư; không upload/chia sẻ
  trial.log
  jobs.sqlite3            # Queue riêng của trial, không phải queue Render
  <job-id>/capture/       # Raw, metadata, ảnh
  <job-id>/predictions/
  <job-id>/references/
  <job-id>/manifest.json
```

- Worker heartbeat trong khi capture/inference/upload, mặc định <=15 giây/lần.
- Lease mặc định 120 giây. Mất heartbeat làm worker dừng; hết lease backend đánh
  dấu lỗi/hủy study, không tự recapture và không giao lại cùng job.
- Ctrl+C dừng worker. Managed Linux dọn simulator sở hữu bởi trial; external
  server vẫn do người vận hành quản lý. Nếu cleanup timeout, kiểm tra process/log
  trước chạy lại; không dùng lệnh kill toàn bộ Python hoặc xóa cả thư mục data.
- Job lỗi giữ `trial.log`; thông báo public cố ý ngắn và không lộ đường dẫn/secret.
- Upload bị gián đoạn: giữ output, không khởi chạy CARLA lại. Trong khi lease
  **vẫn còn hiệu lực**, có thể yêu cầu upload lại rõ ràng:

```bash
.venv-worker/bin/python -m scripts.remote_worker --env-file .env.worker \
  --resume /absolute/WORKER_WORK_DIR/JOB_ID
```

Resume không recapture. Nó đòi trial local đã succeeded, cùng worker/token và job
remote còn running; job đã accepted trả succeeded idempotent. Hết lease, đã hủy
hoặc failed thì từ chối; giữ output để audit và tạo study mới sau khi kiểm tra
simulator. Không có tự phục hồi upload qua nhiều ngày trong v1.

Worker tự thử lại tối đa 3 lần cho lỗi mạng/5xx trong upload và complete; URL
upload 403 được xin lại trong giới hạn đó. Không retry vô hạn hoặc recapture
để chữa lỗi upload. Artifact đã đăng ký không được đổi nội dung/hash.

| Hiện tượng | Kiểm tra |
| --- | --- |
| API 401 | Worker ID/token khớp Render; operator code không thay worker token |
| API 503 | Production opt-in, migration, bucket, backend còn cold start |
| API 409 | Lease đã mất hoặc hủy; dừng, không lặp claim/complete vô hạn |
| API 422 | Protocol/spec/hash/manifest không hợp lệ; xem log backend và local |
| Offline trên FE | Đang chạy đúng module remote_worker? URL origin? HTTPS outbound? |
| Aligned job chờ mãi | Adapter fingerprint worker/backend phải khớp, hoặc tạo raw job |
| Checkpoint mismatch | Cùng file và CHECKPOINTS.sha256; không sửa manifest để bỏ kiểm tra |
| Không đủ RAM | Cần 10 GiB **khả dụng** với managed mode; đóng app, không hạ guard |
| Vulkan/CARLA crash | Kiểm tra graphics driver và native log; CUDA có sẵn chưa đủ |
| Upload 403 | Endpoint/region/key/bucket clock và presigned Content-Length đúng |
| File quá lớn | Giảm frames; chỉ tăng REMOTE_*_MAX_BYTES sau khi kiểm tra RAM/quota |
| Worker không nhận job | ready=false, khác adapter, simulator đang bận hoặc active lease khác |
| Remote queue thiếu bảng | Chạy init_remote_worker với đúng REMOTE_DATABASE_URL |

`--once` chỉ poll/chạy tối đa một trial, không bảo đảm hoàn tất cả study nhiều
trial. Khi vận hành bình thường dùng vòng liên tục. Cập nhật source khi idle;
không đổi checkpoint/adapter lúc study đang chạy. Giữ một worker cho một CARLA
server; tăng số máy không tự thay giới hạn một trial chạy đồng thời của v1.

## 10. Chạy nền tùy chọn trên Ubuntu

Sau khi đã smoke bằng terminal, có thể dùng systemd user service. Không cài dưới
root. Ví dụ `~/.config/systemd/user/p027-worker.service`:

```ini
[Unit]
Description=P027 remote CARLA worker
After=network-online.target

[Service]
WorkingDirectory=/home/USER/c4-app-t027
ExecStart=/home/USER/c4-app-t027/.venv-worker/bin/python -m scripts.remote_worker --env-file /home/USER/c4-app-t027/.env.worker
Restart=on-failure
RestartSec=15
TimeoutStopSec=40

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now p027-worker
journalctl --user -u p027-worker -f
systemctl --user stop p027-worker
```

Thay USER/đường dẫn trước khi chạy. Service user mặc định cần phiên user; muốn
chạy sau logout cần chính sách linger được quản trị máy chấp thuận. Trên Windows
ưu tiên terminal trong bản đầu; chỉ tạo Scheduled Task sau khi smoke và xác nhận
working directory/env đúng. Không gửi `.env.worker` vào log hoặc Task arguments.

## 11. Test và giới hạn nghiệm thu

```powershell
.\.venv-lab\Scripts\python.exe -m pytest tests/test_api/test_remote_workers.py tests/test_api/test_remote_worker_client.py -q
```

Test dùng SQL thật trên SQLite cô lập, HTTP ASGI, object storage giả có hash và
S3 SDK stub; có test chạy checkpoint Occupancy thật với capture tổng hợp.
Test PostgreSQL riêng cũng có trong repo; đặt `P027_TEST_POSTGRES_URL` trỏ database
test để chạy `tests/test_api/test_remote_postgres.py`. Test tạo/drop một schema
ngẫu nhiên riêng, không dùng URL database production để làm test. Đã kiểm tra
giao job đồng thời, migration idempotent và hoàn tất study trên PostgreSQL16 cục bộ.
Các test không thay thế smoke CARLA/Vulkan và bucket production. Không
cần API key LLM để chạy test. Không bật production từ tài liệu này trước khi đã
có credentials, migration và một lượt smoke GPU thành công.
