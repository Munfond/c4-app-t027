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

## Khởi động sau reboot

Terminal 1, giữ mở trong lúc dùng simulator:

```bash
cd /home/lam/WorkSpace/vinuni-buildphase/P-027-active-sensing
nvidia-smi
bash scripts/start_carla_linux.sh
```

Launcher dùng `-RenderOffScreen` và chất lượng Low để giảm tải, giữ camera RGB
hoạt động. Không dùng `no_rendering_mode` nếu cần ảnh camera. Máy ít VRAM có thể
vẫn không đủ chạy CARLA 0.9.16; chỉ kết luận sau khi kiểm tra GPU và capture thật.
Không chạy server bằng `sudo`. Khi đổi cổng, phải đổi cả `.env` và cờ launcher.

Terminal 2, đợi server load map rồi kiểm tra:

```bash
cd /home/lam/WorkSpace/vinuni-buildphase/P-027-active-sensing
.venv-experiments/bin/python -m scripts.check_carla
.venv-experiments/bin/python -m scripts.smoke_carla
```

`check_carla` phải báo hai version `0.9.16`. Smoke tạo hai frame Town01, seed 42,
hai xe, không người đi bộ, chạy checkpoint `occupancy_lidar`, không gọi LLM.
Kết quả ở `data/runtime/carla-smoke/smoke-report.json`; `status` phải là
`succeeded`. Chỉ chạy một capture/worker trên cùng server; dừng worker khác trước
khi chạy smoke. Nếu GPU báo lỗi hoặc capture thất bại, giữ log để xử lý, không
coi cài package thành công là mô phỏng đã hoạt động.

## Mở backend và worker

Sau smoke thành công, dùng hai terminal riêng:

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
`CARLA_TIMEOUT_SECONDS=120`, `EXPERIMENT_DEVICE=cpu`. Với client 0.9.16 cùng
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
