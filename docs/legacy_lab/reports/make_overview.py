"""Level-3 overview montage built ONLY from figures rendered by this project's own runs (no repository or paper images)."""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image

W = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
panels = [
    ('1. Pretrained BEVFusion on real data: 6 cameras + 3D boxes + LiDAR BEV, GT vs prediction (contaminated)', 'notebooks/bev-real-viz/out/viz/sample_040_scene-0916.png'),
    ('2. Own LiDAR-only (left BEV) vs official (right BEV)', 'models/lidar_only/demo_images/sample_005_scene-0916.png'),
    ('3. Camera+Radar CRN pretrained (left BEV) vs Camera+LiDAR (right BEV)', 'models/camera_radar/crn_r18_pretrained/demo_images/sample_005_scene-0916.png'),
    ('4. Unified Object List (Camera+LiDAR x Camera+Radar late fusion)', 'fusion/unified/unified_bev_sample5.png'),
    ('5. Classical (project MATLAB code) vs learned', 'stage_e/results/stage_e_compare_sample31.png'),
    ('6. Learned BEV occupancy (Stage F)', 'models/occupancy/demo_images/stage_f_compare_sample31.png'),
    ('7. Temporal flow: GT vs learned vs detection-derived (Stage G)', 'models/temporal_flow/demo_images/stage_g_flow_sample51.png'),
    ('8. Level-1 risk heatmap on real frames (Stage H)', 'stage_h/results/stage_h_risk_frame17.png'),
]
fig, axes = plt.subplots(4, 2, figsize=(26, 30))
for ax, (title, rel) in zip(axes.ravel(), panels):
    ax.imshow(Image.open(os.path.join(W, *rel.split('/')))); ax.set_title(title, fontsize=15); ax.axis('off')
fig.suptitle('Level 3 on real nuScenes-mini: every panel is rendered from this project\'s runs (VAL frames; official checkpoints are contaminated; not a full-nuScenes benchmark)', fontsize=17)
fig.tight_layout(rect=[0, 0, 1, 0.98]); fig.savefig(os.path.join(W, 'reports', 'level3_overview.png'), dpi=55)
print('wrote reports/level3_overview.png')
