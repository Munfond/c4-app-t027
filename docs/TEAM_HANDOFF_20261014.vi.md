# Bàn giao MVP cho team

> Remote worker mới: [Render + máy GPU cá nhân](REMOTE_GPU_WORKER.vi.md).
> Chỉ bật sau khi tạo schema queue PostgreSQL, private bucket và operator/worker
> credentials. Không cần thay deployment playback hiện tại nếu chưa chạy job mới.

## 1. Repo và deploy phải cùng phiên bản

Sau khi PR tích hợp được merge, kiểm tra Vercel **và** Render đều deploy đúng commit trên `main`. Vercel xanh không đồng nghĩa backend đã cập nhật.

- Vercel: Root Directory `frontend`, Node 22; `API_INTERNAL_URL=https://p027-deploy.onrender.com`. Đổi URL thì redeploy để rewrites được build lại.
- Render: Dockerfile root repo; giữ `APP_ENV=production`, `DATABASE_URL` trong secret của backend. Không ghi connection string hoặc key vào source/frontend.
- Docker tự cài hai gói trong `deploy/artifacts`: 324 output perception cho 81 frame (có Seg3D), và bản ghi đối chứng/PPO 20 frame.
- Các env override `LAB_DATA_ROOT` hoặc `NATIVE_*_ROOT` phải trỏ tới assets thực tế. Volume ngoài có thể che dữ liệu đã cài trong image.

## 2. Ba mức chức năng

| Mức | Dùng được khi nào? | Cần gì? |
| --- | --- | --- |
| Lab / Compare / Benchmarks | Có catalog, prediction và media tương ứng | Backend CPU + Vercel; processed camera/point cloud qua DB hoặc cache của đội |
| Xem PPO/CARLA đã ghi | Docker build cài native bundle; GET evidence hoạt động | Không cần CARLA, Torch, runner hoặc key LLM |
| Tạo thí nghiệm / hội thoại | Backend được opt-in với kiểm soát truy cập và worker/storage phù hợp | LLM key trên backend; capture live cần Linux GPU/RAM/runtime CARLA |

Không bật `EXPERIMENT_API_ENABLED_IN_PRODUCTION` chỉ để xem PPO: API `/api/v1/evidence/*` đã tách riêng đường đọc. Giữ thao tác tạo job/LLM khóa nếu server chưa đủ điều kiện. Render free không được trình bày như máy mô phỏng CARLA live.

## 3. Kiểm tra sau deploy

```bash
curl -f https://p027-deploy.onrender.com/health
curl -f https://p027-deploy.onrender.com/api/v1/lab/perception/tasks
curl -f https://p027-deploy.onrender.com/api/v1/evidence/capabilities
curl -f https://p027-deploy.onrender.com/api/v1/evidence/native-online
curl -f https://p027-deploy.onrender.com/api/v1/evidence/native-rl
```

Mong đợi: health OK; bốn task `seg3d/occupancy/flow/radar` đủ 81 frame; capabilities `playback_only=true`, `interactive_enabled=false`; native-online có `full20-retry1` và `ppo20`; native-rl `ready=true`. Nếu 404, kiểm tra commit/backend deploy trước. Nếu 503 integrity, giữ log và kiểm tra root/hash, không sửa số đo hoặc bỏ guard.

Mở domain Vercel trên máy khác: Camera 360°, LiDAR/Radar, Seg3D, đổi model Compare, Benchmarks và Agent→CARLA→PPO 20 frame→Play→Reference. Ảnh camera nuScenes và environment vẫn phụ thuộc DB/cache của đội; native bundle chỉ chứa ảnh simulator.

## 4. Key LLM và runner

OpenRouter: `LLM_PROVIDER=openrouter`, `OPENROUTER_API_KEY` trong secret backend, `EXPERIMENT_AGENT_MODEL=openai/gpt-4o-mini`, `EXPERIMENT_AGENT_ENABLED=true`. Chỉ bật cho môi trường interactive đã được kiểm soát. Lời hỏi/schema/metadata/evidence được gửi tới provider; ảnh/point cloud/trọng số không được gửi theo luồng này. Key local không tự lên Render sau merge.

Runner GitHub Windows cần đúng labels `self-hosted, Windows, X64, team-27`. Khi offline, CI chờ; kết quả kiểm thử local lưu trong báo cáo nghiệm thu. Merge tuân theo rule repo, không bypass check bắt buộc. Runner CI không phải CARLA worker và không tự cấu hình Render/Vercel.

## 5. Nội dung trình bày và giới hạn

Dùng [hướng dẫn đầy đủ](MVP_USER_GUIDE.vi.md), [bảng nghiệm thu](MVP_ACCEPTANCE_20261014.vi.md) và [sơ đồ kiến trúc](../ARCHITECTURE.md). Cặp PPO 20 frame không cải thiện baseline; study thủ công mới giữ baseline vì giảm điểm quá nhiều làm giảm IoU. Town03 còn crash trên runtime laptop này; demo dùng bản ghi Town01 đã kiểm định. Không gọi preview RGB mưa/sương mù là bằng chứng robust sensor vật lý, không khẳng định tiết kiệm điện hoặc an toàn ngoài đời.
