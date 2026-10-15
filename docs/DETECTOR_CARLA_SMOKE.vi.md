# BEVFusion LiDAR trên CARLA: runtime và smoke thật

08/10/2026. Đây là checkpoint **OpenMMLab MMDetection3D v1.4.0**, không phải
khôi phục trọng số team đã train hoặc checkpoint MIT BEVFusion. Không gắn metric
nuScenes trước đây của web vào artifact mới này.

## Kết quả đã đo

Capture Town01/clear/seed 7 trong FULL_SENSOR_CAPTURE.vi.md, hai frame 64/65,
15.358 / 15.478 điểm LiDAR 32. Simulator đã dừng trước inference.

| Cấu hình | Điểm input | CUDA activity trung bình | Wall inference trung bình | Hộp score ≥ 0,3 |
|---|---:|---:|---:|---|
| Full points, FP32, intensity raw | 100% | 100,239 ms | 118,004 ms | 3 / 3 |
| Half points, FP32, intensity raw | 50% | 92,219 ms | 110,100 ms | 1 / 2 |

CUDA activity là tổng duration của kernel/copy events CUDA từ CUPTI trong **một pass riêng**,
không cộng inclusive CPU events và không coi CUDA event elapsed là kernel work.
Wall inference đo ở pass không profiler, sau warmup, có synchronize.
Cùng checkpoint, config/policy intensity, capture/reference hash; subset seed ghi trong report.
**Chưa có monitoring/switching/segmentation/đa model trong cost scope này.**
Đây không phải GPU work/window hoàn chỉnh cho RL và không chứng minh tiết kiệm điện/tiền.

Giảm 50% điểm chỉ giảm khoảng 8% activity trên hai frame này. Số hộp cũng giảm;
không có quality score đã nghiệm thu để khẳng định hộp mất là false positive hay bỏ sót.
Không chọn winner hoặc chấp nhận cấu hình half là tối ưu. Cả hai sample wall latency
đều vượt một chu kỳ 20 Hz = 50 ms; chưa gọi là real-time 20 FPS.

Checkpoint load strict thành công, không key/shape mismatch. Hai run đầu không AMP; các run AMP được tách riêng bên dưới.
Full run peak allocation khoảng 605 MiB, reserved khoảng 882 MiB; gồm warmup/profiling.
Đây không phải dự đoán VRAM cho full rig + nhiều model đồng thời.

Hình detector-audit.png đã được mở kiểm tra: hộp dự đoán xanh lam được chiếu lên camera
và BEV, tách khỏi hộp engine GT xanh lục. Chỉ có LiDAR vào model; camera/radar trong hình
là dữ liệu ngữ cảnh, không phải sensor fusion của checkpoint này.

## Runtime riêng đã cài

- Python hệ thống 3.10.12 trong `data/runtime/detector-env/`, không đổi `.venv-experiments`.
- Torch 2.1.0+cu121 / torchvision 0.16.0+cu121 / numpy 1.26.4.
- MMCV CUDA wheel 2.1.0, MMEngine 0.10.3, MMDet 3.3.0, spconv-cu120 2.3.6.
- MMDet3D source `fe25f7a51d36e3702f961e198894580d83c4387b` (v1.4.0).
- Native BEV pooling + voxelization ops build thật trên máy, với MAX_JOBS=2.
- GCC/G++ 11, Ninja, Python 3.10 dev headers cài bằng Ubuntu apt; không đổi driver/reboot.
- Compiler CUDA 12.1.105 và header toán từ NVIDIA đặt ở `data/runtime/cuda-12.1/`;
  tar được kiểm SHA256 rồi extract với Python 3.12 data filter. Thư viện toán chỉ extract
  header; runtime đã có trong Torch, không cài trùng tất cả CUDA libraries.
- Open3D và TensorBoard chưa cài vì smoke không dùng renderer/training logger đó.
  `pip check` vì vậy vẫn báo hai dependency vendor thiếu; không coi runtime là toàn bộ
  môi trường train/visualization của upstream. Import và inference cần cho smoke đã qua.

Freeze/build log nằm ở `data/runtime/detector-freeze.txt`, `data/runtime/detector-build.log`.
Snapshot freeze và report nhẹ được lưu tại `eval/detector-linux-2026-10-08/`.

Checkpoint:
`bevfusion_lidar_voxel0075_second_secfpn_8xb4-cyclic-20e_nus-3d-2628f933.pth`
SHA256: `2628f933277774e194932815ea1a5d66a0bd9f69ebc8d9040e8c92760bb6652e`.
File raw ngoài Git, nguồn chính thức [model table](https://github.com/open-mmlab/mmdetection3d/blob/v1.4.0/projects/BEVFusion/README.md).

## Tái lập smoke trên máy hiện tại

```bash
.venv-experiments/bin/python scripts/fetch_detector_checkpoint.py lidar
.venv-experiments/bin/python scripts/setup_detector_cuda.py

CUDA_HOME="$PWD/data/runtime/cuda-12.1" MPLCONFIGDIR=/tmp/p027-detector-matplotlib \
  data/runtime/detector-env/bin/python scripts/smoke_carla_detector.py \
  data/active-sensing/rig-nearby-20261008 --frames 2 --measure-kernels \
  --output data/active-sensing/detector-new

MPLCONFIGDIR=/tmp/p027-matplotlib .venv-experiments/bin/python \
  scripts/preview_sensor_episode.py data/active-sensing/rig-nearby-20261008 \
  --prediction-root data/active-sensing/detector-new \
  --output eval/detector-new/audit.png
```

Thư mục output phải mới. `--keep-fraction 0.5` là subset xác định, không mô phỏng mưa/sương.
`--amp` bật precision mode khác; pilot có số đo riêng, chưa nghiệm thu chất lượng tổng quát.
`--intensity-policy scale_255_approximation` được chuẩn bị nhưng chưa phải calibration;
run trên dùng intensity CARLA raw 0..1, khác phân phối intensity nuScenes.

Một sweep đo thật, đổi CARLA y-right sang LiDAR model y-left, thêm lag=0 cho chính keyframe.
Loại transform pad empty sweeps để tránh biến một capture thành 10 bản sao giả.
Config checkpoint học nhiều sweeps nên smoke một sweep có domain shift; chưa chứng minh quality.
Predicted gravity center và rotation được đổi bằng extrinsic thật sang ego-ground Lab.
Không đưa GT label/box vào forward. Có input SHA và resolved config SHA cho từng run.

## Chưa hoàn tất

- GT coverage cho xe đỗ/prop tĩnh, mapping ontology/ignore và protocol visibility/ROI.
- Camera+LiDAR đã có adapter calibration + smoke riêng. Radar/segmentation còn thiếu; CRN thiếu contract RCS/full compensated
  velocity trên CARLA, không tự điền giả. Trọng số team chưa có trên máy.
- 12–24 profile **validated**; catalog hiện vẫn là ứng viên.
- Episode dài, timeline thời tiết, nhiều map/seed, held-out split; corruption vật lý cảm biến.
- Tổng GPU work/window + monitoring + profile transitions + deadline/miss metric.
- BC/PPO bằng measured replay và so sánh full/min/rule/RL; bridge ROS/online.

Do đó `measured_perception_replay_ready=false`; không dùng report smoke để train RL.

## Pilot mở rộng: 20 frame, 5 cấu hình

Dữ liệu cùng capture Town01/clear/seed 7, 20 frame liên tiếp; một cảnh khoảng 1 giây,
không phải 20 cảnh độc lập. Evidence đầy đủ ở `eval/detector-pilot-2026-10-08/`.

| Cấu hình | Wall TB | Wall p95 | CUDA activity TB | Ghép mục tiêu/frame |
|---|---:|---:|---:|---:|
| LiDAR full FP32 | 118,46 ms | 119,65 ms | 100,51 ms | 72/152 |
| LiDAR half FP32 | 111,21 ms | 113,75 ms | 92,67 ms | 30/152 |
| LiDAR full AMP | 100,44 ms | 102,24 ms | 82,76 ms | 72/152 |
| Camera + LiDAR full FP32 | 545,09 ms | 549,58 ms | 441,74 ms | 89/152 |
| Camera + LiDAR full AMP | 449,64 ms | 458,92 ms | 345,69 ms | 89/152 |

**Ghép mục tiêu** là chẩn đoán hình học class-agnostic: actor vehicle/person đã spawn,
có ít nhất một hit semantic LiDAR GT, tâm nằm trong bán kính 54 m; prediction score ≥ 0,3,
ghép một-một khoảng cách XY ≤ 2 m, tối đa số cặp bằng augmenting paths. Lưu actor ID,
prediction index, sai số tâm và sai số kích thước cho từng cặp. GT visibility lấy từ
semantic LiDAR 64, không chứng minh input LiDAR 32 quan sát đủ vật đó.
Chưa ánh xạ ontology class; không thay metric class-aware của plan bằng metric này.
GT không đầy đủ nên precision/false positives để **null**, không ép thành 0.
152 là số lượt mục tiêu/frame, không phải 152 vật độc lập. Không có confidence interval.

Nhận xét có căn cứ trong capture này:

- Half points giảm khoảng 7,8% CUDA activity nhưng ghép được 30 thay vì 72 mục tiêu/frame.
  Chưa có lý do chấp nhận cấu hình này để đổi lấy mức giảm compute nhỏ đó.
- AMP LiDAR giảm khoảng 17,7% CUDA activity, giữ cùng số cặp ghép trong pilot. Đây là ứng viên
  để kiểm định tiếp; chưa chứng minh mọi prediction/shape/điều kiện đều tương đương.
- Camera+LiDAR ghép được nhiều hơn trên 20 frame, dù hai frame đầu từng bằng LiDAR-only.
  Đổi lại CUDA activity FP32 cao khoảng 4,4 lần và wall ~545 ms. Không kết luận camera vô ích.
- 20 Hz (50 ms) không cấu hình nào đáp ứng. AMP LiDAR vượt chu kỳ 10 Hz ở 13/20 frame,
  nên không gọi là 10 FPS ổn định. LiDAR-only đủ một chu kỳ 5 Hz trong pilot; cả hai CL đều
  vượt 200 ms ở mọi frame. Đây chỉ là inference, chưa cộng monitoring/sync/chuyển model.

Không chọn winner, chưa validate 12–24 profile, `measured_perception_replay_ready=false`.

Chạy lại với output mới, simulator dừng:

```bash
data/runtime/detector-env/bin/python scripts/bench_carla_detector.py \
  data/active-sensing/rig-nearby-20261008 --frames 20 --include-camera \
  --output data/active-sensing/detector-pilot-new
```

## Camera + LiDAR: calibration và artifact identity

Artifact nguồn [model table chính thức](https://github.com/open-mmlab/mmdetection3d/blob/v1.4.0/projects/BEVFusion/README.md):
`bevfusion_lidar-cam_voxel0075_second_secfpn_8xb4-cyclic-20e_nus-3d-5239b1af.pth`.
Nội dung HTTPS hiện tại 167.113.973 byte có SHA256
`e68c6c084d8971f4f879751b0ed3981f575c24ee3cf385a1e39197c26a9bb3ab`,
**không khớp suffix 5239b1af**. Lượt tải đầu bị guard từ chối; hai lần đọc độc lập trùng
full SHA, ZIP CRC không lỗi, MD5 `5873a41fa1ee29b4cdea346be177019a` khớp Content-MD5/ETag
của server chính thức. Sau xác minh, pin nội dung bằng **full SHA** riêng trong downloader;
không cho phép mismatch tùy ý. Provenance giữ `upstream_filename_fingerprint_matches=false`.
Điều này xác định file hiện được phục vụ tại URL, không chứng minh fingerprint release ban đầu.
Không gán metric công bố nuScenes vào run CARLA. Xem camera-lidar-source.json và
camera-lidar-identity-audit.json; trạng thái blocked trong audit là trạng thái lúc kiểm tra
ban đầu, trước khi pin nội dung đã xác minh. Không deserialize file chưa khớp full pin.

Sáu RGB theo thứ tự ghi trong report, extrinsic optical camera ↔ LiDAR từ cùng frame đo thật.
Input 640×360 resize đồng đều 1,1, bottom/center crop về 704×256 bằng ImageAug3D của upstream;
img_aug_matrix được dùng trong projection. Không dùng fixed resize 0,48 của ảnh nuScenes
1600×900 lên ảnh CARLA nhỏ để rồi pad đen phần lớn input. Mọi thay đổi nằm trong resolved config.
Không dùng camera semantic GT vào forward. Strict full checkpoint gồm backbone; script mới
bỏ init ImageNet dư thừa. Peak memory đo CL >2 GiB; không bảo đảm chạy cùng CARLA trên GPU 4 GiB.

## Evidence và engineer review ngay trong bot

Bot → CARLA → mở **Detector trên GPU · pilot 20 frame**. Bảng phân biệt wall, CUDA activity,
số cặp geometry; từng cấu hình có run JSON, GT matching, checkpoint/config hash và chu kỳ vượt hạn.
Đây là archive đọc kết quả, **chưa phải nút thực thi detector từ bot** hoặc policy chọn sensor.

API: `GET /api/v1/experiments/detector-pilot`,
`GET /api/v1/experiments/detector-pilot/artifacts/<member>`,
`GET|POST /api/v1/experiments/detector-pilot/reviews`.
Archive allowlist/checksum toàn bundle; sửa file đo thì trả 409. Review stale hash trả 409.
Review append-only cùng snapshot, không đổi metric/không tự train, danh tính engineer tự khai.
Không có review của người thật được tạo tự động. Production vẫn tuân thủ opt-in Experiments.
Docker context chỉ thêm bundle nhẹ này; raw sensor/weights vẫn ngoài Git/image context.

Frontend lint/build đã qua. Browser automation bị URL policy chặn từ lượt trước;
chưa kiểm tra render tương tác thực trong trình duyệt và không dùng cách khác để vượt chặn.

## Baseline nhẹ PointPillars — đo thêm cùng capture

Checkpoint nuScenes SECFPN từ [model table chính thức v1.4.0](https://github.com/open-mmlab/mmdetection3d/blob/v1.4.0/configs/pointpillars/README.md),
19.778.089 bytes, SHA `f19d00a38e6b775f38a45a9a3ca3ecaec20a5585a3caf44622423e2d5f75d5d0`.
Pin đầy đủ khớp fingerprint tên; strict keys/shapes qua. Không dùng metric nuScenes công bố
làm metric CARLA; không thay thế checkpoint/metric Lab cũ.

```bash
.venv-experiments/bin/python scripts/fetch_detector_checkpoint.py pointpillars
CUDA_HOME="$PWD/data/runtime/cuda-12.1" data/runtime/detector-env/bin/python \
  scripts/bench_carla_detector.py data/active-sensing/rig-nearby-20261008 \
  --family pointpillars --frames 20 --output data/active-sensing/pp-pilot-new
```

| PointPillars | Wall mean ms | CUDA mean ms | Ghép target/frame |
|---|---:|---:|---:|
| Full FP32 | 82,27 | 67,36 | 91/152 |
| Half points FP32 | 71,19 | 56,71 | 57/152 |
| Full AMP | 57,45 | 42,45 | 91/152 |

Ba variant đều vượt chu kỳ 20 Hz ở 20/20 frame, không vượt chu kỳ 10 Hz trong pilot.
Chỉ là inference riêng, CARLA dừng; không chứng minh throughput online hay deadline mọi cảnh.
So với BEVFusion LiDAR AMP, PP AMP ít wall hơn khoảng 42,8%, CUDA activity ít hơn khoảng 48,7%
trong các phiên đo này. 91 so với 72 cặp ghép không phải so mAP hoặc chứng minh an toàn.
Các phiên nối tiếp, chưa randomize/lặp benchmark hoặc kiểm định nhiều cảnh.

**Chi tiết adapter quan trọng:** upstream PointPillars nuScenes `LoadPointsFromMultiSweeps`
chọn `[0,1,2,4]`, HardVFE nhận XYZ + time lag, **không nhận intensity** ở kênh thứ tư.
Script giữ đúng contract đó nhưng chỉ cung cấp một sweep có lag 0; không giả 10 sweep.
BEVFusion giữ XYZ/intensity/lag đủ 5 kênh. Config PP range ±50 m, BEVFusion ±54 m;
diagnostic vẫn dùng ROI XY 54 m chung, không đổi denominator để làm PP trông tốt hơn.

Sampling đã thống nhất gate + replay bằng `numpy-default-rng-sorted-subset-v1`,
seed gốc + frame_id, subset indices được sort. Artifact pilot trước vẫn giữ nguyên;
ABI mới cho cùng subset với script đo trước, khác gate stdlib Random cũ.
Không trộn những bảng replay cũ sinh từ gate cũ vào training mà không xuất lại input SHA.

Archive bot mở rộng thành 8 variant, có `pointpillars-source.json`, `gt-coverage-audit.json`
và `pilot-comparison-8.png`. `prior-summary.json`/`prior-bundle-manifest.json` giữ provenance
bộ 5 variant ban đầu; hash snapshot mới thay đổi, review cũ vẫn giữ snapshot riêng.

## Audit GT và điểm trả về thực tế

```bash
.venv-experiments/bin/python scripts/audit_carla_gt.py \
  data/active-sensing/rig-nearby-20261008 --output data/active-sensing/gt-audit-new.json
```

Taxonomy được kiểm từ enum CARLA 0.9.16, không dùng ID nhãn phiên bản cũ.
Trong capture này không có semantic target ID không được ghi actor GT **trên bề mặt semantic
LiDAR đã hit**. Điều này không chứng minh toàn scene có annotation đầy đủ.
Có 12 lượt actor/frame được reference semantic thấy nhưng 32-channel không có điểm nằm
trong oriented box GT, còn 64-channel có 2 lượt. Điểm trong box là đếm hình học, không phải
label point-aligned hoặc bảo đảm detectability. Không loại những target này để sửa recall.

Xem [protocol GT đề xuất](DETECTION_GT_PROTOCOL.vi.md) trước khi xuất measured replay/train.
