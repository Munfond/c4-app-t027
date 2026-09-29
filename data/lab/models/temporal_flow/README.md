# temporal_flow — `our_flow.pth` (Stage G: temporal U-Net, occupancy(t) + ground-velocity flow + future object occupancy)

**Status: the pipeline passes end to end, but the learned flow is NOT usable.** Read "Results" before using anything from this folder.

Model: 1.93 M-parameter U-Net, input = 4 consecutive keyframes (t-3 ... t, 0.5 s apart), each 7 BEV channels (LiDAR 1 sweep + radar, as in Stage F), history frames warped into the current ego frame with the real ego poses (bilinear). Outputs on the 200 x 200 grid (ego frame at t, 0.5 m cells, +/-50 m; rows +x forward, columns +y left): occupancy(t) (free / static / object), **flow** (vx, vy in m/s), future object occupancy at +0.5 s and +1.0 s. Trained from scratch on mini TRAIN only (323 keyframes), 60 epochs, batch 8, AdamW 2e-3 (one-cycle), seed 0, about 4.3 min on one Tesla T4, 3.8 ms per frame. `our_flow.pth` is the 4-frame variant; `variants/` has 1 frame, 2 frames, and 4 frames **without** ego-motion compensation.

## Labels

* **Flow** = the annotated object's **ground velocity** (m/s) expressed in the current ego axes, so parked objects are ~0 and moving objects are not (the definition in the project's `FLOW_CONTRACT`; not velocity relative to ego). Real GT: finite difference of each instance's annotated positions (nuScenes devkit rule, max gap 1.5 s). Cells with undefined velocity are excluded.
* **Future occupancy** = footprints of annotated objects at the next 1 / 2 keyframes, world-anchored, expressed in the ego frame at t.
* Occupancy(t) labels are those of Stage F (static = LiDAR-derived pseudo-GT, object = annotated footprints).
* Mini VAL: 81 keyframes, 11147 moving-object cells (speed >= 0.3 m/s, median 3.3 m/s) and 76524 static-object cells.

## Results (mini VAL, 81 samples; single seed; all settings fixed before training, last epoch reported)

Occupancy(t) improves with temporal context, and needs ego compensation:

| Variant | mIoU | IoU occupied |
|---|---|---|
| 1 frame | 0.552 | 0.429 |
| 2 frames | 0.568 | 0.463 |
| **4 frames (`our_flow.pth`)** | **0.569** | **0.465** |
| 4 frames, no ego-motion compensation | 0.533 | 0.418 (worse than a single frame) |

Flow (EPE in m/s on the 11147 moving cells; angle only where truth >= 0.5 m/s):

| Source | EPE moving | Angle median | Static-object false flow | Note |
|---|---|---|---|---|
| Zero flow (predict no motion) | 3.79 | - | 0.00 | the bar to beat |
| Learned, 1 frame | 4.32 | 91 deg | 1.35 | |
| Learned, 2 frames | 3.64 | 62 deg | 1.40 | |
| **Learned, 4 frames (`our_flow.pth`)** | **3.52** | **50 deg** | **1.70** | only 7% below zero flow |
| Learned, 4 frames, no ego compensation | 3.79 | 72 deg | 1.39 | |
| Detection-derived, official Camera+LiDAR (score >= 0.5) | 1.74 | 4.8 deg | 0.004 | covers 62% of moving cells (EPE 0.82 where covered); contaminated |
| Detection-derived, fused Camera+LiDAR x Camera+Radar | 1.26 | 3.7 deg | 0.006 | covers 74% (EPE 0.71 where covered); contaminated |
| Detection-derived, our Camera+LiDAR (Stage B, score >= 0.3) | 3.75 | 33.8 deg | 0.044 | covers only 25% |

"Detection-derived" = each detected box rasterised with its predicted velocity (converted to ground velocity in ego axes); uncovered cells count as zero flow in the EPE.

Future object occupancy IoU, +0.5 s / +1.0 s (4-frame model): direct future head 0.146 / 0.119; persistence of its own predicted objects 0.169 / 0.157; **extrapolating predicted objects with the predicted flow 0.133 / 0.098**; oracle references using GT objects: persistence 0.774 / 0.700, GT-flow extrapolation 0.882 / 0.802. The project's flow-warped test (moving footprint IoU, shifted by predicted flow vs not shifted): 0.071 vs 0.079 at 0.5 s and 0.040 vs 0.057 at 1.0 s, i.e. shifting with the learned flow makes it worse.

## What this means

1. **Do not use the learned flow.** It is barely better than predicting zero, it puts about 1.7 m/s of false flow on parked objects, and it degrades the future forecast. The project's Level-1 acceptance values (simulation: EPE <= 0.5 m/s, median angle <= 20 deg, static false flow <= 0.2 m/s, flow-warped gain >= +0.05 / +0.10) are all missed; they were set for a clean simulated scene, but the gap is large enough that the conclusion does not depend on that.
2. **Use detection-derived flow for the risk pipeline.** Rasterising detector velocities gives direction within about 4-5 deg and ~0 false flow, but the numbers above come from checkpoints trained on trainval (contaminated) and cover only 62-74% of moving cells. The same recipe with our own mini-trained detector is no better than zero flow (25% coverage), so this is only as good as the detector behind it.
3. **What did work:** temporal input raises occupancy quality (+0.017 mIoU, +0.036 IoU vs one frame), direction awareness of the flow grows with frames (91 -> 62 -> 50 deg), and ego-motion compensation is necessary (uncompensated input is worse than one frame), matching the project's Phase 8/9 conclusion.
4. Likely causes (hypotheses, not tested): 323 training frames with few distinct moving vehicles; keyframes 0.5 s apart, so a car moves 1.6 m (3 cells) or more between frames, beyond what a small CNN learns to match from this little data; no explicit motion cue (cost volume, correlation); no camera. Untested ideas: use LiDAR/radar **sweeps** (0.05-0.1 s apart) as the temporal stack; a correlation layer; more data. Do not treat these as done.
5. Not a benchmark; 81 samples, one seed. No Occ3D / nuScenes-flow protocol is implied.

## Verified

TRAIN, CHECKPOINT, RELOAD (all four variants reproduce their outputs exactly from the saved file), INFERENCE, EVALUATION, EXPORT and MATLAB import (`matlab/flow_predictions.mat` follows the Level-1 flow contract: `flowX`/`flowY` single m/s, NaN where the model predicts free; `matlab/load_flow.m` checked headless). That is a mechanical PASS of the chain, not a quality PASS for the flow.

Files: `metrics.json` (learned vs reference tables), `training_logs/flow_metrics.json` (per-epoch loss and every metric per variant), `training_curves/`, `demo_images/` (the three VAL samples with the most motion: GT vs learned vs detection-derived), `config/` (scripts; Kaggle notebook `bev-real-flow`), `environment.txt` (frozen BEVFusion environment, torch 2.1.0+cu121).
