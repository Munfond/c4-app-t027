# CARLA 0.9.11 và sensor agent trên máy Windows 4 GB VRAM

Đã kiểm thử trên máy Windows 4 GB VRAM ngày 06/10/2026: client/server 0.9.11, backend Python
3.13.15, client Python 3.7.9. Baseline và half_points đều capture/inference thành
công (2 frame/trial), reference hash khớp. IoU occupancy proxy lần lượt 0.3321
và 0.2958; giảm 0.0363 vượt ngưỡng 0.02 nên lựa chọn tạm thời là baseline.
Báo cáo lưu trên máy chạy, không đưa vào repo.
24 tests cho experiments/bridge/sensor agent và Ruff đã qua. Ngày 07/10/2026 đã
chạy thêm LLM thật với ba cấu hình 600k/300k/150k: cả ba trials succeeded, reference
hash khớp và agent đã lưu thuyết minh. Xem `eval/evidence/2026-10-07-carla-agent/README.md`.

Hướng dẫn từng bước cho thành viên mới: [CARLA_AGENT_QUICKSTART.vi.md](CARLA_AGENT_QUICKSTART.vi.md).
Ký hiệu: `<REPO>` thư mục repo, `<VENV>` venv backend, `<CARLA_ROOT>` thư mục chứa CARLA.

Backend/model/agent dùng Python 3.13 trong `<VENV>`.
Client CARLA dùng Python 3.7.9 riêng trong `<CARLA_ROOT>\client-0.9.11\python`.
Client đọc cấu hình từ worker, capture và xuất NPZ/PNG; worker đọc lại để chạy
checkpoint và chấm điểm. Không cài Torch hoặc dependency backend vào Python 3.7.

1. Mở PowerShell tại thư mục repo:

   ```powershell
   Set-Location -LiteralPath '<REPO>'
   ```

2. Tạo môi trường backend bằng Python mới (ít nhất 3.11), không dùng Python client 3.7:

   ```powershell
   py -3.13 -m venv <VENV>
   <VENV>\Scripts\python.exe -m pip install -r requirements-experiments.txt --extra-index-url https://download.pytorch.org/whl/cpu
   ```

   Client portable gồm Python embedded 3.7.9 chính thức, egg `carla-0.9.11-py3.7-win-amd64.egg`
   được giải nén vào `<CARLA_ROOT>\client-0.9.11\egg`, và wheel NumPy 1.21.6
   cho CPython 3.7/Windows x64 được giải nén vào cùng thư mục client. NumPy có
   SHA-256 được đối chiếu PyPI. Dependency riêng được ghi trong
   `requirements-carla-legacy.txt`. Có thể dùng một venv Python 3.7 bình thường
   thay portable; trỏ `CARLA_PYTHON_EXECUTABLE` đến đúng executable đó.

3. Khởi động đúng một CARLA server 0.9.11:

   ```powershell
   & '<CARLA_ROOT>\0.9.11\WindowsNoEditor\CarlaUE4.exe' /Game/Carla/Maps/Town01 -quality-level=Low -windowed -ResX=960 -ResY=540 -dx11 -nosound -carla-rpc-port=2000
   ```

   Nếu server đang chạy trên port 2000 thì bỏ qua lệnh này. Không chạy đồng thời
   bản 0.9.15 hoặc script traffic/manual_control trên cùng world. Worker sẽ tự
   load Town01. Giữ model trên CPU để dành VRAM cho render.

4. Cấu hình `.env` ở gốc repo (không ghi đè key đang có):

   ```dotenv
   CARLA_HOST=127.0.0.1
   CARLA_PORT=2000
   CARLA_TM_PORT=8001
   CARLA_TIMEOUT_SECONDS=120
   CARLA_PYTHON_EXECUTABLE=<CARLA_ROOT>/client-0.9.11/python/python.exe
   CARLA_CLIENT_PATH=<CARLA_ROOT>/client-0.9.11/egg
   CARLA_BRIDGE_TIMEOUT_SECONDS=600
   EXPERIMENT_DEVICE=cpu
   EXPERIMENT_CPU_THREADS=2
   EXPERIMENT_AGENT_ENABLED=false
   EXPERIMENT_AGENT_MODEL=gpt-4o-mini
   ```

   Những đường dẫn này là đường dẫn Windows. Chạy backend/worker bằng Python
   Windows trong PowerShell, kể cả khi repo nằm trong WSL. Không chạy Python
   Linux với executable client Windows ở cấu hình này.

5. Kiểm tra server/client và chạy study không cần LLM/key:

   ```powershell
   <VENV>\Scripts\python.exe -m scripts.check_carla
   <VENV>\Scripts\python.exe -m scripts.test_sensor_agent --deterministic
   ```

   Study chạy baseline 600.000 điểm/giây và profile 300.000 điểm/giây, Town01,
   2 xe, 0 người đi bộ, 2 frame. Hai trials phải `succeeded`; kiểm tra
   `comparison.json` trong thư mục Artifacts CLI in ra. Khác reference hash sẽ
   loại profile khỏi lựa chọn; không bỏ guard để ép kết luận cấu hình tốt hơn.

6. Bật agent LLM bằng cách sửa `.env`:

   ```dotenv
   OPENAI_API_KEY=<dien-key-cua-ban-tai-may>
   EXPERIMENT_AGENT_ENABLED=true
   EXPERIMENT_AGENT_MODEL=gpt-4o-mini
   ```

   Điền key thật vào file local, không gửi vào chat hoặc commit Git. Agent dùng
   key API OpenAI; tài khoản API cần có quyền sử dụng model và hạn mức phù hợp.
   Biến môi trường PowerShell cùng tên sẽ ưu tiên hơn `.env`; nếu thay cấu hình
   mà không có tác dụng, kiểm tra các biến môi trường cũ và khởi động lại worker/API.
   Nếu `.env` đã có key đúng, giữ nguyên key đó và chỉ bật agent.

7. Chạy agent qua CLI (CLI tự điều phối worker, không cần thêm worker thứ hai):

   ```powershell
   <VENV>\Scripts\python.exe -m scripts.test_sensor_agent --message "Thử LiDAR Town01 trời quang, 2 xe, 0 người đi bộ, 2 frame; so sánh baseline với 300000 điểm/giây, IoU giảm tối đa 0.02"
   ```

   Agent tạo study → worker capture/inference → code so sánh → agent đọc tools
   và giải thích. Kết quả có `comparison.json`, `agent-summary.json`, capture
   và prediction. Có thể dùng API nếu cần; xem `docs/SENSOR_AGENT_LOCAL_TEST.vi.md`.

CARLA 0.9.11 không có `set_pedestrians_seed`, nên nhánh từ chối capture có
`pedestrians>0` khi client thiếu API này, để tránh so sánh trials không kiểm soát
được seed. Luôn ghi rõ 0 người đi bộ trong yêu cầu agent. Chỉ `occupancy_lidar`
được hỗ trợ trên CARLA; camera để kiểm tra bằng mắt. Weather RGB chưa chứng minh
suy giảm vật lý của LiDAR. Nhãn occupancy vẫn là proxy, kết quả lựa chọn tạm thời.

Nếu job bị hủy hoặc timeout, worker dừng tiến trình client. Lượt capture sau tự
tắt synchronous mode bị bỏ lại rồi load lại map (xóa actors cũ). Mỗi CARLA
server chỉ cho một capture tại một thời điểm; process thứ hai báo lỗi `busy`.
Nếu server vẫn treo, khởi động lại CARLA. Log của client nằm
ở `<experiment-id>/capture/client.log`.

Để nhìn xe chạy trong cửa sổ CARLA và thu dữ liệu cho model, mở cửa sổ CARLA rồi
chạy trong PowerShell tại repo:

```powershell
<VENV>\Scripts\python.exe -m scripts.watch_carla --frames 81 --vehicles 4
```

Góc nhìn bám theo xe ego, tick được điều tiết theo thời gian thực. Lệnh thu 81
frame (khoảng 40 giây mô phỏng), chạy occupancy_lidar trên CPU và lưu kết quả
vào đường dẫn Artifacts được in ra. Lượt này không gọi LLM. Sau capture, worker
dọn actors. Có thể chạy lại để xem và thu một lượt mới.
