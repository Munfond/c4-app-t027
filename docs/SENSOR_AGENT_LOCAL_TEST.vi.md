# Test sensor agent trên máy GPU của nhóm

Ngày 06/10/2026. Code đã kiểm thử local; chưa nghiệm thu CARLA trên RTX 3050 hoặc
gọi OpenAI thật. Đây là bản để bạn của anh chạy acceptance test và ghi kết quả.

Agent gọi `create_sensor_study` tạo job → worker chạy CARLA/inference → code lần
lượt enqueue trials → agent gọi `read_sensor_study`, `compare_sensor_configs` rồi giải thích.
Planner `/plan` cũ vẫn chỉ draft. Giao diện hiện chưa có form sensor study; dùng CLI/API dưới đây.

## 1. Clone và dependency

Sau khi anh push các thay đổi này:

```powershell
git clone --branch carla-agent-experiments https://github.com/AI20K-Build-Phase-Cohort-4/P-027.git
cd P-027
py -3.12 -m venv .venv-experiments
.\.venv-experiments\Scripts\python.exe -m pip install -r requirements-experiments.txt
```

Cần quyền truy cập repo nếu private. Checkpoints occupancy/flow được Git track;
không cần raw nuScenes để thử CARLA. Preflight xác minh checkpoint SHA256.

## 2. CARLA/GPU

Giải nén CARLA Windows 0.9.16 vào thư mục riêng, ví dụ `D:\CARLA\0.9.16`.
Cài wheel **đi kèm đúng gói server**, đúng Python và Windows:

```powershell
.\.venv-experiments\Scripts\python.exe -m pip install D:\CARLA\0.9.16\PythonAPI\carla\dist\carla-0.9.16-cp312-cp312-win_amd64.whl
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
```

`memory.total` là VRAM thực, khác RAM hệ thống. Chọn executable CARLA chạy bằng
NVIDIA trong Windows Graphics settings nếu máy có cả Intel/NVIDIA. Bản Latest
có thể trả version dạng commit hash; client/server phải khớp, không chỉ cùng tên 0.9.16.
Lỗi `0xc0000135` có thể do thiếu DLL; DirectX legacy chính thức:
https://www.microsoft.com/en-us/download/details.aspx?id=8109 .

Sửa đường dẫn theo máy, khởi động server riêng ở Low/off-screen:

```powershell
Start-Process -FilePath D:\CARLA\0.9.16\CarlaUE4.exe -WorkingDirectory D:\CARLA\0.9.16 -ArgumentList '/Game/Carla/Maps/Town01','-RenderOffScreen','-quality-level=Low','-carla-rpc-port=2000' -WindowStyle Hidden
```

Không chạy manual_control/generate_traffic hoặc app khác cùng world. Runner có thể
reload map, đổi settings/weather, spawn actors và ticks. Off-screen vẫn render;
không bật no-rendering vì camera sẽ không có dữ liệu.

## 3. Cấu hình

Nếu chưa có `.env`, copy `.env.example`; không ghi đè cấu hình/key đang có.

```powershell
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item '.env.example' '.env' }
notepad .env
```

```dotenv
APP_ENV=development
CARLA_HOST=127.0.0.1
CARLA_PORT=2000
CARLA_TM_PORT=8001
CARLA_TIMEOUT_SECONDS=120
EXPERIMENT_DEVICE=cpu
EXPERIMENT_CPU_THREADS=2
EXPERIMENT_AGENT_ENABLED=false
```

Giữ inference CPU trong lượt đầu để ưu tiên VRAM cho simulator. CUDA cho model
là tùy chọn sau nghiệm thu; không cần train lại checkpoint cho smoke test.

## 4. Test không gọi LLM

```powershell
.\.venv-experiments\Scripts\python.exe -m scripts.check_carla
.\.venv-experiments\Scripts\python.exe -m scripts.test_sensor_agent --deterministic
```

Preflight chỉ đọc kết nối/metadata, không tạo actor/tick. Lệnh thứ hai tạo queue
riêng `data/experiments/sensor-agent-tests/<run-id>`, chạy baseline + profile
nửa số điểm: Town01, 2 xe khác, 0 người, 2 frames. Đây là pipeline test, chưa agent LLM.
CLI tự chạy worker từng job; không mở backend/frontend hay worker riêng để chạy lệnh này.
Script in đường dẫn artifacts/study ID; queue riêng tránh xử lý job có sẵn của người khác.

## 5. Test agent thật

Đặt key riêng trong `.env`, không gửi qua chat hay commit:

```dotenv
OPENAI_API_KEY=<key project OpenAI có quyền và billing>
EXPERIMENT_AGENT_ENABLED=true
EXPERIMENT_AGENT_MODEL=gpt-4o-mini
```

Process mới đọc cấu hình. Lệnh sau có thể phát API request tính phí:

```powershell
.\.venv-experiments\Scripts\python.exe -m scripts.test_sensor_agent --message "Thử LiDAR Town01 trời quang ít xe, 2 frame; so sánh baseline với 300000 và 150000 điểm/giây, IoU giảm tối đa 0.02"
```

Thông số hỗ trợ: channels, points_per_second, range_m, upper_fov, lower_fov, mount_z, pitch.
Tối đa 3 môi trường × (baseline + 3 profiles) = 12 trials; mỗi trial <=20 frames,
15 xe khác và 15 người. Sensor input quay20Hz/tick0.05s; cadence model0.5s giữ nguyên.
Chưa tối ưu radar/camera hoặc đổi sensor giữa chừng trong một trial.

Luồng bình thường có 4 lượt LLM: tạo study, đọc, so sánh, giải thích. Không polling
bằng LLM, không tự retry provider. Summary thành công được cache. Bảng selection
do Python tính; LLM không được quyết định thay số liệu. Chưa eval chất lượng với API thật.

## 6. Artifacts và tiêu chí nghiệm thu

- `study-start.json`: cấu hình, tool tạo study, model/usage.
- `<job-id>/capture`: RGB, NPZ sensor/features, geometry và manifest.
- `<job-id>/predictions/occupancy_lidar`: preview BEV 200×200.
- `comparison.json`: metrics/byte rate theo môi trường và profile.
- `agent-summary.json`: kết quả có cấu trúc, lời giải thích và hai tool đọc/so sánh.
- `jobs.sqlite3`: study/jobs để đọc lại/resume.

Nghiệm thu kỹ thuật: preflight thành công, trials succeeded, ảnh/point cloud có dữ liệu,
sensor specs trong manifest đúng yêu cầu, prediction đúng shape. Tool tạo study nằm
trong `study-start.json` → `metadata.tool`; hai tool đọc/so sánh nằm trong
`agent-summary.json` → `tool_trace` (tổng cộng 3 tool, ở hai file).
Chưa thể coi hai frames là benchmark hoặc kết luận cấu hình sản phẩm.

Selection **provisional**: byte rate thấp nhất trong ngưỡng IoU giảm so với baseline,
chỉ khi reference hash (labels/mask/ego pose) khớp. Mismatch loại trial; baseline
lỗi/không có chất lượng thì selected=null. Có thể chỉ chọn baseline; không tắt guard.
Semantic LiDAR tham chiếu giữ cấu hình/mount cố định độc lập input, nhưng nhãn vẫn
là height/actor-footprint proxy trên observed cells, chưa GT occupancy đầy đủ.
Byte rate là raw LiDAR payload ước tính từ tick capture, không điện/tiền hay overhead mạng.
BEV cố định có thể giữ model latency gần như cũ. Weather đổi RGB, chưa kiểm chứng
suy giảm LiDAR vật lý; autopilot/spawn chưa là tuyến cao tốc đã xác minh.

## 7. Resume/API

Planning đã thành công thì dùng root/study ID để không tạo lại study bằng LLM:

```powershell
.\.venv-experiments\Scripts\python.exe -m scripts.test_sensor_agent --root data/experiments/sensor-agent-tests/<run-id> --study-id <study-id>
```

Thêm `--deterministic` để không gọi LLM tổng hợp. Study cancelled không được resume;
tạo lượt mới. Timeout mặc định1800s, mỗi worker <=600s; kill worker có thể bỏ qua cleanup,
cần kiểm tra/restart server trước retry. Lease stale thành failed, không tự resume capture dở.

Nếu dùng backend, chạy một worker riêng cùng EXPERIMENT_ROOT; không đồng thời dùng CLI
inline worker hoặc nhiều store cùng CARLA world. Routes ở Swagger `/docs`:

- POST `/api/v1/experiments/sensor-agent/start`, body `{"message":"..."}`.
- GET `/api/v1/experiments/sensor-agent/<id>`: poll không gọi LLM.
- POST `/api/v1/experiments/sensor-agent/<id>/advance`: enqueue trial tiếp theo.
- POST `/api/v1/experiments/sensor-agent/<id>/cancel`: hủy.
- POST `/api/v1/experiments/sensor-agent/<id>/summarize`: gọi tool đọc/so sánh, giải thích.

GET không tự advance; CLI thực hiện advance. Summary chỉ sau completed. Production API vẫn opt-in.

### Ví dụ chạy API bằng PowerShell

Dùng cách này khi muốn test HTTP thay vì CLI. Thêm vào `.env` một root riêng:

```dotenv
EXPERIMENT_ROOT=C:/apps/p027-sensor-api-test
```

Mở hai terminal tại thư mục repo, cùng đọc `.env` đó:

```powershell
# Terminal 1: backend
.\.venv-experiments\Scripts\python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2: một worker duy nhất; CARLA đã khởi động
.\.venv-experiments\Scripts\python.exe -m scripts.experiment_worker
```

Terminal 3 tạo study và theo dõi; yêu cầu start này gọi LLM:

```powershell
$sensorApi = 'http://127.0.0.1:8000/api/v1/experiments/sensor-agent'
$sensorBody = @{ message = 'Town01 trời quang, 2 xe, 0 người, 2 frames; thử LiDAR 300000 điểm/giây' } | ConvertTo-Json
$sensorStudy = Invoke-RestMethod -Method Post -Uri "$sensorApi/start" -ContentType 'application/json' -Body ([System.Text.Encoding]::UTF8.GetBytes($sensorBody))
$sensorStudyId = $sensorStudy.id
$sensorStudyId
```

Chạy hai lệnh sau khi muốn cập nhật trạng thái. `advance` chỉ enqueue thêm trial
khi trial trước đã kết thúc; gọi lại trong lúc đang chạy không tạo job trùng:

```powershell
$sensorStudy = Invoke-RestMethod -Method Post -Uri "$sensorApi/$sensorStudyId/advance"
$sensorStudy = Invoke-RestMethod -Uri "$sensorApi/$sensorStudyId"
$sensorStudy.jobs | Format-Table profile,status,stage,error
$sensorStudy.status
```

Lặp lại cập nhật cho tới `completed`, rồi tổng hợp (gọi LLM):

```powershell
$sensorSummary = Invoke-RestMethod -Method Post -Uri "$sensorApi/$sensorStudyId/summarize"
$sensorSummary.explanation
$sensorSummary.comparison.environments | ConvertTo-Json -Depth 20
```

Hủy study đang chạy:

```powershell
Invoke-RestMethod -Method Post -Uri "$sensorApi/$sensorStudyId/cancel"
```

## 8. Xử lý lỗi thường gặp

| Hiện tượng | Kiểm tra / xử lý |
|---|---|
| `No module named carla` hoặc pip từ chối wheel | Dùng đúng executable Python trong venv; wheel cần khớp Python (`cp312` cho 3.12), hệ điều hành và gói server. |
| Client/server version mismatch | Cài wheel đi kèm chính gói CARLA đang chạy; kiểm tra không kết nối nhầm server khác trên port 2000. |
| Timeout kết nối, preflight thất bại | Xác nhận server còn chạy và đã load map; kiểm tra `CARLA_HOST`, port và firewall. Chưa chạy agent khi preflight chưa thành công. |
| Server tắt ngay hoặc thiếu DLL | Kiểm tra log trong thư mục `CarlaUE4/Saved/Logs` của gói CARLA; kiểm tra dependency và GPU được chọn theo mục 2. |
| Out of memory hoặc thiếu sensor frame | Giữ Low/off-screen, inference CPU, bắt đầu 2 frames/2 xe/0 người; đóng ứng dụng chiếm GPU, kiểm tra VRAM bằng `nvidia-smi`. `CARLA_TIMEOUT_SECONDS=120` chỉ tăng thời gian chờ, không bổ sung VRAM. |
| Agent disabled / API trả 503 | Kiểm tra `EXPERIMENT_AGENT_ENABLED=true`, key có giá trị, khởi động lại process để đọc `.env` mới. Trong production cần opt-in API như cấu hình dự án. |
| Provider HTTP 401 / 429 / 403 / 404 | Kiểm tra lần lượt key; quota/rate limit/billing; quyền truy cập; model được cấu hình. Code không tự retry; nếu study đã tạo thì dùng resume thay vì tạo study mới. |
| Checkpoint thiếu hoặc SHA256 sai | Kiểm tra checkout có các file `.pth` đã track và `CHECKPOINTS.sha256`; bỏ override `LAB_DATA_ROOT` trỏ nhầm. Không sửa hash chỉ để bỏ qua lỗi. |
| `reference_matches_baseline=false` | Trial bị loại khỏi lựa chọn chất lượng. Giữ một world riêng và cùng seed/route; không coi cấu hình đó là đã tốt hơn baseline. |
| `provisional_selected=baseline` hoặc `null` | Đọc trạng thái từng trial, IoU và reference; đây có thể là kết quả hợp lệ, không phải lỗi LLM. |

Để gửi kết quả test cho nhóm: cung cấp tên GPU/VRAM thực, Python/client/server version,
lệnh đã chạy, lỗi console và các file `study-start.json`, `comparison.json`,
`agent-summary.json` nếu có. Lỗi worker nằm trong `jobs[].error` của study/API;
không gửi `.env` hoặc API key. Khi study lỗi trước bước xuất báo cáo, đọc API nếu
dùng backend, hoặc xem `jobs.sqlite3` trong root được CLI in ra.
