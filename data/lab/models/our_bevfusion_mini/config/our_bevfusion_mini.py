# Stage B: BEVFusion Camera+LiDAR. LiDAR branch initialised from OUR Stage-A checkpoint; Swin-T image backbone uses the official
# ImageNet-pretrained weights (BEVFusion workflow). No official LiDAR / LiDAR+Camera BEVFusion checkpoint is loaded.
import os

_base_ = ['./bevfusion_lidar-cam_voxel0075_second_secfpn_8xb4-cyclic-20e_nus-3d.py']

EPOCHS = int(os.environ.get('OUR_EPOCHS', 6))
LR = float(os.environ.get('OUR_LR', 3e-5))
PEAK = LR * 3.5          # ~1e-4 for effective batch 4 (official: 2e-4 for batch 32)
ACCUM = int(os.environ.get('OUR_ACCUM', 4))
VAL_INT = int(os.environ.get('OUR_VAL_INT', 1))
NUM_WORKERS = int(os.environ.get('OUR_WORKERS', 4))
WITH_CP = bool(int(os.environ.get('OUR_WITH_CP', '0')))
WARM_EPOCHS = EPOCHS * 0.4

load_from = os.environ['OUR_LIDAR_CKPT']
resume = False
randomness = dict(seed=42, deterministic=False)

model = dict(img_backbone=dict(with_cp=WITH_CP))

train_dataloader = dict(batch_size=1, num_workers=NUM_WORKERS, persistent_workers=True)
val_dataloader = dict(batch_size=1, num_workers=2, dataset=dict(metainfo=dict(version='v1.0-mini')))
test_dataloader = dict(batch_size=1, num_workers=2, dataset=dict(metainfo=dict(version='v1.0-mini')))

optim_wrapper = dict(optimizer=dict(lr=PEAK), accumulative_counts=ACCUM)

param_scheduler = [
    dict(type='LinearLR', start_factor=0.33333333, by_epoch=False, begin=0, end=200),
    dict(type='CosineAnnealingLR', begin=0, T_max=EPOCHS, end=EPOCHS, by_epoch=True, eta_min_ratio=1e-4,
         convert_to_iter_based=True),
    dict(type='CosineAnnealingMomentum', eta_min=0.85 / 0.95, begin=0, end=WARM_EPOCHS, by_epoch=True,
         convert_to_iter_based=True),
    dict(type='CosineAnnealingMomentum', eta_min=1, begin=WARM_EPOCHS, end=EPOCHS, by_epoch=True,
         convert_to_iter_based=True)
]

train_cfg = dict(by_epoch=True, max_epochs=EPOCHS, val_interval=VAL_INT)

default_hooks = dict(
    logger=dict(type='LoggerHook', interval=20),
    checkpoint=dict(type='CheckpointHook', interval=1, max_keep_ckpts=-1, save_optimizer=True,
                    save_best='NuScenes metric/pred_instances_3d_NuScenes/NDS', rule='greater'))
