# Deploy và cập nhật server

MVP phục vụ artifact tính sẵn; không cần GPU nếu camera/perception/environment cache đầy đủ. Cấu hình dưới đây là hướng dẫn vận hành; [evidence 04/10/2026](../eval/results/report.md) chỉ kiểm thử **local**, không xác nhận VPS/domain/HTTPS hoạt động.

## AI Agent Occupancy: triển khai riêng với worker

Mục 04 `/experiments` không cần CARLA. Ngoài FE/API cần worker PyTorch,
ba checkpoint occupancy, raw nuScenes-mini và cùng EXPERIMENT_ROOT có quyền ghi.
Bundle perception của Lab không thay raw dataset hoặc worker. Hướng dẫn Compose
Lab bên dưới không tự cài inference dependencies hay khởi động worker agent.

API production mặc định tắt experiments. Chỉ bật
`EXPERIMENT_API_ENABLED_IN_PRODUCTION` khi đã kiểm soát truy cập/quota/budget.
Key LLM ở backend, không truyền sang FE. Phiên tạm không thay thế xác thực.
Camera preview agent đọc raw ảnh, không qua anonymizer Lab; không mở raw cho công chúng.

API/worker phải truy cập cùng vùng lưu tạm. SQLite/lease hiện phù hợp deployment
có shared local storage, chưa tự scale thành các replica có filesystem riêng.
Redeploy cần restart cả API/worker; phiên hết hạn được dọn khi khởi động lại.
Chi tiết: [runbook agent](REPLAY_SENSOR_AGENT.vi.md).

## Windows VPS · native processes

Dùng Python 3.12, Node 22.x và Caddy; backend/frontend setup theo [README](../README.md). Data đặt ngoài checkout, ví dụ `C:/apps/lab`, `C:/apps/nuscenes`. Root `.env` override roots; frontend `.env.local` dùng `API_INTERNAL_URL=http://127.0.0.1:8000` trước khi build.

Caddy native cần **literal domain và loopback upstream**. `deploy/Caddyfile` trong repo dùng Compose env/service names; đừng chạy nguyên trạng nếu chưa chuyển cấu hình. Giữ native file riêng, ví dụ `C:/caddy/Caddyfile`, để pull không ghi đè local config:

```caddyfile
c4-app-t027.duckdns.org {
    # Nếu dùng judge auth: đặt basic_auth và user/hash BÊN TRONG site block này.
    request_body {
        max_size 12MB
    }
    handle /lab/* {
        respond "Legacy media unavailable" 404
    }
    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle /health {
        reverse_proxy 127.0.0.1:8000
    }
    handle {
        reverse_proxy 127.0.0.1:3000
    }
}
```

`/lab` là route trang; `/lab/*` chặn media legacy chưa review. Judge auth dùng hash tạo bằng `caddy hash-password`, giữ ngoài Git; `basic_auth` không đặt trong global options. DNS phải trỏ IP public VPS; mở TCP 80/443 ở firewall/provider. Backend/frontend bind loopback.

```powershell
& 'C:/caddy/caddy.exe' validate --config 'C:/caddy/Caddyfile'
& 'C:/caddy/caddy.exe' run --config 'C:/caddy/Caddyfile'
```

### Mỗi lần merge / cập nhật

1. Chỉ cập nhật sau merge và kiểm tra CI của commit đích. Nếu `git status` có file sửa, bảo toàn cấu hình và thay đổi đó trước; không reset sạch bừa.
2. Dừng **đúng tiến trình frontend/backend đang phục vụ** bằng terminal/service quản lý. Giữ Caddy và runner CI chạy. Không kill mọi node/python vì có thể dừng runner hoặc công việc khác.
3. Repo root:

```powershell
Set-Location 'C:/apps/P-027'
git status --short --branch
git fetch origin
git switch main
git pull --ff-only origin main
git rev-parse HEAD
.\.venv-lab\Scripts\python.exe -m pip install -r requirements.txt
Set-Location frontend
npm ci
npm run build -- --webpack
```

4. Backend, terminal/service riêng:

```powershell
Set-Location 'C:/apps/P-027'
.\.venv-lab\Scripts\python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

5. Frontend, terminal/service riêng:

```powershell
Set-Location 'C:/apps/P-027/frontend'
npm run start -- --hostname 127.0.0.1 --port 3000
```

6. Kiểm tra local trước domain:

```powershell
Invoke-WebRequest 'http://127.0.0.1:3000/lab' -UseBasicParsing | Select-Object StatusCode
Invoke-RestMethod 'http://127.0.0.1:8000/health'
Invoke-RestMethod 'http://127.0.0.1:3000/api/v1/lab/perception/tasks'
Get-NetTCPConnection -State Listen -LocalPort 80,443,3000,8000 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
```

Kiểm tra HTTPS từ máy ngoài mạng, đăng nhập nếu đã cấu hình judge auth, rồi chạy lại manual cases. Nếu 3000/8000 trả 200 nhưng không có listener 80/443, kiểm tra Caddy trước. Nếu listener có nhưng domain lỗi, kiểm tra DNS/firewall/certificate log. Cập nhật artifact riêng khi code yêu cầu output mới; Git pull không mang dataset/cache lớn.

## Linux/Docker Compose · phương án khác

`deploy/compose.yml`: backend Python 3.12 + frontend standalone + Caddy; chỉ gateway expose 80/443, data bind mount read-only. `LAB_VOLUME` chứa `lab/`, `nuscenes/`, `sim/`.

```powershell
# Repo root, tạo file một lần và điền cấu hình trước khi chạy
if (-not (Test-Path -LiteralPath 'deploy/.env')) { Copy-Item 'deploy/.env.example' 'deploy/.env' }
docker run --rm -it caddy:2-alpine caddy hash-password
# Điền LAB_DOMAIN, LAB_VOLUME, JUDGE_USER, JUDGE_PASSWORD_HASH vào deploy/.env
docker compose --env-file deploy/.env -f deploy/compose.yml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yml up -d --build
docker compose --env-file deploy/.env -f deploy/compose.yml ps
```

Cache phải chuẩn bị trước vì data mount read-only và anonymizer web mặc định tắt. Caddy được Compose cấp env; không nhầm `deploy/.env` với root `.env` hoặc frontend `.env.local`. Lưu SHA/release trước để rollback bằng checkout/build lại; không xóa data volume.

## CI runner và bàn giao

Workflow `.github/workflows/ci.yml` dùng labels `self-hosted, Windows, X64, team-27`, backend lint/pytest và frontend lint/build. Một runner có thể chạy hai job lần lượt. Runner không tự tạo domain hay deploy; hiện chưa có workflow tự cập nhật server. Không dùng runner PR chung với production data/secrets.

Trước bàn giao: review processed cameras, kiểm tra cache/task coverage và thao tác UI, thử restart/rollback, kiểm tra URL từ bên ngoài, lưu release SHA và video dự phòng. Chưa đo concurrent users, p95/FPS hay uptime production trong đợt evidence local này.
