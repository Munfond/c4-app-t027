# camera_lidar — `our_bevfusion.pth` (BEVFusion Camera+LiDAR, trained on nuScenes-mini TRAIN)

Byte-identical copy of `../our_bevfusion_mini/our_bevfusion_mini.pth` (Stage B). LiDAR branch initialised from **our** `lidar_only/our_lidar.pth`; Swin-T image backbone from the official ImageNet weights (standard BEVFusion workflow); no official BEVFusion LiDAR or fusion checkpoint loaded. 7 epochs x 1630 iterations, one Tesla T4, batch 1 with accumulation 4, AMP, about 2 h 45 min.

Mini VAL (81 samples): **mAP 0.192, NDS 0.207** (mATE 0.62, mASE 0.61, mAOE 1.14, mAVE 0.99). This is **lower than our own LiDAR-only (0.210 / 0.232)**: train loss fell (1.10) while VAL did not improve, i.e. the camera branch overfits 323 samples. A 2-epoch smoke run already reached 0.197 / 0.222. Best-by-val (`our_bevfusion_best_by_val_NDS.pth`, 0.200 / 0.213) was selected on VAL and is optimistic. Reference (contaminated, official): 0.570 / 0.576.

Verified: checkpoint saved, reloaded from the exported file, inference and evaluation without key mismatch, ego export and MATLAB import done. Details and caveats: `../our_bevfusion_mini/README.md`. Config: `config/our_bevfusion_mini.py`.
