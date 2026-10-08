# Checkpoint tiếp tục active sensing — 08/10/2026, khoảng 07:48 Việt Nam

Branch `codex/active-sensing-integration`, không push/merge trong lượt này.
Yêu cầu đầy đủ vẫn đang làm; automation theo dõi hạn mức còn ACTIVE, chưa được tắt.
Nguồn plan: `/home/lam/Downloads/active-sensing-rl.vi.md`.

## Đã hoàn thành và kiểm tra

- Bot mở cạnh map, evidence occupancy, kết luận improved/no_improvement/inconclusive,
  engineer review append-only cùng snapshot, không tự train: commit 0465346.
- Full-rig collector + input/GT/calibration/hash boundary: c8c370f.
  Town01/clear/seed 7, 20 frame dt 0,05; 6 RGB + 6 semantic camera GT,
  LiDAR 32/64 + semantic GT 64, 5 radar. Capture ở
  `data/active-sensing/rig-nearby-20261008`, manifest SHA
  `c72255c929c32d55c07fa1ec48ba0dc4504cf4142b2316714eabbc8ee7f581b3`.
- Runtime detector riêng Python 3.10/Torch 2.1 cu121/MMDet3D v1.4 + native CUDA ops,
  official LiDAR smoke: dc11c95. Không đổi runtime CPU của worker/web.
- Camera+LiDAR adapter optical/extrinsics thật, 640×360 → cover/bottom crop 704×256.
  Full SHA checkpoint pin, strict load toàn bộ keys/shapes. File tại URL chính thức có
  fingerprint tên khác full hash; đã xác minh hai reads/CRC/Content-MD5 và giữ discrepancy.
  Xem DETECTOR_CARLA_SMOKE.vi.md, không xóa hoặc che audit mismatch ban đầu.
- Pilot 5 variant × 20 frame, source cùng capture, timing CUDA CUPTI pass riêng / wall pass
  không profiler, partial GT geometry diagnostic class-agnostic, không gán mAP/precision giả.
  Dữ liệu tại `data/active-sensing/detector-pilot-20261008`; archive nhẹ trong
  `eval/detector-pilot-2026-10-08/`, có manifest kiểm checksum toàn bundle.
- Bot → CARLA → **Detector trên GPU · pilot 20 frame**, archive qua API + review riêng.
  Đây là đọc kết quả đo sẵn, chưa phải thực thi detector hoặc policy online từ bot.
- 176 tests qua; Ruff, frontend lint, production build qua. HTTP thật health, /carla,
  evidence proxy và reviews trả 200. Không có engineer review người thật tự tạo.
- Hình calibration/detector/pilot plot đã mở kiểm tra bằng view_image.
  **Không có UI render QA**: browser automation trước đó bị URL policy chặn;
  không thử browser khác/CDP/Playwright để vượt chặn đó.

| Pilot | Wall mean | CUDA activity mean | Ghép GT target/frame |
|---|---:|---:|---:|
| LiDAR full FP32 | 118,46 ms | 100,51 ms | 72/152 |
| LiDAR half FP32 | 111,21 ms | 92,67 ms | 30/152 |
| LiDAR full AMP | 100,44 ms | 82,76 ms | 72/152 |
| CL full FP32 | 545,09 ms | 441,74 ms | 89/152 |
| CL full AMP | 449,64 ms | 345,69 ms | 89/152 |

152 là lượt mục tiêu/frame tương quan trong một cảnh khoảng 1 giây. GT chỉ actor đã spawn,
visibility từ semantic LiDAR GT 64. Không đủ scene precision/class ontology/held-out coverage.
20 Hz chưa đạt ở mọi variant; AMP LiDAR vẫn vượt chu kỳ 10 Hz trong 13/20 frame.
CL vượt chu kỳ 5 Hz ở mọi frame. Không dùng các run này để train hoặc validate catalog.

## Runtime hiện tại

- Backend local 8000: uvicorn PID 136391, exec session 46468.
- Frontend local 3111: standalone server, exec session 88179. Static/public assets đã copy
  vào `.next/standalone/`; không còn warning dùng next start với output standalone.
- Worker occupancy PID 9023 vẫn chạy, idle. CARLA và detector đã dừng sau đo.
- Detector env: `data/runtime/detector-env`; SDK/web/CPU RL: `.venv-experiments`.
- Còn khoảng 5,2 GiB trống. Collector có reserve guard; không thu 60–120 s full-rig bừa
  hoặc hạ guard để ép chạy. Raw hiện PNG + uncompressed semantic camera NPY khá lớn.
- LLM chưa bật/key chưa cấu hình; chưa có real LLM end-to-end call. Review không tự train.
- Một pytest trong sandbox bị treo async IPC; chỉ process đó đã TERM. Suite với IPC cho phép
  chạy đầy đủ 176 passed. Không còn test/train/background benchmark treo.

## Các bước tiếp theo, theo thứ tự

1. Chốt protocol GT trước: actor + parked/static object coverage, ontology/ignore/ROI,
   semantic visibility không thay observability của sensor được chọn. Positive geometry
   diagnostic đang có **không** được đổi thành metric class-aware hoặc reward của plan.
2. Xử lý cadence thực trên RTX 2050: khảo sát thêm baseline detector nhẹ có checkpoint chính
   thức phù hợp (Lab từng có PointPillars). Không bật profile 20 Hz chỉ vì scheduler có 20 slot.
   Shield phải báo infeasible nếu cấu hình khả dụng không đáp ứng nhiệm vụ/nhịp yêu cầu.
3. Chỉ sau protocol đạt, đo 2–3 profile trước; rồi 12–24 **validated discrete** profiles.
   Current catalog 24 là ứng viên; CRN/fused/seg chưa được nghiệm thu. Không mở MultiDiscrete.
   Sampling pilot dùng NumPy RNG, gate dùng stdlib Random; phải thống nhất trước replay.
4. Bổ sung tổng GPU work/window gồm monitor + transition + mọi invocation/task, observation
   chỉ dùng dữ liệu đo trước action/kết quả action trước. Không lấy GT hoặc candidate hiện tại
   chưa được chọn làm actor feature. Không dùng delay/cadence số học thay online deadline log.
5. Episode 60–120 s theo plan cần phương án storage/capture encoding có provenance và guard;
   lossless compression semantic camera, nếu JPEG RGB thì phải ghi rõ policy và kiểm adapter.
   Nhiều map/seed/môi trường/events, split theo capture/scenario, held-out test không dùng chọn profile.
   Thời tiết CARLA RGB chưa là mô hình suy giảm LiDAR/radar; corruption ngoại sinh phải kiểm định.
6. Segmentation và radar adapter: không dùng semantic GT làm input; CARLA radar không có RCS/
   vx_comp/vy_comp nên không bịa để chạy CRN. Thiếu team detection/CRN weights tương thích.
7. ROS 2 Humble chưa cài/nối. CARLA 0.9.16 native hoặc Python bridge; một tick owner,
   use_sim_time, frame barrier, timeout/profile transition log. Agent không điều khiển xe.
8. Khi có measured replay đúng scope đủ cổng: BC(rule teacher) → masked/Lagrangian PPO,
   so full/min/rule/RL trên tập giữ riêng. Hiện mới trainer smoke synthetic 256 steps;
   **chưa policy trained thật**, không tạo policy giả từ 20 frame pilot.
9. Nối detector vào worker/bot/map qua runtime riêng rồi browser QA khi policy cho phép.
   Engineer review chưa phải xác nhận an toàn/sim-to-real hoặc cập nhật policy tự động.

## Hạn mức và automation

Tool gần nhất trong lượt: used 26% cửa sổ 5 giờ; `resetsAt=1791435933`
(12:05:33 ngày 08/10 Việt Nam). **Luôn query lại**, không dựa vào giá trị lưu này.
Nếu còn <10% trước reset: lưu tiến độ, hoãn công việc nặng tới reset thực tế.
Automation id: `ti-p-t-c-p-027-sau-reset-h-n-m-c`. Chỉ tắt khi tất cả yêu cầu hoàn tất.
Không lưu password/API key trong tài liệu, notebook, log hoặc Git.
