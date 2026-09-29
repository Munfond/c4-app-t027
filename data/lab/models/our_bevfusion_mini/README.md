# our_bevfusion_mini — BEVFusion trained by us on nuScenes-mini

Two checkpoints trained by this project on **nuScenes-mini TRAIN** (323 keyframes, 8 scenes), evaluated on **mini VAL** (81 keyframes, 2 scenes, disjoint from TRAIN).
This is a pipeline-validation artifact, **not a benchmark**. Do not quote these numbers as nuScenes results.

| File | What it is |
|---|---|
| `our_lidar_mini.pth` | Stage A. BEVFusion LiDAR-only, trained **from scratch** (no checkpoint loaded), 15 epochs. Weights only. |
| `our_bevfusion_mini.pth` | Stage B. BEVFusion Camera+LiDAR. LiDAR branch initialised from **our** `our_lidar_mini.pth`; Swin-T image backbone from the official ImageNet weights (standard BEVFusion workflow); 7 epochs. Weights only. |

No official BEVFusion LiDAR or LiDAR+Camera checkpoint is loaded by either training run (config gate in the Stage B log lists every `.pth` string in the resolved config: our LiDAR checkpoint and the Swin-T ImageNet weights only).

## Results (nuScenes-mini VAL, 81 samples)

| Model | Training data | mAP | NDS | mATE | mASE | mAOE | mAVE |
|---|---|---|---|---|---|---|---|
| Official pretrained LiDAR | official (trainval) - CONTAMINATED on mini VAL | 0.543 | 0.563 | 0.41 | 0.44 | 0.47 | 0.45 |
| Official pretrained LiDAR+Camera | official (trainval) - CONTAMINATED on mini VAL | 0.570 | 0.576 | 0.41 | 0.45 | 0.50 | 0.42 |
| **Our trained LiDAR** (last epoch, 15) | mini TRAIN only, from scratch | 0.210 | 0.232 | 0.61 | 0.64 | 1.16 | 0.88 |
| **Our trained LiDAR+Camera** (last epoch, 7) | our LiDAR init + Swin-T ImageNet | 0.192 | 0.207 | 0.62 | 0.61 | 1.14 | 0.99 |

Per-class AP (2 m centre-distance threshold):

| Model | car | truck | bus | pedestrian | motorcycle | bicycle | traffic_cone | trailer | constr. veh. | barrier |
|---|---|---|---|---|---|---|---|---|---|---|
| Official pretrained LiDAR | 0.90 | 0.79 | 1.00 | 0.92 | 0.62 | 0.49 | 0.71 | 0.00 | 0.00 | 0.00 |
| Official pretrained LiDAR+Camera | 0.92 | 0.80 | 1.00 | 0.92 | 0.68 | 0.58 | 0.80 | 0.00 | 0.00 | 0.00 |
| Our trained LiDAR | 0.60 | 0.31 | 0.40 | 0.74 | 0.07 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Our trained LiDAR+Camera | 0.62 | 0.18 | 0.36 | 0.74 | 0.02 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

Full numbers (including best-by-val rows and re-runs) are in `metrics.json` and `comparison_table.csv`.

### How to read this table

* **Data contamination (official rows).** The official checkpoints were trained on nuScenes **trainval**, and the mini scenes are part of trainval. Their mini-VAL scores are therefore optimistic and are not comparable with ours. Our models never saw the mini VAL scenes.
* **Not a full-nuScenes benchmark.** 81 samples / 2 scenes. Trailer, construction_vehicle and barrier have **no GT in mini VAL**, so their AP is 0 for every model and caps mAP at 0.70. Differences of a few mAP points between our two models are within what 81 samples can resolve.
* **Official numbers are non-deterministic by about ±0.003.** Frozen run: LiDAR 0.5431/0.5626, LiDAR+Cam 0.5702/0.5755. Re-run in the rebuilt frozen environment: 0.5450/0.5657 and 0.5720/0.5761 (`environment.txt`, `metrics.json`).
* **Primary rows use the last epoch.** `epoch_ckpts/*_best_by_val_NDS.pth` were picked by mini-VAL NDS (LiDAR: mAP 0.214 / NDS 0.238; Fusion: 0.200 / 0.213) and are therefore optimistic.

### Findings

1. Training from scratch on 323 samples reaches mAP 0.21 (about 39% of the official LiDAR model on the same, contaminated, val set). Validation was **still rising** when the schedule ended (NDS 0.092 at epoch 2 to 0.239 at epoch 14, `training_curves/stageA_val_metrics.png`), so Stage A is under-trained, not converged. Orientation (mAOE 1.16) and velocity (mAVE 0.88) are barely learned; classes with few training instances (bicycle, traffic_cone, motorcycle) are near 0.
2. **Camera fusion did not help at this data scale.** Stage B train loss fell below Stage A's (1.10 vs 1.35) while VAL got slightly worse (mAP 0.192 vs 0.210). A 2-epoch smoke run of Stage B already reached mAP 0.197 / NDS 0.222, i.e. the same level, so the extra epochs did not add generalisation. Most likely the camera branch overfits 323 samples. The official model's fusion gain (+0.03 mAP on this val set) comes from trainval-scale training, which we cannot reproduce here.
3. Both checkpoints reload and run inference correctly: the final evaluation loads the exported weights-only `.pth` from disk (no `size mismatch` / missing / unexpected keys) and produces the metrics above. Predictions are in `predictions/`.

## Training setup (what was actually run)

| | Stage A (LiDAR) | Stage B (Camera+LiDAR) |
|---|---|---|
| Base config | mmdet3d v1.4.0 `bevfusion_lidar_voxel0075_second_secfpn_8xb4-cyclic-20e_nus-3d` | `bevfusion_lidar-cam_voxel0075_second_secfpn_8xb4-cyclic-20e_nus-3d` |
| Our config | `config/our_lidar_mini.py` | `config/our_bevfusion_mini.py` |
| Init | random | LiDAR branch = our Stage A; Swin-T = official ImageNet |
| GPU | one Tesla T4 (the Kaggle T4 machine exposes two; `CUDA_VISIBLE_DEVICES=0`) | same |
| Precision | AMP (`--amp`) | AMP |
| Batch | **1 per iteration, gradient accumulation 4 (effective batch 4)** | same |
| Optimiser | AdamW, wd 0.01, grad-clip 35; LR 3e-5 warm-up to 3e-4 then cosine decay | peak LR 1.05e-4, 200-iter linear warm-up, cosine decay |
| Epochs / iterations | 15 epochs x 1630 it (CBGS-resampled mini TRAIN) | 7 epochs x 1630 it |
| Speed | 0.43 s/it, about 3 h 05 min | 0.84 s/it, about 2 h 45 min |
| Checkpointing | every epoch during training (in the Kaggle work dir); exported: final, best-by-val, epochs 1/5/10/15 (A) and 1/5 (B) | same |
| Validation | every 2 epochs + final, mini VAL | same |
| Smoke run first | 2 epochs, passed (loss finite, decreasing 211 to 5.7; checkpoint reloaded and evaluated) | 2 epochs, passed |

Automatic smoke gate (`training_logs/*/smoke_report.json`): finite loss, grad-norm non-finite fraction < 20 %, loss decreasing, checkpoint written, reload-and-evaluate without key mismatch, and (Stage B) the expected checkpoint actually loaded. Retry ladder for OOM / instability was in place (allocator settings, fewer workers, gradient checkpointing, lower LR, AMP off); it was not needed: both smoke runs passed on the first attempt, peak memory 2.0 GB (A) and 4.8 GB (B).

## Deviations from the "frozen" pipeline (disclosed)

* **One source patch, training path only.** mmdet3d v1.4.0's `ObjectSample` uses `np.long`, which numpy 1.26 removed. Replaced by `np.int64` in `dbsampler.py` (`config/numpy_alias_patch.diff`, the only file touched). No dependency was changed, and inference code is unaffected.
* **Environment location.** The frozen environment is repacked as `env_bevfusion.tar.gz` (Kaggle notebook `canhquang/bev-real-freeze`, sha256 in `environment_archive_SHA256.txt`) and restored to `/tmp/l3`, not `/kaggle/working/envs/bevfusion`, to keep a 3+ GB env out of the notebook output.
* **Effective batch 4** (see table) rather than a literal batch of 1 per optimiser step.
* **Schedule is short by necessity** (about 3 h per stage). It is a budget-driven mini schedule, not the official 20-epoch trainval schedule.

## Layout

```
our_lidar_mini.pth, our_bevfusion_mini.pth     final weights (last epoch)
epoch_ckpts/                                    best-by-val (optimistic) and selected per-epoch weights
config/                                         our configs, upstream v1.4.0 base configs, drivers, numpy patch
metrics.json, comparison_table.csv              all numbers (incl. per-epoch VAL, per-class AP, official re-runs)
training_logs/{lidar_stageA,fusion_stageB}/     full logs, scalars.json, smoke + full-train reports
training_curves/                                loss / lr / VAL metrics per stage
demo_images/                                    9 real val samples per stage: 6 cameras + 3D boxes + LiDAR BEV, GT vs prediction
predictions/                                    nuScenes-format results for both models (last + best)
environment.txt                                 pip/conda freeze, GPU, CUDA, mmdet3d commit
SHA256SUMS.txt                                  checksums of everything above
```

`demo_images/`: left BEV = our model, right BEV = official model; camera panels show the right-panel (official) predictions. Green = GT, red = prediction (score >= 0.3).

Reproduce: Kaggle notebooks `bev-real-freeze` (environment) then `bev-real-train-a` then `bev-real-train-b` (all private, account `canhquang`).
