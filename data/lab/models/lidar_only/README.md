# lidar_only — `our_lidar.pth` (BEVFusion LiDAR-only, trained from scratch on nuScenes-mini TRAIN)

Byte-identical copy of `../our_bevfusion_mini/our_lidar_mini.pth` (Stage A). 15 epochs x 1630 iterations (CBGS-resampled mini TRAIN, 323 keyframes), one Tesla T4, batch 1 per iteration with gradient accumulation 4 (effective 4), AMP, AdamW (3e-5 warm-up to 3e-4, cosine), about 3 h 05 min. No checkpoint loaded.

Mini VAL (81 samples): **mAP 0.210, NDS 0.232** (mATE 0.61, mASE 0.64, mAOE 1.16, mAVE 0.88). Validation was still rising when training ended: under-trained, not converged. Best-by-val (`our_lidar_best_by_val_NDS.pth`, epoch 14, mAP 0.214 / NDS 0.238) was selected on VAL, so it is optimistic; use the last epoch.

Verified: checkpoint saved, reloaded from the exported weights-only file, inference and nuScenes evaluation run without key mismatch, ego export and MATLAB import done (`../../exports/L3E`). Reference (contaminated, official): 0.543 / 0.563.

Details, caveats and the deviations from the frozen pipeline (one numpy-alias source patch on the training path): `../our_bevfusion_mini/README.md`. Config: `config/our_lidar_mini.py` (inherits the upstream mmdet3d v1.4.0 config in the same folder).
