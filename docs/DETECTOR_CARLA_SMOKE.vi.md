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

Checkpoint load strict thành công, không key/shape mismatch. Smoke không AMP.
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
`--amp` chỉ bật precision mode khác, chưa được nghiệm thu trong các run trên.
`--intensity-policy scale_255_approximation` được chuẩn bị nhưng chưa phải calibration;
run trên dùng intensity CARLA raw 0..1, khác phân phối intensity nuScenes.

Một sweep đo thật, đổi CARLA y-right sang LiDAR model y-left, thêm lag=0 cho chính keyframe.
Loại transform pad empty sweeps để tránh biến một capture thành 10 bản sao giả.
Config checkpoint học nhiều sweeps nên smoke một sweep có domain shift; chưa chứng minh quality.
Predicted gravity center và rotation được đổi bằng extrinsic thật sang ego-ground Lab.
Không đưa GT label/box vào forward. Có input SHA và resolved config SHA cho từng run.

## Chưa hoàn tất

- GT coverage cho xe đỗ/prop tĩnh, mapping ontology/ignore và protocol visibility/ROI.
- Camera+LiDAR/radar/segmentation adapter và smoke. CRN thiếu contract RCS/full compensated
  velocity trên CARLA, không tự điền giả. Trọng số team chưa có trên máy.
- 12–24 profile **validated**; catalog hiện vẫn là ứng viên.
- Episode dài, timeline thời tiết, nhiều map/seed, held-out split; corruption vật lý cảm biến.
- Tổng GPU work/window + monitoring + profile transitions + deadline/miss metric.
- BC/PPO bằng measured replay và so sánh full/min/rule/RL; bridge ROS/online.

Do đó `measured_perception_replay_ready=false`; không dùng report smoke để train RL.
