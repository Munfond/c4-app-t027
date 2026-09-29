# Model zoo — status (nuScenes-mini; every number is mini VAL, 81 samples / 2 scenes, NOT a full-nuScenes benchmark)

"Official" = checkpoint released by the model authors, trained on nuScenes **trainval**, which contains the mini scenes, so its mini-VAL scores are **contaminated** (a pretrained integration reference, not evidence of generalization). "Own" = trained by this project on mini TRAIN only.

| Branch | Own checkpoint | Own mAP / NDS | Official pretrained reference (contaminated) | Status |
|---|---|---|---|---|
| LiDAR-only | `lidar_only/our_lidar.pth` | 0.210 / 0.232 (15 epochs, from scratch) | BEVFusion-L 0.543 / 0.563 | TRAIN, CHECKPOINT, RELOAD, INFERENCE, EVALUATION, EXPORT, MATLAB: PASS |
| Camera+LiDAR | `camera_lidar/our_bevfusion.pth` | 0.192 / 0.207 (7 epochs; LiDAR branch from our LiDAR ckpt, Swin-T ImageNet) | BEVFusion 0.570 / 0.576 | PASS (own result is below own LiDAR-only; camera branch overfits 323 samples) |
| Camera+Radar | **not created** (optional, not started) | - | CRN R18 0.433 / 0.476 (`camera_radar/crn_r18_pretrained/`) | Pretrained inference, evaluation, visualization, ego export, MATLAB: PASS. Own training: NOT DONE |
| 3-sensor hybrid | no network (object-level late fusion) | official CL + CRN: 0.574 / 0.578; our CL + CRN: 0.436 / 0.415 | - | PASS as a baseline; no demonstrable gain over Camera+LiDAR alone (`../fusion/README.md`) |
| Classical vs Learned | - | - | - | E PASS on 81 samples (`../stage_e/README.md`); re-run with the real MATLAB toolboxes after they were installed (shim run agrees: F1 0.459 vs 0.460) |
| Learned occupancy | `occupancy/our_occupancy.pth` (U-Net, LiDAR 1 sweep + radar -> free/static/object BEV grid) | mIoU 0.549, occupied IoU 0.423 vs aligned rule 0.384 and project classical 0.289 (static labels are LiDAR-derived pseudo-GT; object labels are real GT) | none used (SurroundOcc / TPVFormer: camera-only, Baidu / Tsinghua hosting, trainval-trained, no GT in mini) | TRAIN, CHECKPOINT, RELOAD, INFERENCE, EVALUATION, EXPORT, MATLAB: PASS. Weak on objects (IoU 0.196 vs 0.475-0.587 for detection footprints); overfits after ~epoch 40; no camera (`occupancy/README.md`) |
| Temporal / flow | `temporal_flow/our_flow.pth` (temporal U-Net: occupancy(t) + ground-velocity flow + future occupancy) | occupancy mIoU 0.569 (1 frame: 0.552); flow EPE 3.52 m/s vs zero-flow 3.79 | none | Chain TRAIN..MATLAB: mechanical PASS. **Learned flow NOT usable** (7% better than zero flow, 1.7 m/s false flow on static objects, worsens the future forecast). Use detection-derived flow (EPE 1.26-1.74, contaminated) for risk. Temporal input does help occupancy; ego compensation is necessary (`temporal_flow/README.md`) |

Layout per branch: checkpoint, `config/`, `environment.txt`, `training_logs/`, `training_curves/`, `metrics.json`, `demo_images/`, `predictions/`, `README.md`. `our_bevfusion_mini/` is the original combined artifact (kept unchanged; it also holds the per-epoch checkpoints and the 4-row comparison table). Copies in `lidar_only/` and `camera_lidar/` are byte-identical to it (same weights, same metrics).

Environments: BEVFusion stack `envs/bevfusion` (`environment.txt`); Camera+Radar stack `envs/camera_radar` (`camera_radar/environment_camera_radar.txt`); both packed and checksummed on Kaggle (`bev-real-freeze`, `bev-real-cr-env`).

Common export format (all branches, MATLAB-ready): `sample_idx, class, x, y, z, w, l, h, yaw, vx, vy, score`; x forward, y left, z up, yaw CCW from +x. Files: `../exports/L3E/`, `../fusion/unified/`.
