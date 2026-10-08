# Checkpoint active sensing — 08/10/2026, đã nhận yêu cầu tiếp tục

## Trạng thái hiện tại: baseline + bốn diagnostics hoàn tất, không còn job GPU

- Người dùng đã cho phép tiếp tục sau khi chuyển máy sang phòng khác. Không bật
  lại automation. Khi hạn mức 5 giờ còn dưới 10% (hoặc gần ngưỡng trước việc dài),
  lưu checkpoint và dừng có kiểm soát các tác vụ GPU của chat này, chờ yêu cầu mới.
- Lượt retry ban đầu bị reserve guard chặn: cần 5,01 GiB, còn 4,96 GiB. Đã dọn
  232.815.987 bytes của hai archive cài CUDA có thể tải lại, giữ SDK đã cài và
  toàn bộ raw/model. Hash cache cũ ở eval/compact-rig-2026-10-08/cache-cleanup.json.
- Episode mới data/active-sensing/rig-town01-60s-retry-20261008 đã hoàn tất và
  **verify 1.200 frame/20 streams**, timestamp span59,9500009 giây, artifacts3,819GiB.
  ManifestSHA599e7e41d05bc119e28cf764a4690f683ed0ac93133f7a07601218bda8d0e645.
  Evidence nhẹ eval/full-rig-60s-2026-10-08/, raw ngoài Git. Session34261 đã thoát0,
  CARLA server đã dừng; không phải episode đã nghiệm thu perception/reward.
- PointPillars sparse pilot3variants đã xong,20frame cách60index (span57giây),
  data/active-sensing/pp-pilot-60s-20261008. Đo thêm actual64-channel AMP tại
  data/active-sensing/pp64-amp-60s-20261008; không upsample/fake channel.
  Cả4 dùng cùng capture/indices. CPU kiểm80tensor hashes khớp raw32/64, bao gồm
  deterministic half subset. Tất cả CARLA/detector/GPU compute đã dừng.
- Matrix wall/CUDA mean ms và geometry matches:32FP32 76,72/63,10→30/62;
  32halfFP32 67,87/54,52→26/62;32AMP53,42/40,09→30/62;
  64AMP64,75/51,03→29/62. AMP32 giảm30,37%wall;64 không chứng minh cải thiện.
  19/20mẫu32AMP vẫn >50ms. Không dùng per-call CUDA/geometry làm cost-window/reward.
- Bot cạnh map hiện chọn được **capture60giây ·4PointPillars** hoặc **pilot cũ ·8**.
  API `?pilot=sparse60|short` chọn allowlist cố định; review namespaces/snapshot
  riêng. Không đổi bộ đo khi còn review nháp/đang lưu, không tự train/áp profile.
  Các report/geometry/auditZIP có link từ panel. Prototype chưa có real LLM call.
- Canonical readonly bundle141members:eval/detector-pilot-sparse-60s-2026-10-08/.
  Case3 ban đầu và case64 giữ riêng; không sửa reports đã đo. Plot4đã view_image kiểm tra; plot3
  đã view_image/refine để p95 và mean không đè chữ. Raw/checkpoints không đưa Git.
- Audit toàn1200frame: reference-visible instances5299; zero input32returns1161,
  input64returns285. Trong radius54m:3484instances,zero32=103,zero64=8.
  ROI công thức draft69instances đều có returns; không chứng minh detectability.
  Full detailed audit ngoàiGit, ZIP166289bytes trong bundle; hash ZIP decoded
  khớp source audit khi gọi HTTP thật. Actor/evaluator boundary vẫn giữ đúng.
- Smoke native2frame mới có1 lượt reference-visible nhưng input32 không có điểm
  trong engine box; input64 có. Evidence compact-world-gt-audit.json giữ scope world
  và reference inventory. Không đồng nhất reference visibility với observability.
- **206tests11,71s passed**, Ruff và componentESLint qua. Webpackproductionbuild
  Next16.3.8 qua, TypeScript qua. Turbopack gặpEPERM bind IPC cả khi escalated;
  dùng `next build --webpack` theo local docs, không bypass browser URL policy.
- HTTP thật:health,/carla,proxy4/8variants,reviews,64report,GTsummary/ZIP đều200.
  EvidenceSHA mới2469b20de1d9e001ac0a9e7e98d08368d5f2f8216ca8a34face2f037e3a28f92.
  eval/detector-sparse-60s-api-check.json. Actual engineer reviews0; không tạo giả.
  SSR không chứa picker vì dock chưa mở; **chưa browser render QA**, vẫn bị policy.
- Backend8000PID162507/session31707,frontend3111PID159832/session49012, dùng build
  standalone mới/static đã copy. Worker9023idle giữ nguyên, chưa restart worker.
  Không gọi capture/detector/train online từ bot; đây là đọc số đo đã lưu.
- Ổ đĩa còn khoảng1,18GiB sau build. Đã hỏi phương án thêm15–20GiB/ổ khác/máy khác,
  chưa có trả lời. Không bắt đầu full-rig60s mới khi thiếu reserve;
  cần phương án thêm dung lượng/offload giữ checksum, không xóa raw hay checkpoint.

Chưa có 12–24 **validated** profiles, complete GT ontology/static mapping, CRN/seg
adapters, total GPU/window, ROS2 bridge hoặc real BC/PPO. Không ép train từ pilot.
Không push/merge trong lượt này. Commit phần compact64edf65; baseline/stride3837a39.
GUI/evidence đã commit0d3831c; guard thiếu member trong bundle đi kèm checkpoint này.
9 focused tests qua sau guard: missing artifact→409, optional absent archive→available=false.
AutomationPAUSED, không bật lại.
Hạn mức mới nhất85%used/15%remaining, reset12:05:33VN; query lại trước công việc dài.
- Metadata ngắt cũ đã kiểm kê 517 frame, mỗi frame 20 stream; file tham chiếu
  hiện diện, chưa verify checksum toàn bộ. Không gắn manifest complete cho lượt cũ.

## Lịch sử yêu cầu dừng trước đó

- Người dùng yêu cầu dừng CARLA vì tiếng quạt ảnh hưởng giấc ngủ; lệnh dừng được
  chuyển từ chat liên quan. Collector/client đã nhận SIGINT, server riêng nhận SIGTERM.
  Kiểm tra PID 145194/144923/144935 và danh sách CUDA compute: không còn tiến trình.
  Yêu cầu mới cho phép chạy lại đã được ghi ở đầu checkpoint này.
- Automation `ti-p-t-c-p-027-sau-reset-h-n-m-c` **PAUSED** theo yêu cầu dừng,
  prompt hiện tại “Đã dừng theo yêu cầu người dùng.” Không tự bật lại.
- Capture dự kiến 60 giây/1.200 frame đã giữ **517 file metadata**, frame CARLA
  65–581, khoảng 25,8 giây từ timestamp đầu đến cuối. Thư mục
  `data/active-sensing/rig-town01-60s-20261008`, `user-interruption.json` ghi
  `interrupted`, `complete=false`. Không có manifest hoàn tất; không dùng làm
  episode 60 giây hoàn chỉnh hoặc dữ liệu train đã nghiệm thu.
- Giữ nguyên partial artifacts/log. Chỉ kiểm kê metadata và file hiện diện khi dừng;
  chưa verify toàn bộ checksum của partial capture, chưa chạy perception trên nó.

## Thay đổi mới đã kiểm tra trước khi dừng

- Collector schema 2 `raw-only-lossless-v2`: raw NPZ giữ nguyên, tọa độ ego dựng lại
  bằng calibration đo thật; semantic camera GT thành PNG uint8 lossless, RGB PNG
  giữ nguyên. Schema 1 cũ vẫn đọc được. Không dùng semantic GT làm actor input.
- Chuyển 20 frame cũ: sensor bytes 121.967.963 → 71.217.954, giảm **41,61%**.
  Đối chiếu raw/ego/semantic chính xác; SHA tensor đầu vào BEVFusion AMP của cả
  20 frame khớp archive cũ. Không chạy lại model, không đổi provenance prediction cũ.
- Capture native 2 frame Town01 compact đã verify đủ 20 streams. Inventory gồm
  4.125 mesh references của môi trường; bbox world đúng hệ tọa độ. Actor GT mới
  lấy toàn bộ vehicle/walker trong world. Mapping ID mesh ↔ semantic LiDAR và
  coverage/ontology chưa kiểm định, nên chưa có scene precision hoặc reward RL.
- Town02/seed27/4 xe/2 pedestrian bị native Signal 11 trước frame đầu. Chưa xác
  định nguyên nhân; không gán cho pedestrian/GPU hoặc xem Town01 là chứng minh fix.
- Quota ghi compact + reserve 1 GiB bảo vệ ổ đĩa; vượt quota/hủy thì không có
  manifest hoàn tất. Server chết trong capture được phát hiện sớm, tránh client
  chờ hết RPC timeout. Fresh lifecycle chỉ quản lý server do tác vụ tạo.
- Replay đo thật chặn partial pilot và metadata boolean dạng chuỗi; đòi protocol
  hash cùng cờ nghiệm thu catalog/quality/reward. Cờ không thay evidence hoặc review.
- **197 tests passed (12,50 giây)**; Ruff và git diff --check qua. Frontend không đổi trong lượt này; lint/build
  frontend ở checkpoint trước vẫn là lần kiểm tra gần nhất. Browser render QA còn
  bị policy chặn, không có ảnh UI được kiểm tra tự động trong lượt này.
- Evidence nhẹ: `eval/compact-rig-2026-10-08/`. Raw ngoài Git. Chưa push/merge.

## Chạy lại khi người dùng cho phép

Không append vào capture bị ngắt: session CARLA mới không tiếp tục timeline cũ.
Chọn thư mục mới, kiểm tra dung lượng và nguồn điện trước; ví dụ từ repo:

```bash
CARLA_BRIDGE_TIMEOUT_SECONDS=1800 .venv-experiments/bin/python \
  scripts/collect_active_sensing.py capture --seconds 60 --hz 20 \
  --map Town01 --vehicles 8 --pedestrians 0 --seed 7 --include-64 \
  --disk-budget-gib 4 --output data/active-sensing/rig-town01-60s-retry-20261008
```

Lệnh trên đã được khởi chạy sau yêu cầu tiếp tục; không chạy trùng và không reuse
output đã tồn tại cho lượt sau. Capture có thể
abort nếu thiếu reserve, không giảm thời lượng để báo hoàn tất giả. Sau capture
thành công cần kiểm định GT, nhiều scenario và tổng GPU/window trước catalog
12–24 validated profiles → BC/PPO; ROS2/CRN/segmentation adapters vẫn còn thiếu.

Hạn mức đọc gần nhất: 62% đã dùng cửa sổ 5 giờ, reset 12:05:33 Việt Nam
(`resetsAt=1791435933`). Luôn đọc lại khi tiếp tục. Không lưu credential.

---

## Lịch sử checkpoint khoảng 08:07 — trạng thái bên dưới là trước khi dừng

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
- 182 tests qua; Ruff, frontend lint, production build qua. HTTP thật health, /carla,
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

## Kết quả mới trong lượt 08:00–08:07

- Official PointPillars nuScenes SECFPN strict load thành công; full SHA khớp filename.
  Data runtime riêng như BEVFusion. Upstream feature contract XYZ + lag, không XYZI.
- 3 variant ×20 frame cùng capture: full FP32 wall82,27/CUDA67,36 ms, 91/152;
  half FP32 wall71,19/CUDA56,71 ms, 57/152; full AMP wall57,45/CUDA42,45 ms, 91/152.
  Tất cả vẫn vượt chu kỳ 20 Hz; 10 Hz chỉ đủ trong pilot inference độc lập, chưa online.
- Gate/replay dùng `numpy-default-rng-sorted-subset-v1`, seed+frame_id. Có test đối chiếu
  đúng indices giữa hai đường chạy; bản gate stdlib Random cũ cần xuất lại bảng/hash.
- `scripts/audit_carla_gt.py`: geometry return counts từng actor/input32/64/half,
  taxonomy kiểm enum0.9.16. 12 lượt reference-visible mà input32 không có điểm trong box,
  input64 có2. Không có unknown semantic target ID trong bề mặt reference đã hit;
  vẫn không đủ complete GT/precision/reward. Xem docs/DETECTION_GT_PROTOCOL.vi.md (draft).
- Archive mở rộng8 variant,193 members pin fullSHA, prior-summary/prior-manifest giữ audit
  bộ5 ban đầu; thêm gt-coverage-audit và pilot-comparison-8.png. Plot đã view_image kiểm tra.
- Bot có8 variant + GT audit; review hiển thị thuộc snapshot hiện tại hay cũ, không tự duyệt.
  API/proxy200; checks ở eval/detector-pointpillars-2026-10-08-api-check.json.
  Snapshot SHA83b712da279ad6998fa95994290fce1815f671e98ae1bfafb3e3ffdff6b1fba9.
- 182 tests11,66s passed, Ruff/frontendlint/build passed. Chưa browser render QA vì policy.
- Không có CARLA/detector/train đang chạy; chỉ web/worker idle. Không thêm ROS2 hoặc train
  policy thật trong lượt này. Không có thêm long-duration capture; free disk khoảng5,3GiB.
- Bước tiếp: complete GT/static inventory + capture storage (có thể raw-only NPZ/semantic PNG
  lossless, schema mới và guard), rồi long episode; nhiều scene/pedestrians/events/seg/radar
  adapters + total GPU/window trước validated profiles và BC/PPO. Không ép train từ pilot.

## Runtime hiện tại

- Backend local 8000: uvicorn PID 141372, exec session 2548.
- Frontend local 3111: standalone server; đã restart với build cuối lúc khoảng 08:07. Static/public assets đã copy
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
2. Xử lý cadence thực trên RTX 2050: đã có PointPillars pilot; AMP 57,45 ms, vẫn chưa 20 Hz.
   Không bật profile 20 Hz chỉ vì scheduler có 20 slot.
   Shield phải báo infeasible nếu cấu hình khả dụng không đáp ứng nhiệm vụ/nhịp yêu cầu.
3. Chỉ sau protocol đạt, đo 2–3 profile trước; rồi 12–24 **validated discrete** profiles.
   Current catalog 24 là ứng viên; CRN/fused/seg chưa được nghiệm thu. Không mở MultiDiscrete.
   Sampling gate và detector đã thống nhất ABI NumPy v1; không reuse bảng gate cũ stdlib Random.
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

Tool gần nhất trong lượt: used 39% cửa sổ 5 giờ; `resetsAt=1791435933`
(12:05:33 ngày 08/10 Việt Nam). **Luôn query lại**, không dựa vào giá trị lưu này.
Nếu còn <10% trước reset: lưu tiến độ, hoãn công việc nặng tới reset thực tế.
Automation id: `ti-p-t-c-p-027-sau-reset-h-n-m-c`. Chỉ tắt khi tất cả yêu cầu hoàn tất.
Không lưu password/API key trong tài liệu, notebook, log hoặc Git.
