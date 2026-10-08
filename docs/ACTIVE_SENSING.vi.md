# Active sensing: triển khai theo cổng nghiệm thu

Ngày kiểm tra: 08/10/2026. Nguồn yêu cầu: active-sensing-rl.vi.md do người dùng cung cấp.
Đây là nền móng phần mềm cho plan. Capture CARLA đã chạy thật; chưa có policy RL
được train trên dữ liệu đo thật hoặc kết quả tiết kiệm GPU.

## Trạng thái đã làm

- Khôi phục liên kết Git worktree Windows sang Linux, không reset hoặc thay thế các thay đổi UI có sẵn.
- Core độc lập ROS/CUDA: 24 profile ứng viên, kiểm tra rig/model/task, policy luật dùng observation.
- Gate chọn camera/LiDAR/radar theo profile, lấy mẫu điểm xác định bằng seed, đồng bộ frame.
- Scheduler 5/10/20 Hz theo thời gian mô phỏng; đổi profile ở capture tiếp theo, không chạy burst bù.
- Shield không bật lại sensor failed/unknown; không có cấu hình phù hợp thì báo infeasible.
- Ground truth chỉ dùng tính reward/metric; observation actor không chứa GT, thời tiết GT, metric GT.
- Replay kiểm tra frame, khoảng thời gian, rò rỉ train/test cùng capture và provenance.
- Matching detection một-một theo class, khoảng cách tâm <= 2 m, score >= 0.3;
  phạt false positives và output trễ, không ép GPU ratio vào [0,1].
- Ràng buộc segmentation riêng cho camera/LiDAR: cần nhãn tham chiếu thật và số phần tử đã đánh giá.
- Adapter Gymnasium và script BC + masked PPO + cập nhật Lagrange được chuẩn bị.
  Đã cài Gymnasium/SB3 và smoke BC/PPO 256 bước bằng fixture tổng hợp. Chưa có measured replay
  đủ điều kiện train; smoke này chỉ kiểm tra trainer, không phải policy được nghiệm thu.
- CLI doctor, catalog profiles, fixture synthetic và đánh giá 3 baseline có timeline.

Frontend giữ replay (/experiments) và CARLA form (/carla); hội thoại agent dùng bot mở rộng
cạnh workspace, `/agent` cũ chuyển về `/carla`. Xem AGENT_EVIDENCE.vi.md về evidence/review.
Chưa nối ROS. Policy luật hiện là baseline bảo thủ theo
sensor health/brightness/contrast/return ratio; chưa port toàn bộ bảng luật nhiều yếu tố của plan.

## Các chỉnh sửa cần thiết so với plan

1. ROS 2 native được công bố ở CARLA **0.9.16**, không mặc định 0.9.15 có cờ --ros2.
   CARLA 0.9.16 có wheel Python 3.10–3.12:
   https://carla.org/2025/09/16/release-0.9.16/
   Chốt phiên bản và smoke test. Đã fetch carla-agent-experiments và feat/ai-agent-integration; CARLA capture hiện có
   tại src/simulation/carla_capture_core.py. Đường legacy 0.9.11 vẫn được giữ;
   chưa có bridge ROS 2 native và không coi nó là implementation ROS của plan.
2. Checkpoint chưa được xác nhận hỗ trợ rig thiếu camera/radar. Bản đầu chỉ cho 0/6 camera
   và 0/5 radar với đúng model tương ứng. **Profile là ứng viên**, chưa nghiệm thu catalog.
   Detector LiDAR và Camera+LiDAR riêng đã smoke CARLA; chưa nối vào worker/bot/ROS.
   Không giả định camera_weight thay được trọng số học bên trong BEVFusion/CRN.
3. 24 profile = 4 nhánh detection × 3 Hz × 2 lựa chọn segmentation.
   LiDAR-only có thể thêm lidar_seg; CRN có thể thêm camera_seg;
   CL/fused có thể thêm cả hai. Experiments đặt required_tasks để không đổi nhiệm vụ khi so chi phí.
   Bản đầu giữ LiDAR 32 tia, 100% điểm, 1 sweep. Núm khác cần đo trước khi mở action space.
4. Không coi kết quả [frame, profile] độc lập với lịch sử tracking/flow.
   Replay hiện **chỉ chấp nhận stateless_independent_windows**. Chưa bật Flow hoặc tracking.
   Multi-sweep gate ném NotImplementedError cho tới khi có adapter ego-motion đúng.
5. Chỉ đổi mưa/sương trên CARLA RGB chưa mô phỏng suy giảm LiDAR/radar.
   Tham số nhiễu môi trường là ngoại sinh, agent không được giảm nó để cải thiện reward.
6. Shield là bộ kiểm tra cấu hình, không phải bảo đảm an toàn. Nó không biết vật bị mọi
   sensor/model bỏ sót. Tầm radar rộng hơn không mở rộng output range của CRN/BEVFusion.
   Không có sensor khỏe hoặc vùng yêu cầu vượt model range thì ghi infeasible.
7. MaskablePPO không tích hợp recurrent policy. Bản đầu MLP + Discrete profiles;
   không dùng masking độc lập từng chiều để giả vờ kiểm soát mọi ràng buộc tổ hợp:
   https://sb3-contrib.readthedocs.io/en/master/modules/ppo_mask.html
8. Trainer hiện dùng một critic quan sát, reward penalty với beta cố định trong một rollout.
   Callback cập nhật beta cho rollout tiếp theo, không sửa reward sau GAE.
   Asymmetric/dual critics là nâng cấp chưa làm.
9. Ràng buộc thực thi ban đầu là **mean per-window cost**: bỏ sót vật trong ROI hoặc deadline/
   segmentation không đạt. Không trình bày nó như chứng nhận xác suất an toàn.
   Chưa triển khai grace 3 frame hoặc p95 thời gian phát hiện vật mới; cần log đủ 20 Hz.
   dt=0.05 và bước agent=0.5 s không đồng nghĩa inference đạt 20 Hz thời gian thực.
10. Cấu hình "đầy đủ" là baseline, không mặc định chất lượng cao nhất.
    Các baseline cùng đi qua shield. Báo shield intervention và infeasible để không che mất điều đó.
11. Ít điểm không bảo đảm GPU giảm; tensor cố định có thể giữ compute gần nguyên.
    Tổng GPU ms/window phải cộng mọi lượt inference, mọi task, chuyển model và monitoring.
    CARLA render, wall latency, GPU perception và CPU policy phải đo/báo riêng.
12. Observation đo được là điều kiện cần, không đủ để khẳng định sim-to-real.
    Test tập chưa dùng để chọn cấu hình và dữ liệu thực vẫn cần riêng.

## File chính

- src/active_sensing/core.py: profile, observation, shield, baseline, detection reward.
- src/active_sensing/gate.py: chọn stream và scheduler.
- src/active_sensing/sync.py: barrier chính xác frame, timeout.
- src/active_sensing/replay.py: schema, actor boundary, replay, timeline/summary.
- src/active_sensing/gym_env.py: adapter Gymnasium tùy chọn.
- scripts/active_sensing.py: diagnostics/catalog/replay.
- scripts/train_active_sensing.py: trainer tùy chọn; smoke synthetic đã qua, measured training chưa chạy.
- tests/active_sensing/test_core.py: unittest độc lập app dependencies.

## Chạy phần core ngay trên Linux

Từ root P-027-active-sensing:

~~~bash
python3 -B scripts/active_sensing.py doctor
python3 -B scripts/active_sensing.py profiles
python3 -B -m unittest discover -s tests/active_sensing -v
~~~

Thử đường CLI bằng fixture **synthetic**, không dùng kết quả này trong báo cáo model:

~~~bash
python3 -B scripts/active_sensing.py fixture --output /tmp/p027-active-sensing-fixture.json
python3 -B scripts/active_sensing.py evaluate /tmp/p027-active-sensing-fixture.json \
  --allow-synthetic --split test --output /tmp/p027-active-sensing-fixture-report.json
~~~

Mặc định CLI từ chối fixture synthetic. Cờ allow-synthetic luôn cần được ghi cùng provenance.
Fixtures chỉ chứa số giả có chủ đích để kiểm tra phần mềm; không được gọi là benchmark CARLA.

## Định dạng dữ liệu đo thật

Dùng fixture để xem schema, rồi thay bằng kết quả **inference và timing thật**:

- schema_version=1, window_s=0.5.
- provenance.kind=measured_perception.
- provenance.history_mode=stateless_independent_windows.
- capture_id, model_manifest_sha256, hardware, timing_scope=total_gpu_work_per_window,
  monitoring_cost_included=true.
- profiles: cấu hình chính xác dùng tạo dữ liệu; reference_profile thuộc catalog.
- constraints.required_tasks: cùng nhiệm vụ cho mọi cấu hình được so.
- episodes: id, capture_id, split train/validation/test, steps.
- Mỗi step: frame_id, observation (monitor đo trước quyết định), ground_truth,
  profile_results cho toàn bộ profile trong catalog.
- Mỗi result: frame_id, detections, gpu_ms (tổng công việc/window),
  end_to_end_ms (wall latency), actor_feedback đo được.
- task_metrics.camera_seg/lidar_seg: iou, reference_kind=ground_truth,
  evaluated_elements>0. Tính ngoài core với mapping lớp/valid mask đã kiểm tra.
- Label không chắc chắn, không đồng bộ, không có true GT segmentation thì không đủ
  cho experiment có ràng buộc segmentation. Không đổi pseudo-GT thành nhãn thật bằng metadata.
- Observation dự đoán dùng **kết quả profile đã chạy ở bước trước**; không lấy kết quả
  chưa chọn ở bước hiện tại, không cho actor xem GT cost/IoU.
- Capture gốc chỉ thuộc một split. Giữ thêm map/scenario family/seed chưa thấy trong test.
  Schema check không tự chứng minh dữ liệu thực hoặc chất lượng annotation; audit nguồn vẫn cần.

ROI khởi điểm = max(5 m, v*0.5 + v²/(2*4)).
Đây là miền đánh giá bảo thủ của thí nghiệm, không tính năng điều khiển/phanh.
Hạn chế v1 ở đô thị <= 50 km/h. Phạm vi khai báo model không phải bảo đảm chất lượng.

## Runtime RL riêng, không trộn với detector legacy

Chỉ chạy khi đã có Python venv/pip phù hợp:

~~~bash
python3 -m venv .venv-active-sensing
.venv-active-sensing/bin/python -m pip install -r requirements-active-sensing.txt
.venv-active-sensing/bin/python scripts/train_active_sensing.py \
  data/active-sensing/measured-replay.json --steps 20000 --bc-steps 200 \
  --output data/active-sensing/policy-v1
~~~

Máy có Python hệ thống 3.10.12; kiểm thử API dùng Python 3.12.14 trong .venv-review.
Runtime RL và CARLA 0.9.16 đã cài; NVIDIA driver hoạt động trên RTX 2050 4 GB.
Capture occupancy hai frame thành công. Full rig CLI đã thu thật 20 frame đồng bộ,
6 RGB + 6 camera GT, LiDAR 32/64 + semantic LiDAR GT, 5 radar và actor GT/calibration.
Xem FULL_SENSOR_CAPTURE.vi.md và eval/full-rig-2026-10-08/. Reader/gate/scheduler đã qua;
Detector LiDAR và Camera+LiDAR OpenMMLab đã chạy thật với strict checkpoint loading,
CUDA activity đo bằng CUPTI; xem DETECTOR_CARLA_SMOKE.vi.md. Chưa nghiệm thu quality,
chưa có measured replay/GPU work toàn window hoặc bridge ROS 2. Workaround native reload crash dùng server/client mới mỗi capture,
chi tiết tại CARLA_LINUX_SETUP.vi.md. Worker occupancy của web vẫn chạy CPU;
detector riêng đã đo CUDA activity/invocation, chưa có GPU work/window đầy đủ cho agent.

## Cổng nghiệm thu tiếp theo

1. Chốt máy/GPU/VRAM, CARLA 0.9.16 + ROS 2 Humble; một tick owner và use_sim_time.
2. CARLA capture một episode ngắn: rig, frame/timestamp, extrinsics, GT.
3. Smoke BEVFusion-L trước; sau đó CL, CRN và segmentation. Riêng radar cần adapter;
   vận tốc hướng tâm CARLA không được giả thành vx_comp/vy_comp nuScenes.
4. Đo 2–3 profile trước khi đo cả catalog. Ghi GPU work/window thực và deadline miss.
5. Smoke Gym/SB3 + BC/PPO; train/validation/test độc lập.
6. Đánh giá 4 policy (full/min/rule/RL), cả target-conditional miss và số infeasible.
   Nhiều bước đường trống không được che việc bỏ sót ở bước có vật nguy hiểm.
7. Bridge online, Lab timeline và shield events. Chỉ sau đó báo demo vòng kín hoàn thành.
8. Kiểm chứng dữ liệu thực; chưa tuyên bố an toàn ngoài đường hoặc GPU tiết kiệm đã đạt.

**Thứ tự tiếp tục:** rig/calibration/GT → smoke detector và radar adapter → đo 2–3 profile
→ kiểm định catalog 12–24 profile → bảng perception đo thật → BC/PPO offline → so bốn policy
→ bridge online. Chưa mở MultiDiscrete hoặc train từ hai-frame occupancy proxy smoke.

## Bằng chứng

eval/agent-integration-2026-10-08/ lưu kiểm tra phần mềm thực chạy.
Không có inference CARLA, checkpoint RL đã train, phép đo GPU hay kết quả sim-to-real trong thư mục này.
Capture CARLA thực nằm riêng tại eval/carla-linux-2026-10-08/ và
eval/agent-evidence-2026-10-08/. Study ba cấu hình mới kết luận giữ baseline theo ngưỡng,
không chứng minh độ tin cậy detection hoặc khả năng tiết kiệm GPU.

## Tích hợp hai branch agent

Xem AGENT_BRANCH_AUDIT.vi.md để phân biệt agent lập thí nghiệm, replay và policy RL,
và các sửa đổi đã thực hiện trên branch codex/active-sensing-integration.
