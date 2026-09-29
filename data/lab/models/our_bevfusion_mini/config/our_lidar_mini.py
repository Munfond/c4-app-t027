# Stage A: BEVFusion LiDAR-only trained FROM SCRATCH on nuScenes-mini TRAIN. No checkpoint is loaded.
import os

_base_ = ['./bevfusion_lidar_voxel0075_second_secfpn_8xb4-cyclic-20e_nus-3d.py']

EPOCHS = int(os.environ.get('OUR_EPOCHS', 20))
LR = float(os.environ.get('OUR_LR', 3e-5))
ACCUM = int(os.environ.get('OUR_ACCUM', 4))
VAL_INT = int(os.environ.get('OUR_VAL_INT', 2))
NUM_WORKERS = int(os.environ.get('OUR_WORKERS', 4))
WARM = max(1, round(EPOCHS * 0.4))
DECAY = max(1, EPOCHS - WARM)

load_from = None
resume = False
randomness = dict(seed=42, deterministic=False)

train_dataloader = dict(batch_size=1, num_workers=NUM_WORKERS, persistent_workers=True)
val_dataloader = dict(batch_size=1, num_workers=2, dataset=dict(metainfo=dict(version='v1.0-mini')))
test_dataloader = dict(batch_size=1, num_workers=2, dataset=dict(metainfo=dict(version='v1.0-mini')))

optim_wrapper = dict(optimizer=dict(lr=LR), accumulative_counts=ACCUM)

param_scheduler = [
    dict(type='CosineAnnealingLR', T_max=WARM, eta_min=LR * 10, begin=0, end=WARM, by_epoch=True,
         convert_to_iter_based=True),
    dict(type='CosineAnnealingLR', T_max=DECAY, eta_min=LR * 1e-4, begin=WARM, end=EPOCHS, by_epoch=True,
         convert_to_iter_based=True),
    dict(type='CosineAnnealingMomentum', T_max=WARM, eta_min=0.85 / 0.95, begin=0, end=WARM, by_epoch=True,
         convert_to_iter_based=True),
    dict(type='CosineAnnealingMomentum', T_max=DECAY, eta_min=1, begin=WARM, end=EPOCHS, by_epoch=True,
         convert_to_iter_based=True)
]

train_cfg = dict(by_epoch=True, max_epochs=EPOCHS, val_interval=VAL_INT)

default_hooks = dict(
    logger=dict(type='LoggerHook', interval=20),
    checkpoint=dict(type='CheckpointHook', interval=1, max_keep_ckpts=-1, save_optimizer=True,
                    save_best='NuScenes metric/pred_instances_3d_NuScenes/NDS', rule='greater'))

custom_hooks = [dict(type='DisableObjectSampleHook', disable_after_epoch=max(1, int(EPOCHS * 0.75)))]
