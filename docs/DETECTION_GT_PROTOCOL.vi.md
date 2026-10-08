# Protocol GT cho active sensing — draft cần engineer nghiệm thu

Pilot hiện tại chưa đủ để train policy thật. Mọi cổng bên dưới chưa được đánh dấu đạt
chỉ từ smoke hoặc 20 frame cùng một cảnh. Agent không điều khiển xe.

## 1. Population và ontology cố định

- Target động/đứng yên: xe, người đi bộ, xe đạp, xe máy; người dễ tổn thương có trọng số
  riêng theo plan. Cần bảng map blueprint CARLA → class, chỉ rõ van/ambulance/bus,
  cyclist/rider và đối tượng ngoài ontology. Giữ raw `type_id` để audit.
- Ghi toàn bộ vehicle/walker actor đang tồn tại từ world snapshot, không chỉ list spawn.
  Ghi thêm inventory environment/parked/static cùng bounding boxes world-space.
  [API CARLA 0.9.16](https://carla.readthedocs.io/en/0.9.16/python_api/#carla.World)
  có `get_actors`, `get_environment_objects`, `get_level_bbs`; environment ID không được
  tự coi là semantic LiDAR actor ID nếu chưa kiểm chứng mapping/deduplication.
- Box actor local phải qua actor transform; box environment/level đã world-space.
  Không nhân environment transform thêm lần nữa. Đối tượng nhiều mesh cần group/dedup;
  bỏ mesh thiếu annotation không được tính là false positive.
- Road/wall/building thuộc bài toán segmentation/occupancy riêng; không dùng detector
  object boxes làm GT semantic hoàn chỉnh.

## 2. ROI, visibility và vùng ignore

- Chốt ROI theo nhiệm vụ/vùng phanh thực nghiệm trước khi đo. Công bố range cấu hình
  từng detector: PP ±50 m, BEVFusion ±54 m; range không phải detection guarantee.
- Denominator GT cố định độc lập action. Tắt sensor/giảm điểm không được xóa target khỏi GT.
- Visibility reference semantic 64 chỉ là tiêu chí tham chiếu, không chứng minh LiDAR 32,
  camera hoặc radar được chọn có đủ bằng chứng. Lưu số input returns trong box từng sensor,
  reference hits/occlusion và sự kiện xuất hiện; không đưa GT này vào actor observation.
- GT không phủ toàn scene → unknown extra predictions giữ unknown; precision/FP = null.
  Muốn tính FP cần coverage gate đầy đủ + ignore region/ontology, không chỉ “không thấy ID lạ”.
- Input LiDAR32/64 và semantic LiDAR độc lập: không ghép nhãn theo array index hoặc nearest
  point rồi coi như ground truth thật mà không có protocol/cổng kiểm định riêng.

## 3. Matching và temporal quality

- Pilot hiện chỉ maximum-cardinality one-to-one class-agnostic tâm XY ≤2 m, score ≥0,3.
  Đây là geometry diagnostic, không phải nuScenes mAP, segmentation IoU hoặc reward.
- Chốt metric task thực: class-aware matching, tolerance theo class/size, weighted recall
  trong ROI, coverage đầy đủ cho FP, độ trễ target mới tính từ frame xuất hiện, grace/deadline
  theo plan. Giữ event/frame ID, thời gian mô phỏng và thời gian inference riêng.
- Empty-target window không được gán recall = 1 để làm đẹp điểm. Model output ngoài ontology,
  ROI hoặc ignore được phân loại bằng luật công khai. Không đổi threshold sau khi xem test.

## 4. Cổng trước 12–24 validated profiles và BC/PPO

1. Engineer kiểm overlay calibration, box extent/rotation, ontology/static coverage và
   representative pedestrian/crossing/cut-in events. Review có reference hash, không tự duyệt.
2. Đo 2–3 profile cùng capture: quality task + total GPU activity/window (monitor, transition,
   mọi invocation), timing online/chậm/missing frame. Không dùng per-call CUPTI làm tổng chi phí.
3. Nhiều episode 60–120 s, map/seed/weather/event; train/validation/test split theo capture.
   Cảnh held-out không dùng chọn profile hay tune threshold. RGB weather không tự là suy giảm radar.
4. Catalog 12–24 chỉ gồm checkpoint + adapter + cadence + task đã kiểm định. CRN thiếu ABI/weights,
   segmentation chưa có model thì disable; không điền kết quả synthetic/GT thay inference.
5. Shield báo infeasible nếu không có profile đáp ứng; PP AMP 57,45 ms vẫn chưa đáp ứng 20 Hz.
   Không fallback “full là an toàn” hoặc gắn nhãn validated chỉ vì action mask có profile đó.
6. Khi replay đủ cổng mới BC từ rule teacher → masked/Lagrangian PPO. So full/min/rule/RL trên
   tập giữ riêng; critic/actor boundary và state history phải đúng. MultiDiscrete để sau.

Hiện đã có capture/sensor/cost smoke + audit geometry. Chưa có complete detection-quality,
segmentation, GPU/window, ROS2 online, full-duration split hay policy đã train từ dữ liệu thật.
