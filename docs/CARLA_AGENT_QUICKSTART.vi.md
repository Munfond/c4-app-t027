# Chạy CARLA + Sensor Agent: hướng dẫn cho thành viên

Mục tiêu: nhập một prompt tiếng Việt, agent sinh dữ liệu LiDAR trong CARLA với
baseline và tối đa 3 cấu hình khác, chạy checkpoint `occupancy_lidar`, so sánh
IoU/lượng dữ liệu và giải thích kết quả. Mọi lệnh chạy trong **PowerShell trên Windows**.

Ký hiệu: `<REPO>` thư mục repo, `<CARLA_ROOT>` thư mục để CARLA (ví dụ `D:\CARLA`).

## 0. Chọn phiên bản CARLA theo máy

| Máy | Phiên bản | Cách chạy client |
|---|---|---|
| GPU ≥ 8 GB VRAM | 0.9.16 | Client chạy trong cùng Python với backend |
| GPU 4–6 GB VRAM | 0.9.11 | Client chạy bằng Python 3.7 riêng, nối qua bridge |

Kiểm tra VRAM: `nvidia-smi --query-gpu=name,memory.total --format=csv`.
Client và server phải **cùng phiên bản**; preflight sẽ báo lỗi nếu lệch.

## 1. Cài môi trường backend (chung cho hai phiên bản)

Cần Python 3.12 (khớp CI) và Git.

```powershell
git clone --branch carla-agent-experiments https://github.com/AI20K-Build-Phase-Cohort-4/P-027.git
cd P-027
py -3.12 -m venv .venv-experiments
.\.venv-experiments\Scripts\python.exe -m pip install -r requirements-experiments.txt --extra-index-url https://download.pytorch.org/whl/cpu
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Model chạy trên CPU (`EXPERIMENT_DEVICE=cpu`) để dành VRAM cho CARLA render.

## 2A. CARLA 0.9.16 (máy mạnh)

1. Tải gói Windows 0.9.16 từ https://github.com/carla-simulator/carla/releases, giải nén vào `<CARLA_ROOT>\0.9.16`.
2. Cài wheel client đi kèm gói, đúng Python 3.12:
   ```powershell
   .\.venv-experiments\Scripts\python.exe -m pip install <CARLA_ROOT>\0.9.16\PythonAPI\carla\dist\carla-0.9.16-cp312-cp312-win_amd64.whl
   ```
3. Trong `.env`, **không** đặt `CARLA_PYTHON_EXECUTABLE` và `CARLA_CLIENT_PATH`.
4. `CarlaUE4.exe` nằm ở `<CARLA_ROOT>\0.9.16\CarlaUE4.exe`.

## 2B. CARLA 0.9.11 (máy 4 GB VRAM)

1. Tải gói Windows 0.9.11 từ trang releases ở trên, giải nén vào `<CARLA_ROOT>\0.9.11`.
   `CarlaUE4.exe` nằm ở `<CARLA_ROOT>\0.9.11\WindowsNoEditor\CarlaUE4.exe`.
2. Cài Python **3.7** 64-bit (https://www.python.org/downloads/release/python-379/),
   rồi tạo client riêng. Không cài torch hay backend vào Python 3.7.
   ```powershell
   $client = '<CARLA_ROOT>\client-0.9.11'
   py -3.7 -m venv "$client\venv37"
   & "$client\venv37\Scripts\python.exe" -m pip install -r requirements-carla-legacy.txt
   # Egg chứa file .pyd nên phải giải nén ra thư mục, không dùng trực tiếp file .egg
   Copy-Item '<CARLA_ROOT>\0.9.11\WindowsNoEditor\PythonAPI\carla\dist\carla-0.9.11-py3.7-win-amd64.egg' "$client\carla.zip"
   Expand-Archive "$client\carla.zip" -DestinationPath "$client\egg"
   ```
3. Thêm vào `.env` (đường dẫn dùng dấu `/`):
   ```dotenv
   CARLA_PYTHON_EXECUTABLE=<CARLA_ROOT>/client-0.9.11/venv37/Scripts/python.exe
   CARLA_CLIENT_PATH=<CARLA_ROOT>/client-0.9.11/egg
   CARLA_TIMEOUT_SECONDS=120
   ```

## 3. Cấu hình agent LLM

Trong `.env` (chỉ để trên máy, không commit, không gửi qua chat):

```dotenv
OPENAI_API_KEY=<key-cua-ban>
EXPERIMENT_AGENT_ENABLED=true
EXPERIMENT_AGENT_MODEL=gpt-4o-mini
```

Biến môi trường PowerShell cùng tên sẽ được ưu tiên hơn `.env`.

## 4. Nghiệm thu bắt buộc (không gọi LLM, không tốn tiền)

Mở CARLA trước, rồi chạy:

```powershell
& '<đường-dẫn-CarlaUE4.exe>' /Game/Carla/Maps/Town01 -quality-level=Low -windowed -ResX=960 -ResY=540 -dx11 -nosound -carla-rpc-port=2000
# đợi khoảng 30 giây cho cửa sổ hiện bản đồ
.\.venv-experiments\Scripts\python.exe -m scripts.check_carla
.\.venv-experiments\Scripts\python.exe -m scripts.test_sensor_agent --deterministic
```

Đạt khi: `check_carla` in ra `client_version` bằng `server_version`, và hai trial
(`baseline`, `half_points`) đều `succeeded`. Chạy lại bước này mỗi khi đổi máy,
đổi phiên bản CARLA hoặc pull code mới.

## 5. Chạy với prompt

**Cách 1: launcher (chỉ cần gõ prompt).** Launcher tự mở CARLA nếu chưa chạy,
chạy preflight, rồi hỏi prompt liên tục cho tới khi bạn nhập dòng trống.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_agent.ps1 -CarlaExe '<đường-dẫn-CarlaUE4.exe>'
```

Tham số: `-Python <path>` nếu venv đặt chỗ khác; `-NoWatch` để không cho camera
bám xe (chạy nhanh hơn); `-Port` nếu CARLA không dùng 2000.

**Cách 2: giao diện web `/agent`.** Xem [SENSOR_AGENT_UI.vi.md](SENSOR_AGENT_UI.vi.md)
(cần chạy backend, **một** worker và frontend).

Prompt mẫu để thử lần đầu:

```
Town01 trời quang, 4 xe, 0 người đi bộ, 10 frame. So sánh baseline với profile 450000 điểm/giây. Ngưỡng giảm IoU 0.02.
```

Kết quả nằm trong thư mục `Artifacts` được in ra: `comparison.json` (metric và
lựa chọn), `agent-summary.json` (giải thích của LLM), `dataset-index.json`
(liên kết cấu hình, frame, input và output). Ý nghĩa từng file: [PROMPT_LIDAR_DATASET.vi.md](PROMPT_LIDAR_DATASET.vi.md).

## 6. Giới hạn cần biết khi viết prompt

- Mỗi study: tối đa 3 kịch bản, 3 profile, 20 frame, 15 xe, 15 người đi bộ.
  Map Town01–05; cao tốc (`highway`) chỉ có ở Town04.
- **CARLA 0.9.11 bắt buộc 0 người đi bộ** (bản này không seed được người đi bộ, nên
  trial sẽ bị từ chối). Luôn ghi "0 người đi bộ" trong prompt.
- Mưa/sương trong CARLA chỉ đổi ảnh camera, **không làm suy giảm LiDAR**. Kết quả
  "trong mưa" gần như giống trời quang.
- Cấu hình được chọn là cấu hình rẻ nhất **trong số đã thử**, không phải tối ưu toàn cục.
  Muốn tìm sát hơn thì chạy thêm study thu hẹp khoảng.
- Chỉ checkpoint `occupancy_lidar` chạy trên dữ liệu CARLA; IoU tính trên nhãn proxy.

## 7. Xử lý sự cố

| Triệu chứng | Cách xử lý |
|---|---|
| `CARLA client/server version mismatch` | Cài đúng wheel/egg đi kèm gói server |
| `CARLA 127.0.0.1:2000 is busy with another capture` | Đã có worker hoặc CLI khác đang dùng CARLA; đợi xong hoặc tắt nó. Mỗi server chỉ một worker |
| Timeout khi load map | Đặt `CARLA_TIMEOUT_SECONDS=120`; giảm độ phân giải cửa sổ CARLA |
| `cannot seed pedestrians` | Đang dùng 0.9.11; sửa prompt về 0 người đi bộ |
| `Actor spawn shortfall` | Giảm số xe hoặc đổi map |
| `LLM provider HTTP 401/429` | Kiểm tra key, quyền dùng model và hạn mức OpenAI |
| CARLA đứng hình sau lần chạy lỗi | Lượt sau tự gỡ synchronous mode; nếu vẫn treo thì tắt và mở lại CARLA |

Log của client 0.9.11 nằm ở `<Artifacts>\<JOB_ID>\capture\client.log`.
Không chạy `manual_control.py`, `generate_traffic.py` hay một worker khác trên cùng CARLA.
