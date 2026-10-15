# CARLA và Active Sensing trên Linux

Môi trường chuẩn bị: Ubuntu 22.04, CARLA server/client **0.9.16**, Python 3.12.
Server render trên NVIDIA; checkpoint occupancy chạy trên CPU để dành VRAM cho
mô phỏng. Chưa cần ROS 2 hoặc build Unreal Engine từ source cho đường chạy Python SDK này.

## Máy hiện tại

Checkout: `/home/lam/WorkSpace/vinuni-buildphase/P-027-active-sensing`, branch
`codex/active-sensing-integration`. `.venv-experiments` trỏ tới runtime đã cài;
CARLA nằm trong `data/runtime/carla-0.9.16`. Các runtime, dữ liệu và `.env` không
được đưa lên Git. Các đường dẫn này là cấu hình máy hiện tại, không phải yêu cầu
đường dẫn cho mọi thành viên.

Đã cài Python client, dependencies backend/worker và dependencies RL. Lượt
BC/PPO 256 bước dùng **fixture tổng hợp** đã chạy để kiểm tra phần mềm; đây không
phải policy được huấn luyện trên CARLA. NVIDIA driver được Ubuntu chọn tự động.
Sau khi cài driver, phải reboot và kiểm tra `nvidia-smi` trước khi chạy server.

## Chạy trên máy này sau reboot

Driver NVIDIA 595 đã hoạt động, GPU RTX 2050 có 4 GB VRAM. CARLA 0.9.16
đã capture được, nhưng lần reload Town01 tiếp theo trong cùng process gây crash
native ở landscape renderer. Cấu hình máy hiện tại dùng **server mới cho mỗi
capture**, bật bằng đường dẫn `CARLA_SERVER_EXECUTABLE` trong `.env`. Worker
khởi động server, chờ client/server cùng version, capture và đóng process do nó
sở hữu. Capture dùng client subprocess cùng Python/client version để native Traffic
Manager không giữ kết nối của trial trước trong worker. Cổng đang có server khác sẽ bị từ chối; worker không tự kill server ngoài.

**Không cần mở CARLA riêng trong chế độ này.** Chạy smoke không cần API hoặc LLM:

```bash
cd /home/lam/WorkSpace/vinuni-buildphase/P-027-active-sensing
nvidia-smi
.venv-experiments/bin/python -m scripts.check_carla
.venv-experiments/bin/python -m scripts.smoke_carla
```

`check_carla` kiểm tra binary/client/checkpoint; version của server đang chạy
được kiểm tra trong mỗi capture. Smoke tạo hai frame Town01, seed 42, hai xe,
không người đi bộ và chạy checkpoint `occupancy_lidar`. Kết quả ở
`data/runtime/carla-smoke/smoke-report.json`; `status` phải là `succeeded`.
Đợi smoke hoàn tất trước khi mở worker; không chạy hai capture đồng thời trên
cùng cổng CARLA.
Log server nằm tại `<JOB_ROOT>/capture/server.log`. Server chạy Low, offscreen,
640 × 360, giới hạn render 20 FPS; checkpoint chạy CPU. Không gọi LLM.

Mỗi trial mất thêm thời gian khởi động server; đây là workaround cho máy này,
không phải cam kết simulator chạy ổn định lâu dài. Startup không nằm trong metric
`latency_model_only_ms`. Trial vẫn reset world/seed, không bỏ reload để làm metric
trông ổn hơn. Capture dùng timestep 0,05 giây, xuất frame mỗi 0,5 giây.

Máy khác có thể dùng server ngoài: bỏ `CARLA_SERVER_EXECUTABLE` khỏi `.env`,
restart worker và chạy `bash scripts/start_carla_linux.sh` trong terminal riêng.
Trên máy hiện tại, chế độ server ngoài đã gặp crash khi reload map lặp lại.
Không dùng `no_rendering_mode` nếu cần ảnh camera. Không chạy server bằng `sudo`.

## Mở backend và worker

Sau smoke thành công, dùng hai terminal riêng (managed mode tự mở CARLA khi có job):

```bash
cd /home/lam/WorkSpace/vinuni-buildphase/P-027-active-sensing
.venv-experiments/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

```bash
cd /home/lam/WorkSpace/vinuni-buildphase/P-027-active-sensing
.venv-experiments/bin/python -m scripts.experiment_worker
```

Frontend cần Node 22. Máy hiện tại có Node trong
`data/review-runtime/node-v22.23.3-linux-x64/bin`; mở terminal tiếp:

```bash
cd /home/lam/WorkSpace/vinuni-buildphase/P-027-active-sensing
export PATH="$PWD/data/review-runtime/node-v22.23.3-linux-x64/bin:$PATH"
cd frontend
npm run start -- --hostname 127.0.0.1 --port 3111
```

Production build đã có trên máy hiện tại; sau khi đổi frontend, chạy
`npm run build` trước `npm run start`. Mở `http://127.0.0.1:3111/carla` để chạy
thử nghiệm thủ công; `/agent` là study dùng LLM. `.env` hiện tắt agent LLM, nên
có thể kiểm tra capture mà không cần key. Muốn dùng LLM, đặt key riêng trong
`.env` và bật `EXPERIMENT_AGENT_ENABLED=true`, rồi restart backend/worker.

## Cài trên máy Ubuntu 22.04 khác

```bash
sudo bash scripts/setup_carla_system.sh
# Lưu công việc rồi reboot; không chạy CARLA với driver chưa hoạt động.
python3.12 -m venv .venv-experiments
.venv-experiments/bin/python -m pip install -r requirements-carla-linux.txt \
  --extra-index-url https://download.pytorch.org/whl/cpu
.venv-experiments/bin/python -m pip install -r requirements-active-sensing.txt
```

Tải gói Linux từ [CARLA 0.9.16 release](https://github.com/carla-simulator/carla/releases/tag/0.9.16)
vào `data/runtime/downloads/`, giải nén server vào `data/runtime/carla-0.9.16/`
sao cho thư mục này chứa `CarlaUE4.sh`. Kiểm tra đủ dung lượng cho cả archive và
server trước khi giải nén. Tạo `.env` từ `.env.example` nếu chưa có, giữ
`CARLA_HOST=127.0.0.1`, `CARLA_PORT=2000`, `CARLA_TM_PORT=8001`,
`CARLA_TIMEOUT_SECONDS=120`, `EXPERIMENT_DEVICE=cpu`. Nếu dùng managed mode, thêm
`CARLA_SERVER_EXECUTABLE` trỏ tới `CarlaUE4/Binaries/Linux/CarlaUE4-Linux-Shipping`
trong thư mục server. Với client 0.9.16 cùng
runtime, không đặt `CARLA_PYTHON_EXECUTABLE` hoặc `CARLA_CLIENT_PATH` legacy.

## Giới hạn của bằng chứng

- Capture smoke chứng minh kết nối, đồng bộ sensor và checkpoint chạy được;
  không chứng minh chất lượng ngoài thực tế.
- Occupancy được chấm với nhãn proxy CARLA, không phải benchmark nuScenes.
- Catalog profile RL và các checkpoint của study hiện chưa nối thành policy
  online. Muốn train RL đáng tin cần replay đo thật, chia train/val/test theo
  kịch bản, có cost/latency đo trên máy và baseline so sánh.
- Mưa/sương trong cấu hình hiện tại thay đổi hình ảnh; chưa có mô hình suy giảm
  LiDAR/radar được hiệu chuẩn. Không suy luận khả năng thích nghi sensor từ hiệu
  ứng thời tiết trên ảnh.

Tài liệu chính thức: [Ubuntu NVIDIA](https://ubuntu.com/server/docs/how-to/graphics/install-nvidia-drivers/),
[CARLA requirements](https://carla.readthedocs.io/en/0.9.16/start_quickstart/),
[rendering modes](https://carla.readthedocs.io/en/0.9.16/adv_rendering_options/).
