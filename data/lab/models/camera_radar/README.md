# camera_radar — Stage C (Camera + Radar), pretrained-first

Status: **C0 dataset audit PASS, C1 model audit done, C2 pretrained inference PASS (evaluate + visualize + export).**
C3 own training has **not** been run (optional by decision; see "Not done").

## C0. Radar dataset audit (nuScenes-mini from the Kaggle dataset `aadimator/nuscenes-mini`)

Real files only, nothing synthesized. Full numbers: `radar_audit.json`; visual check: `radar_lidar_ego_sample.png` (radar points line up with LiDAR structure in the ego frame).

| Radar | keyframe pcd | sweep pcd | table entries missing on disk | mean points / keyframe |
|---|---|---|---|---|
| RADAR_FRONT | 404 | 2231 | 0 | 120 |
| RADAR_FRONT_LEFT | 404 | 2282 | 0 | 32 |
| RADAR_FRONT_RIGHT | 404 | 2269 | 0 | 53 |
| RADAR_BACK_LEFT | 404 | 2230 | 0 | 106 |
| RADAR_BACK_RIGHT | 404 | 2231 | 0 | 109 |

* Calibration: 5 distinct extrinsics, modality `radar`, mounting positions and yaw angles as expected for the nuScenes rig.
* Timing: radar ~13.3 Hz. Keyframe radar timestamps differ from LiDAR by -37 to +37 ms (std ~21 ms; asynchronous sensors); cameras lag LiDAR by 1 to 48 ms.
* Fields: all 18 standard nuScenes fields incl. `rcs`, `vx_comp`, `vy_comp`, `invalid_state`, `ambig_state`, `dyn_prop`. `z` is always 0 (radar is 2D). The hardware caps each frame at 125 points; FRONT_LEFT/RIGHT are sparse in this mini subset (as low as 1 point in some frames).
* Split used: `mini_train` 323 keyframes (8 scenes), `mini_val` 81 keyframes (scene-0103, scene-0916); disjoint.

## C1. Model choice (audit, not preference)

| Candidate | Result |
|---|---|
| `BEVFusion-R` | No public repository found with this name/scope. Not usable. |
| **CRN** (Camera Radar Net, ICCV 2023) | MIT license; official checkpoints on GitHub Releases (R18, R50); nuScenes-native; R18 has 37.2 M params (T4-feasible); 3D boxes with velocity. **Chosen: `CRN_r18_256x704_128x128_4key`.** |
| RCBEVDet, HyDRa | Weights on Google Drive, heavier stacks; not needed once CRN passed. Not evaluated. |

CRN stack is old (Python 3.8, torch 1.9.1+cu111, mmcv-full 1.6.0, mmdet 2.25.2, vendored mmdet3d 1.0.0rc4, two custom CUDA ops), so it lives in its **own environment** and does not touch the BEVFusion environment (`envs/camera_radar`, packed as `env_camera_radar.tar.gz`, sha256 in `SHA256SUMS_camera_radar.txt`, full freeze in `environment_camera_radar.txt`). CUDA 11.1 toolkit and gcc-10 were installed only to compile the ops. Pinned commit: `5e9d2fa2f91c714b297e75ca666d27fc4ad0d13d`.

## C2. Pretrained inference on nuScenes-mini VAL (81 samples)

Checkpoint `CRN_r18_256x704_128x128_4key.pth` (sha256 in `logs/crn_r18_checkpoint_sha256.txt`), no fine-tuning.

| | mAP | NDS | mATE | mASE | mAOE | mAVE | mAAE |
|---|---|---|---|---|---|---|---|
| CRN R18 (official pretrained) | 0.433 | 0.476 | 0.575 | 0.471 | 0.640 | 0.425 | 0.293 |

AP @ 2 m: car 0.74, truck 0.69, bus 0.76, pedestrian 0.60, motorcycle 0.51, bicycle 0.34, traffic_cone 0.68, trailer / construction_vehicle / barrier 0.00 (**no GT of these classes in mini VAL**, so mAP is capped at 0.70).

**Caveats (do not skip):**
* **Contaminated.** CRN was trained on nuScenes trainval, which contains the mini scenes. This is a *pretrained integration reference*, not evidence of generalization, and not comparable to our own trained models.
* 81 samples / 2 scenes; not a full-nuScenes benchmark. The authors' own full-val number for this checkpoint is NDS 0.542 / mAP 0.449 (their README); our mini number is a different and smaller set.
* Compare with the other pretrained references on the same 81 samples: official BEVFusion Camera+LiDAR mAP 0.570 / NDS 0.576 (also contaminated).

## What was changed to run on mini (`config/crn_mini_patch.diff`, plus new scripts under `scripts/`)

* `scripts/gen_info_mini.py`: CRN's own `generate_info`, fed `splits.mini_train` / `splits.mini_val`.
* `gen_radar_bev_mini.py`, `gen_radar_pv_mini.py`, `gen_depth_gt_mini.py`: identical to CRN's scripts except the nuScenes split constant (`v1.0-mini`) and `Pool(4)`.
* `exps/base_exp.py`: evaluator constructed with `version='v1.0-mini'` (CRN's evaluator already maps it to `mini_val`).
* No CRN model/weights/dependency changes. Pre-processing output: 404 BEV radar files (mean 2522 points/sample over 8 sweeps x 5 radars), 2424 perspective-radar files, 2424 depth-GT files.

## Export (common ego format, used by Stage D)

`exports/L3E/pred_camera_radar_ego.csv` and `camera_radar_predictions.mat` (`sample_idx, class, x, y, z, w, l, h, yaw, vx, vy, score`; x forward, y left, z up, yaw CCW from +x; same `sample_idx` as the LiDAR exports). Check: 83.5% of boxes with score > 0.3 fall within 2 m of a same-class GT box in the ego frame (LiDAR-based models: ~95%). MATLAB loader verified headless: `load_camera_radar.m`.

## Not done (explicit)

* **C3 own Camera+Radar training.** Feasible on one T4 (R18, ImageNet-initialised ResNet-18, no official fusion checkpoint needed) but needs a dedicated Lightning driver (checkpoint every epoch, CSV metrics) and hours of GPU; kept OPTIONAL as agreed so it does not block Stage D.
* No claim is made that the radar branch generalizes; the numbers above are contaminated references.
