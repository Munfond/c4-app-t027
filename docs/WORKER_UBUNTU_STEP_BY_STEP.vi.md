# Hướng dẫn setup worker GPU Ubuntu — backend Render, storage R2

Tài liệu dành cho người vận hành máy GPU Ubuntu. Backend và frontend chạy trên
Render/Vercel; máy Ubuntu chỉ chạy worker, CARLA và inference checkpoint.
Đối chiếu code remote worker v1; không phải hướng dẫn train RL.

## 1. Luồng chạy và phạm vi

```text
Người dùng nhập yêu cầu trên Vercel
  → Render/LLM tạo study và queue trong PostgreSQL
  → worker Ubuntu chủ động nhận job qua HTTPS
  → worker mở CARLA, capture và chạy checkpoint Occupancy LiDAR
  → worker upload artifact vào R2 bằng URL ký có thời hạn
  → Render kiểm tra artifact, tính lại metric, cập nhật study
  → người dùng xem kết quả và so sánh trên FE
```

- Worker v1 hỗ trợ study CARLA Occupancy LiDAR; baseline/candidate chạy lần lượt.
- Chưa nhận remote job camera/radar fusion, Flow, nuScenes replay hoặc PPO online.
- Camera trong capture giúp đối chiếu bối cảnh; không phải input của model LiDAR.
- Worker không cần IP public, mở port router, Node.js, frontend, API key LLM,
  mật khẩu database hoặc key R2. Không mở cổng CARLA ra Internet.
- Một thời điểm hệ thống chỉ giao một trial CARLA. Một study có thể gồm nhiều trial.
- Khi máy worker tắt, job mới có thể chờ trong queue; kết quả đã upload vẫn xem được.

## 2. Thông tin quản trị viên phải cấp trước

| Thông tin | Ví dụ / ý nghĩa |
| --- | --- |
| Backend origin | `https://p027-deploy.onrender.com` |
| Worker ID | `gpu-worker-01` |
| Worker token | Token riêng tối thiểu 32 ký tự, khớp cấu hình Render |
| Source | Repo mirror `Munfond/c4-app-t027`, branch `main` |
| Operator access code | Người dùng FE cần mã này; khác token worker |

Token worker phải được khai báo trước trên Render, ví dụ
`REMOTE_WORKER_TOKENS={"gpu-worker-01":"<WORKER_TOKEN>"}`. Chỉ biết URL backend
không đủ để nhận job. Mỗi máy dùng ID/token riêng.

Quản trị viên xác nhận các việc sau đã hoàn tất:

- PostgreSQL đã có schema remote, tạo bằng `python -m scripts.init_remote_worker`.
- Render có `REMOTE_DATABASE_URL`, `EXPERIMENT_EXECUTION_MODE=remote`,
  `EXPERIMENT_API_ENABLED_IN_PRODUCTION=true`, `EXPERIMENT_ACCESS_TOKEN` và
  `REMOTE_WORKER_TOKENS`.
- Bucket R2 private đã có key Object Read & Write dành riêng cho bucket.
- Render có đủ `REMOTE_STORAGE_*`. Mẫu ở phụ lục A; không copy sang worker.
- Nếu nhập prompt: backend bật agent và có key/model LLM tương ứng.

Đây là checklist cần kiểm tra, không phải xác nhận hệ thống production đã được
nghiệm thu. Người vận hành worker không cần được cấp quyền quản trị Render.

## 3. Chuẩn bị máy Ubuntu

Đường chạy trong repo dùng Ubuntu 22.04, Python **3.12**, CARLA server và client
**0.9.16**. Máy cần NVIDIA driver/Vulkan hoạt động, SSD đủ chứa runtime/capture
và ít nhất **10 GiB RAM khả dụng** trước khi managed CARLA khởi động.
Tổng RAM không phải RAM đang khả dụng. Không suy luận VRAM từ tổng RAM máy.

Chạy bằng tài khoản người dùng thông thường, không chạy Unreal/CARLA dưới root.
Kiểm tra:

```bash
lsb_release -ds
nvidia-smi
free -h
df -h "$HOME"
python3.12 --version
git --version
```

Nếu thiếu công cụ cơ bản, có thể cài:

```bash
sudo apt update
sudo apt install -y git ca-certificates vulkan-tools
vulkaninfo --summary
```

`nvidia-smi` phải nhận GPU; Vulkan phải nhận thiết bị NVIDIA. CUDA hoạt động
không chứng minh Vulkan hoạt động. Nếu GPU/driver lỗi, xử lý và reboot trước
khi tiếp tục; không cài ngẫu nhiên driver hoặc chạy script thay driver tự động.

Nếu chưa có `python3.12`, cài Python 3.12 cùng module venv theo cách quản trị
máy chấp thuận. Ubuntu 22.04 không mặc định có sẵn Python 3.12; đừng thay Python
hệ thống bằng symlink. Có Python nhưng thiếu venv thì cần gói venv tương ứng
với nguồn đã cài Python.

Máy phải truy cập HTTPS tới Render và endpoint R2. Không sleep/suspend khi có job.

## 4. Clone repo và cài dependency

Các ví dụ dùng `$HOME/c4-app-t027`. Nếu chọn đường dẫn khác, sửa các bước sau
cho đồng nhất. Không copy đường dẫn của máy thành viên khác.

```bash
cd "$HOME"
git clone https://github.com/Munfond/c4-app-t027.git
cd "$HOME/c4-app-t027"
git branch --show-current
git log -1 --oneline

python3.12 -m venv .venv-worker
.venv-worker/bin/python -m pip install --upgrade pip
.venv-worker/bin/python -m pip install -r requirements-worker.txt
.venv-worker/bin/python -m pip check
```

Nếu đã clone, vào repo, kiểm tra thay đổi local và cập nhật `git pull --ff-only`
khi worker idle; không clone đè hoặc reset để xóa cấu hình của người vận hành.
Mirror và backend phải cùng phiên bản protocol/checkpoint.

Không cần activate venv: các lệnh dùng trực tiếp `.venv-worker/bin/python`.
Requirements đã có Torch và `carla==0.9.16`; bản đầu chạy inference CPU để dành
GPU cho simulator. Chưa cần cài dependency training RL.

Kiểm tra import:

```bash
.venv-worker/bin/python -c 'import carla, torch, httpx; print("Worker dependencies import OK")'
```

Nếu pip báo không có distribution/wheel CARLA phù hợp, kiểm tra Python 3.12,
kiến trúc máy và nền tảng wheel. Không đổi tên wheel khác ABI để ép cài.
Managed mode cần client trong chính venv worker; bridge client riêng chỉ dành
cho external server, không dùng với `CARLA_SERVER_EXECUTABLE`.

## 5. Chuẩn bị CARLA Linux 0.9.16

Tải gói Linux chính thức từ
[CARLA 0.9.16 release](https://github.com/carla-simulator/carla/releases/tag/0.9.16).
Không dùng bản Windows hoặc CARLA khác version. Giải nén bằng trình quản lý
archive vào thư mục do user sở hữu, ví dụ `$HOME/carla-0.9.16`.

Sau giải nén, cây thư mục cần tương ứng:

```text
~/carla-0.9.16/
  CarlaUE4.sh
  CarlaUE4/Binaries/Linux/CarlaUE4-Linux-Shipping
  ...
```

Kiểm tra binary:

```bash
test -f "$HOME/carla-0.9.16/CarlaUE4/Binaries/Linux/CarlaUE4-Linux-Shipping" \
  && echo "CARLA binary found"
test -x "$HOME/carla-0.9.16/CarlaUE4/Binaries/Linux/CarlaUE4-Linux-Shipping" \
  && echo "CARLA binary executable"
```

Nếu mất quyền executable sau khi copy, cấp lại quyền cho đúng binary thuộc user:

```bash
chmod u+x "$HOME/carla-0.9.16/CarlaUE4/Binaries/Linux/CarlaUE4-Linux-Shipping"
```

Hướng dẫn này dùng **managed mode**: không mở CARLA thủ công trước.
Worker tự mở server mới cho từng capture rồi dọn process do nó sở hữu.
Để trống các cổng 2000, 2001 và 8001; không chạy collector/worker khác cùng cổng.

```bash
ss -ltnp | grep -E ':(2000|2001|8001)\b' || true
```

Nếu có server khác, xác định chủ sở hữu và đóng đúng server trước khi chạy;
không kill toàn bộ Python hoặc process GPU của người khác.

## 6. Tạo `.env.worker`

Tại repo, copy mẫu nếu chưa có:

```bash
cd "$HOME/c4-app-t027"
cp -n .env.worker.example .env.worker
chmod 600 .env.worker
nano .env.worker
```

Nội dung mẫu dưới đây dùng `/home/USER`; **thay bằng đường dẫn thật**, không để
nguyên `USER`, `<...>` hoặc `$HOME` trong các trường đường dẫn của file dotenv.
Lấy đường dẫn thật bằng `pwd` và `echo "$HOME"` trong terminal.

```dotenv
REMOTE_API_URL=https://p027-deploy.onrender.com
WORKER_ID=gpu-worker-01
WORKER_TOKEN=<TOKEN_RIENG_CUA_MAY_NAY>

WORKER_WORK_DIR=/home/USER/c4-app-t027/data/remote-worker
LAB_DATA_ROOT=/home/USER/c4-app-t027/data/lab
EXPERIMENT_EXECUTION_MODE=local
EXPERIMENT_DEVICE=cpu
EXPERIMENT_CPU_THREADS=2
ANONYMIZER_ENABLED=false

CARLA_SERVER_EXECUTABLE=/home/USER/carla-0.9.16/CarlaUE4/Binaries/Linux/CarlaUE4-Linux-Shipping
CARLA_HOST=127.0.0.1
CARLA_PORT=2000
CARLA_TM_PORT=8001
CARLA_TIMEOUT_SECONDS=120
CARLA_BRIDGE_TIMEOUT_SECONDS=600
CARLA_MIN_AVAILABLE_MEMORY_GIB=10
```

Lưu ý:

- Backend origin không có `/api/v1`, không dùng URL Vercel.
- `WORKER_TOKEN` khớp worker ID trên Render, không phải operator code/key R2.
- Worker dùng `local` cho queue trial cô lập; Render dùng `remote` cho queue chung.
- Không đặt `CARLA_PYTHON_EXECUTABLE` hoặc `CARLA_CLIENT_PATH` trong managed mode.
- Không copy `.env` của backend sang worker. Chạy từ terminal mới nếu trước đó
  đã export biến khác; biến shell được ưu tiên hơn file `.env.worker`.
- Không chia sẻ `.env.worker`, ảnh chụp token hoặc `assignment.json` có lease.

## 7. Kiểm tra checkpoint và preflight

Hai file bắt buộc đã được track trong repo:

```bash
test -f data/lab/models/CHECKPOINTS.sha256 && echo "Checksum manifest found"
test -f data/lab/models/occupancy/variants/our_occupancy_lidar.pth \
  && echo "Occupancy checkpoint found"
```

Xác minh hash theo cấu hình worker:

```bash
.venv-worker/bin/python -c 'from dotenv import load_dotenv; load_dotenv(".env.worker"); from src.services.experiment_registry import verified_hash; print(verified_hash("occupancy_lidar"))'
```

Hash checkpoint là thông tin đối chiếu, không phải token. Không sửa manifest
checksum để bỏ qua checkpoint mismatch. Backend và worker phải dùng cùng model.

Nếu study dùng adapter `intensity_mean_experimental`, cần cùng cặp manifest/hash
ở `eval/recovery-mvp-2026-10-13/native-input-adapter.{json,sha256}` với backend.
Job raw không yêu cầu adapter; adapter khác fingerprint không nhận aligned job.

Chạy preflight:

```bash
.venv-worker/bin/python -m scripts.remote_worker --env-file .env.worker --check
```

Đọc JSON trả về: `ready` phải là `true`. Checkpoint hash phải được tạo thành công.
`--check` không nhận job, không khởi động CARLA và không kiểm tra token/backend.
Managed preflight cũng chưa chứng minh Vulkan/capture thành công. Cần lượt chạy
thật ở bước 9; không coi `ready=true` là đã nghiệm thu toàn bộ hệ thống.

## 8. Kết nối Render và giữ worker chạy

Kiểm tra backend bằng endpoint công khai:

```bash
curl --fail --show-error https://p027-deploy.onrender.com/health
```

Render Free có thể cold start. Health 200 chỉ chứng minh API đang trả lời,
không chứng minh DB, bucket hoặc token đã đúng.

Chạy worker:

```bash
cd "$HOME/c4-app-t027"
.venv-worker/bin/python -u -m scripts.remote_worker --env-file .env.worker
```

Giữ terminal mở. Khi idle, worker poll khoảng 10 giây; chưa có job có thể không
in thêm dòng nào. Xem runtime notice trên FE sau khi đăng nhập operator code.
Worker gửi heartbeat trong khi capture/inference/upload, không chỉ lúc idle.

Không chạy `scripts.experiment_worker` ở bước này: đó là worker queue local cũ,
không phải client nhận job từ Render.

## 9. Chạy thử 2 frame và đối chiếu kết quả

1. Mở [ứng dụng](https://c4-app-t027.vercel.app/lab), vào CARLA/bot.
2. Nhập **operator access code**, không nhập token worker hoặc secret R2.
3. Kiểm tra đúng worker ID online, sẵn sàng. Nếu có notice lỗi, xử lý trước.
4. Dùng cấu hình nâng cao tạo thử Town01, clear, 2 frame, 2 xe, 0 người, seed42,
   model `occupancy_lidar`, đầu vào gốc. Chỉ chạy một thí nghiệm ban đầu.
5. Terminal worker xuất hiện `Running remote trial <id>`; CARLA được mở tự động.
6. FE phải có trạng thái/tiến độ; sau inference worker upload bằng HTTPS.
7. Chờ `Uploaded remote trial <id>` và FE báo succeeded, xem ảnh/prediction/metric.
8. Quản trị viên có thể thấy object trong bucket dưới prefix `p027-jobs/`.

Sau khi trial đơn thành công, thử prompt để chạy cả study nếu backend bật LLM:

> So sánh baseline LiDAR 32 kênh 600000 điểm/s với profile half 300000 điểm/s,
> Town01 trời quang, 2 frame, 2 xe và 0 người đi bộ, seed42.
> Chấp nhận IoU giảm tối đa 0.02 so với baseline.

Study cần baseline/candidate hoàn tất rồi mới so sánh. Candidate có thể không
đạt ràng buộc; giữ baseline là kết quả hợp lệ. Prompt dùng token LLM; capture,
inference và preflight không tự gọi LLM từ worker.

Refresh trang, mở lại kết quả để kiểm tra artifact đã lưu. Có thể tắt worker idle
rồi mở lại kết quả đã completed; ảnh phải được đọc qua Render từ R2.

Không suy luận giảm điện/GPU/chi phí thực tế chỉ từ giảm số điểm/bytes.
IoU là occupancy so với nhãn proxy CARLA, không phải detection/risk ngoài thực tế.
Weather ảnh chưa chứng minh suy hao vật lý LiDAR đã được mô phỏng đầy đủ.

## 10. Dừng, log, mất mạng và upload lại

Nhấn Ctrl+C để dừng. Managed worker cố dọn simulator của trial; nếu dừng giữa
capture, kiểm tra trạng thái job/log trước chạy tiếp. Chỉ tắt máy sau khi job đã
upload thành công nếu muốn giữ kết quả trên cloud.

```text
<WORKER_WORK_DIR>/<job-id>/
  assignment.json             # Riêng tư: có lease
  trial.log
  jobs.sqlite3                # Queue cô lập của trial
  <job-id>/manifest.json
  <job-id>/capture/server.log
  <job-id>/capture/client.log  # Nếu được tạo bởi client subprocess
  <job-id>/capture/...
  <job-id>/predictions/...
  <job-id>/references/...
```

Đọc log bằng đường dẫn job thật, ví dụ:

```bash
tail -n 100 /absolute/WORKER_WORK_DIR/JOB_ID/trial.log
tail -n 100 /absolute/WORKER_WORK_DIR/JOB_ID/JOB_ID/capture/server.log
```

Không gửi assignment/token hoặc raw log chưa kiểm tra lên chat/public issue.
Heartbeat mặc định tối đa khoảng 15 giây/lần, lease mặc định 120 giây.
Mất heartbeat làm worker dừng; hết lease backend đánh lỗi/hủy study và không
tự giao lại cùng trial để recapture. Khởi động lại worker không tự resume job cũ.

Nếu trial local đã succeeded, upload lỗi nhưng remote job còn running và lease
**chưa hết**, có thể yêu cầu upload lại rõ ràng:

```bash
.venv-worker/bin/python -m scripts.remote_worker --env-file .env.worker \
  --resume /absolute/WORKER_WORK_DIR/JOB_ID
```

Resume không chạy CARLA lại. Nếu hết lease/đã hủy/failed thì bị từ chối; giữ output
để kiểm tra rồi tạo study mới khi simulator ổn định. Upload retry có giới hạn,
không phải cơ chế phục hồi qua nhiều ngày. Không sửa assignment để ép nhận lại.

`--once` chỉ chạy tối đa một trial; không dùng nếu muốn worker tiếp tục xử lý
cả study nhiều trial. Scratch và object cũ không tự được dọn; kiểm tra dung lượng
định kỳ, chỉ dọn job đã kết thúc và không cần giữ.

## 11. Bảng xử lý lỗi

| Triệu chứng | Việc cần làm |
| --- | --- |
| Không có `python3.12` / thiếu venv | Chuẩn bị Python 3.12 và venv, không thay Python hệ thống |
| `ModuleNotFoundError` | Dùng đúng `.venv-worker/bin/python`, cài lại requirements trong venv |
| Checksum mismatch / thiếu `.pth` | Kiểm tra clone/copy model và `LAB_DATA_ROOT`; không sửa hash |
| `ready=false` | Xem binary, client, driver, RAM; output preflight không phải lỗi token |
| Thiếu RAM | Cần 10 GiB khả dụng; đóng app, không tự hạ guard |
| Port đã bị chiếm | Kiểm tra 2000/2001/8001, đóng đúng simulator khác |
| Vulkan driver lỗi / CARLA crash | Kiểm tra Vulkan NVIDIA và server.log; CUDA không thay Vulkan |
| `Worker paused: ProtocolError` | Kiểm tra network và backend/log Render để biết HTTP status |
| Backend 401 | ID/token worker phải khớp Render, không dùng operator code |
| Backend 409 | Lease mất/hủy/hết hạn; không ép complete hoặc recapture tự động |
| Backend 422 | Kiểm tra version, frozen spec, checkpoint và artifact manifest |
| Backend 503 | Kiểm tra remote opt-in, migration, bucket credentials và cold start |
| FE không thấy worker | Đúng URL Render? Module remote_worker? Token? ready? |
| Aligned job chờ | Adapter fingerprint worker/backend phải khớp |
| Upload 403 | Backend kiểm tra key R2, quyền bucket, endpoint, đồng hồ hệ thống |
| File/job quá lớn | Giảm frames hoặc quản trị viên kiểm tra giới hạn artifact/quota |
| CARLA chạy nhưng không có kết quả cloud | Xem inference/upload trong trial.log; đừng chỉ dựa cửa sổ CARLA |

## 12. Chạy nền bằng systemd user sau khi test thành công

Không chuyển sang service trước khi lượt thử ở terminal thành công. Các đường dẫn
trong unit phải là tuyệt đối; thay USER bằng user thật. Tạo file
`~/.config/systemd/user/p027-worker.service`:

```ini
[Unit]
Description=P027 remote CARLA GPU worker
After=network-online.target

[Service]
WorkingDirectory=/home/USER/c4-app-t027
ExecStart=/home/USER/c4-app-t027/.venv-worker/bin/python -u -m scripts.remote_worker --env-file /home/USER/c4-app-t027/.env.worker
Restart=on-failure
RestartSec=15
TimeoutStopSec=40

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now p027-worker
systemctl --user status p027-worker
journalctl --user -u p027-worker -f
```

Nhấn Ctrl+C ở `journalctl` chỉ ngừng xem log. Muốn dừng worker:

```bash
systemctl --user stop p027-worker
```

User service mặc định phụ thuộc phiên user. Muốn chạy sau logout cần cấu hình
linger theo chính sách quản trị máy. Không chạy terminal worker song song service.
Sau khi sửa `.env.worker`, restart service khi không còn job đang chạy.

## Phụ lục A. Storage R2 chỉ cấu hình trên Render

Người vận hành Ubuntu có thể bỏ qua phần này nếu backend đã setup đúng.

```dotenv
REMOTE_STORAGE_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
REMOTE_STORAGE_REGION=auto
REMOTE_STORAGE_BUCKET=<TEN_BUCKET_PRIVATE>
REMOTE_STORAGE_ACCESS_KEY=<ACCESS_KEY_ID_MOI>
REMOTE_STORAGE_SECRET_KEY=<SECRET_ACCESS_KEY_MOI>
REMOTE_STORAGE_PREFIX=p027-jobs
```

Endpoint là URL API S3, không thêm tên bucket vào cuối. Bucket giữ private;
backend tạo presigned PUT, worker upload qua Python nên không cần bucket CORS
cho browser. FE xem artifact qua backend đã xác thực. Không cần public r2.dev.

Không dùng lại secret đã đăng trong hội thoại/public log: thu hồi credential cũ,
tạo cặp mới trong Cloudflare và cập nhật trực tiếp Render. Tài liệu không chứa
key thật và không xác nhận việc thu hồi/thay key đã hoàn tất.

## Phụ lục B. Bật LLM trên Render, không đặt trên worker

Nếu dùng OpenRouter, thêm các biến sau trong Render Environment:

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<KEY_LLM_MOI_CUA_BACKEND>
EXPERIMENT_AGENT_MODEL=openai/gpt-4o-mini
EXPERIMENT_AGENT_ENABLED=true
```

Nếu dùng OpenAI, thay provider bằng `openai`, dùng `OPENAI_API_KEY` và
`EXPERIMENT_AGENT_MODEL=gpt-4o-mini`. Chỉ cần cấu hình provider được chọn.
Không dùng `LLM_API_KEY` thay hai tên key cụ thể này; code chọn key theo
`LLM_PROVIDER`. API key phải có quyền gọi model và tài khoản đủ khả năng thanh toán.

LLM chỉ lập kế hoạch/giải thích trên backend; không chạy trong CARLA. Sau khi
lưu biến, redeploy backend. Không bật LLM vẫn thử được qua cấu hình thủ công.
Ngoài nhóm LLM vẫn phải đủ remote mode, DB migration, operator/worker token
và storage như mục 2. `/health` trả 200 không xác nhận những mục này đã xong.

## Phụ lục C. Tiêu chí bàn giao

- [ ] Dependency/client/checkpoint kiểm tra thành công.
- [ ] Managed preflight `ready=true`; không có CARLA khác chiếm cổng.
- [ ] Backend nhận đúng worker, FE hiển thị online.
- [ ] Trial Town01 2 frame chạy CARLA và inference thật thành công.
- [ ] Worker báo uploaded, object có trong R2, FE xem được artifact và metric.
- [ ] Study baseline/candidate đưa ra so sánh dựa trên kết quả đo.
- [ ] Refresh vẫn xem được kết quả, không phụ thuộc scratch trên Render.
- [ ] Biết dừng worker, xem log, xử lý hết lease và giữ kín token.

Các mục này phải thực hiện trên máy GPU/bucket thật. Unit test, checkpoint chạy
trên capture tổng hợp hoặc worker giả lập không thay thế nghiệm thu này.

Hướng dẫn kiến trúc/backend đầy đủ: [REMOTE_GPU_WORKER.vi.md](REMOTE_GPU_WORKER.vi.md).
