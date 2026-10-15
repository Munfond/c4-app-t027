# Đối chiếu hai branch agent với plan Active Sensing RL

Ngày kiểm tra: 08/10/2026. Checkout phát triển: P-027-active-sensing.
Branch local: codex/active-sensing-integration. Không cập nhật main hoặc publish GitHub trong lượt này.

## Hai branch đã fetch và đọc

| Branch / revision | Phần có thể kế thừa |
|---|---|
| carla-agent-experiments / e8873c3 | Capture đồng bộ CARLA, khóa một capture trên một simulator, client Python 3.7 riêng cho CARLA 0.9.11, seed/map/traffic/highway, LiDAR feature adapter, U-Net occupancy, sensor-study queue, UI agent và dataset export. |
| feat/ai-agent-integration / d312b24 | Replay raw nuScenes LiDAR/radar/camera, ba checkpoint occupancy, reductions trước tạo features, so sánh baseline/candidate, session scope và cleanup, replay agent/UI. |

Hai branch chung nền 6f97fe9. Một branch không chứa toàn bộ phần mới của branch còn lại.
Bản tích hợp giữ cả hai nguồn, không áp một phiên bản file lên tất cả conflicts.

Đã đọc schemas, agents, queue/worker, registry, evaluator, capture/bridge, replay/comparison,
sessions/API, routes frontend, tests và evidence CARLA liên quan.

## Agent đang có là gì?

**Agent lập và tổng hợp thí nghiệm:** LLM chuyển yêu cầu thành spec giới hạn; worker chạy
baseline/candidate; Python chọn bằng metric; LLM giải thích. Đây là tính năng hữu ích
để tìm cấu hình offline, nhưng chưa học policy hay đổi cấu hình sensor theo từng observation.

**Active Sensing RL trong plan:** policy quan sát tín hiệu đo được, chọn profile theo thời gian,
shield kiểm tra ràng buộc, reward dùng GT tách khỏi actor. Core/replay/Gym/trainer đã được đưa
vào checkout này; chưa nối với CARLA/API/UI và chưa train/evaluate policy RL.

Không gọi bảng lựa chọn offline là policy RL đã huấn luyện.

## Những sửa đổi đã thực hiện khi tích hợp

- Giữ /experiments cho replay; giữ /agent cho CARLA agent; khôi phục form CARLA tại /carla.
- Khôi phục runbook/form/check_carla/test_sensor_agent thay vì xóa cùng branch replay.
- Giữ tham số max_iou_drop/frames từ UI CARLA, route highway/lane-change và legacy bridge.
- Giữ replay tools, session isolation, scene validation và giải thích ngắn theo metric.
- Worker dùng advance_running cho cả CARLA và replay trong từng store/session; không cần
  browser tiếp tục polling để enqueue trial kế tiếp. Lỗi orchestration được ghi và hủy study.
- Capture download dùng store.root() của phiên thay vì experiment_root toàn cục.
  Regression kiểm tra có thể tải đúng phiên và không fallback sang phiên khác.
- SensorStudySpec thêm min_occupied_iou=0.3 (có thể cấu hình qua schema).
  Phải đạt cả chất lượng tuyệt đối, giới hạn giảm IoU và reference hash khớp mới được chọn.
  Nếu baseline/candidate đều thấp thì provisional_selected=null.
  0.3 là ngưỡng thí nghiệm ban đầu, không chuẩn an toàn; cần chọn bằng validation riêng.
- Đưa src/active_sensing, CLI, optional Gym/trainer, tests và requirements RL riêng vào branch.
  Giữ data synthetic có nhãn rõ và bị từ chối theo mặc định.

## Plan cần điều chỉnh theo code thực tế

| Nội dung | Thực tế / quyết định |
|---|---|
| CARLA + ROS 2 | Legacy CARLA 0.9.11 đã có đường chạy; không bắt team bỏ nó để demo offline. Plan dùng native ROS 2 phải smoke CARLA 0.9.16 + ROS Humble riêng. Hiện chưa có nodes ROS, một tick-owner ROS hoặc online sensor gate. |
| Model switching | Agent hiện chạy occupancy_lidar / occupancy_radar / occupancy_lidar_radar. Catalog RL thử nghiệm là official_lidar / official_cl / crn / fused. Hai catalog khác task và adapter; không nối bằng đổi tên model. |
| CARLA CRN/radar | Chưa có adapter radar được hiệu chuẩn. Không giả vận tốc hướng tâm thành vx_comp/vy_comp; chưa bật CRN/BEVFusion-Camera-LiDAR trên CARLA nếu thiếu đúng rig/calibration/runtime. |
| Camera/Segmentation | Camera replay đang đo fidelity/optional detector consistency; camera chưa vào U-Net occupancy. Không dùng PSNR hay retention như GT accuracy/segmentation IoU. RL task camera_seg/lidar_seg cần inference và true GT riêng. |
| Flow/history | Checkpoint temporal có adapter trên nuScenes; replay agent hiện occupancy-only. Cache worker hash toàn capture. RL stateless lookup chưa hỗ trợ lịch sử phụ thuộc profile; cần sequential replay nếu bật flow/tracking/multi-sweep. |
| Mưa/sương | RGB weather/overlay không đủ cho thí nghiệm LiDAR/radar robustness. Sensor degradation phải ngoại sinh, có provenance và kiểm định; agent không được chỉnh độ nhiễu thời tiết để hưởng reward. |
| Chi phí | Nhánh agent chọn theo payload bytes; model-only p50/p95 là số đo riêng. Tensor BEV vẫn 200×200; ít điểm không bảo đảm giảm GPU. RL cần tổng inference GPU work/window gồm monitor/task/switch, latency deadline và CPU/CARLA render tách riêng. |
| Reward/GT | Planner được nhận kịch bản do người dùng đặt và LLM đọc báo cáo GT sau thử nghiệm. Actor RL tuyệt đối không nhận weather GT/metric GT/các prediction profile chưa chạy. Core đã kiểm tra boundary này; chưa có observation extractor online. |
| Shield | Core kiểm tra cấu hình/health/range/Hz. Nó không biết vật thể bị mọi sensor bỏ sót và không chứng nhận an toàn. No feasible profile phải được báo, không bật lại sensor failed/unknown. |
| Training/eval | BC + masked PPO/Lagrange mới là trainer được chuẩn bị. Chưa smoke train, dual critic/recurrent hay held-out RL eval. Không dùng evidence hai frame để tuyên bố policy tối ưu/sim-to-real. |

## Evidence có sẵn và giới hạn

Branch CARLA có báo cáo 07/10/2026, server/client 0.9.11, inference CPU, Town01,
2 frame/profile. Occupied IoU lần lượt 0.3321 / 0.2958 / 0.2312 ở 600k / 300k / 150k điểm/giây.
Hai cấu hình giảm điểm không đạt giới hạn giảm IoU 0.02; baseline được giữ.
Các báo cáo khác/highway được giữ nguyên để review; raw capture được ghi là ở máy Windows của team,
không tự có trong checkout Linux này.

Đây là báo cáo đã track từ branch, không phải CARLA được chạy lại trong lượt tích hợp Linux.
GT static dùng height proxy + semantic-LiDAR observed mask/actor footprints; không phải
dense semantic occupancy GT hoàn chỉnh. Hai frame không đủ p95 ổn định hoặc kiểm định tổng quát.

Kiểm thử local: xem eval/agent-integration-2026-10-08/verification.json.
139 tests backend qua, gồm 41 core tests và ba checkpoint occupancy inference trên fixture có nhãn.
Provider LLM được mock; không gọi OpenAI. Không chạy CARLA thật, ROS hoặc train RL.
Ruff src/tests và frontend lint/build bằng Node 22.23.3 qua.
Đây là evidence phần mềm và CPU checkpoint smoke, không phải benchmark sensor ngoài thực tế.

## Thứ tự phát triển tiếp

1. Dùng CARLA/replay agent hiện có làm bộ thu thập thí nghiệm offline; review proxy labels,
   ghép baseline/candidate bằng exact reference và log input/model/capture identity.
2. Chốt một task occupancy trước. Nếu chuyển detection/Seg3D, triển khai adapter/rig/labels
   và metrics tương ứng rồi mới mở actions; chưa mở tất cả model/sensor cùng lúc.
3. Đo 2–3 profile trên cùng held-out scenarios; ghi GPU work/window và deadline thực,
   monitor cố định được tính chi phí. Không đưa payload report vào replay RL như GPU đo thật.
4. Nối observation extractor với core causal replay; split theo capture/map/seed/scenario family.
   Smoke Gym + BC/PPO, đánh giá full/min/rule/RL với cùng shield và task constraints.
5. Chạy online trên một simulator riêng; một tick owner, timestamp/frame barrier và fail states.
   Sau đó mới thêm RL timeline vào Lab. Giữ CARLA agent/replay hiện có làm baseline kiểm chứng.

## Chạy checkout tích hợp

~~~bash
cd /home/lam/WorkSpace/vinuni-buildphase/P-027-active-sensing
.venv-review/bin/python -B -m pytest tests/ -q
.venv-review/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
# Terminal khác, cùng checkout và EXPERIMENT_ROOT:
.venv-review/bin/python -m scripts.experiment_worker
~~~

.venv-review là venv kiểm thử local Python 3.12, đã có Torch CPU; không commit venv.
Đặt NUSC_ROOT/LAB_DATA_ROOT/EXPERIMENT_ROOT theo máy trong .env riêng.
CARLA server/client cần cài riêng theo runbook; LLM key chỉ cần khi gọi agent planning/summary.
Không copy .env chứa key từ máy khác vào Git.

Frontend đã build với Node 22; sau khi có node/npm 22 trên PATH:
~~~bash
cd frontend
npm ci
npm run build
npm run start -- --hostname 127.0.0.1 --port 3000
~~~

Nguồn plan và giới hạn core: [ACTIVE_SENSING.vi.md](ACTIVE_SENSING.vi.md).
