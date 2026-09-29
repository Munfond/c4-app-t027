# occupancy — `our_occupancy.pth` (Stage F: learned BEV occupancy, trained on nuScenes-mini TRAIN)

A 1.93 M-parameter U-Net that turns **one LiDAR keyframe + the five radar keyframes** into a 200 x 200 BEV occupancy grid (ego frame, 0.5 m cells, +/-50 m; rows +x forward, columns +y left) with three classes: **free / static / object**. `our_occupancy.pth` is the LiDAR+radar variant; `variants/` holds LiDAR-only and radar-only for the sensor-dependency ablation. Trained from scratch (no checkpoint), 323 TRAIN keyframes, 80 epochs, batch 8, AdamW (2e-3, one-cycle), seed 0, about 5.5 min on one Tesla T4, 1.1 GB peak memory, 3.75 ms per frame. Camera is not used.

## Labels (this is the part to read carefully)

* **object** = rasterised footprints of the annotated boxes of the 10 evaluated categories: real human GT.
* **static** = cells hit by obstacle-height LiDAR points (0.3 < z < 3.0 m above the ego ground plane) in >= 4 of 11 ego-motion-compensated sweeps (keyframe + 10 previous), excluding object footprints: **pseudo-GT derived from LiDAR**, not human annotation. nuScenes-mini has no dense occupancy GT.
* **free** = everything else, which also contains cells that were never observed (occluded / out of range); the label cannot separate them.
* The model input is a single keyframe, which is a subset of the data the static label is built from. Part of any gain over a classical grid therefore reflects that the label and the learned input are related, not only "learning".

All label thresholds and training settings were fixed before training; the last-epoch model is reported (no VAL-based selection).

## Results, mini VAL (81 samples; strict per-cell metrics unless marked tol1 = 1-cell tolerance)

| System | IoU occupied (static+object) | Precision | Recall | Precision tol1 | Recall tol1 |
|---|---|---|---|---|---|
| Classical LiDAR occupancy (project `buildBevOccupancy`, single sweep) | 0.289 | 0.714 | 0.327 | 0.879 | 0.580 |
| Classical radar hits (project `rasterizeRadarBev`) | 0.099 | 0.338 | 0.123 | 0.677 | 0.243 |
| Rule: any obstacle-height LiDAR point (single sweep) | 0.384 | 0.751 | 0.440 | 0.924 | 0.685 |
| **Learned LiDAR + radar (`our_occupancy.pth`)** | **0.423** | 0.686 | 0.524 | 0.909 | 0.711 |
| Learned LiDAR only | 0.410 | 0.679 | 0.508 | 0.907 | 0.700 |
| Learned radar only | 0.098 | 0.240 | 0.142 | 0.497 | 0.243 |

Per-class IoU (free / static / object) and mIoU: LiDAR+radar 0.960 / 0.490 / 0.196, **mIoU 0.549**; LiDAR only 0.959 / 0.483 / 0.160, mIoU 0.534; radar only 0.929 / 0.066 / 0.060, mIoU 0.352.

Object channel against detection-derived footprints (score >= 0.5, from Stages A-D): official Camera+LiDAR IoU 0.475, fused Camera+LiDAR x Camera+Radar 0.587 (both contaminated by trainval training), learned occupancy (object class) 0.196 (precision 0.62, recall 0.22).

## What this does and does not show

1. The learned grid beats the aligned single-sweep rule by +0.039 IoU (LiDAR+radar) and +0.026 (LiDAR only), and the project's classical grid (toolbox run) by +0.13. The classical number is **not** "classical is inaccurate": that grid is defined differently (ground clearance 0.15 m, >= 2 points per cell, free-space semantics), so it disagrees with a label built from a height rule. The like-for-like reference is the rule row.
2. Radar adds +0.013 IoU over LiDAR-only; radar alone is nearly useless here (0.098; a few hundred sparse points per frame). With one seed and 81 samples, differences of about 0.01 are not established.
3. **The occupancy net is a weak object detector** (object IoU 0.196 vs 0.475-0.587 for detection footprints). Use the detection lists for objects; use this grid for static structure and as a dense input for the risk pipeline.
4. It overfits: mini-VAL mIoU peaked around epoch 40 (0.560) and ended at 0.549 while train loss kept falling (0.38 to 0.28).
5. Not comparable to Occ3D / SurroundOcc / TPVFormer mIoU (different labels, classes, resolution, data). Not a full-nuScenes benchmark.
6. No temporal information, no camera, occluded space not modelled.

## Verified

TRAIN, CHECKPOINT, RELOAD (a fresh model loaded from the saved file reproduces all 81 predictions exactly, all three variants), INFERENCE, EVALUATION, EXPORT, MATLAB import (`matlab/load_occupancy.m`, axes checked against the matplotlib rendering). Environment: the frozen BEVFusion environment (`environment.txt`; torch 2.1.0+cu121). Scripts in `config/`; run on Kaggle as notebook `bev-real-occ`.

Files: `metrics.json` (all tables), `training_logs/occupancy_metrics.json` (per-epoch loss, per-variant metrics), `training_curves/`, `demo_images/` (label vs classical vs learned, samples 5 / 31 / 61), `matlab/occupancy_predictions.mat` (81 x 200 x 200 grids: label, three learned variants, classical LiDAR occupancy, classical radar hits).
