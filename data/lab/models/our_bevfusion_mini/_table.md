| Model | Training data | mAP | NDS | mATE | mASE | mAOE | mAVE |
|---|---|---|---|---|---|---|---|
| Official pretrained LiDAR | official (trainval) - CONTAMINATED on mini VAL | 0.543 | 0.563 | 0.41 | 0.44 | 0.47 | 0.45 |
| Official pretrained LiDAR+Camera | official (trainval) - CONTAMINATED on mini VAL | 0.570 | 0.576 | 0.41 | 0.45 | 0.50 | 0.42 |
| Our trained LiDAR (last epoch, 15) | ours: mini TRAIN only, from scratch | 0.210 | 0.232 | 0.61 | 0.64 | 1.16 | 0.88 |
| Our trained LiDAR+Camera (last epoch, 7) | ours: LiDAR init from our LiDAR, Swin-T ImageNet init | 0.192 | 0.207 | 0.62 | 0.61 | 1.14 | 0.99 |

| Model | car | truck | bus | pedestrian | motorcycle | bicycle | traffic_cone | trailer | construction_vehicle | barrier |
|---|---|---|---|---|---|---|---|---|---|---|
| Official pretrained LiDAR | 0.90 | 0.79 | 1.00 | 0.92 | 0.62 | 0.49 | 0.71 | 0.00 | 0.00 | 0.00 |
| Official pretrained LiDAR+Camera | 0.92 | 0.80 | 1.00 | 0.92 | 0.68 | 0.58 | 0.80 | 0.00 | 0.00 | 0.00 |
| Our trained LiDAR (last epoch, 15) | 0.60 | 0.31 | 0.40 | 0.74 | 0.07 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Our trained LiDAR+Camera (last epoch, 7) | 0.62 | 0.18 | 0.36 | 0.74 | 0.02 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
