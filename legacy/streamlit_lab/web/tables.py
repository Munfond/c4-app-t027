"""Bảng ablation và chỉ số dựng từ các file kết quả đã có (không tính lại gì). Trả về pandas.DataFrame."""
import csv, json, os
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
WS = os.environ.get('LAB_DATA_ROOT', os.path.join(REPO, 'data', 'lab'))
SIM_DATA = os.environ.get('SIM_DATA_ROOT', os.path.join(REPO, 'data', 'sim'))
SIM_ASSETS = os.environ.get('SIM_ASSET_ROOT', os.path.join(REPO, 'frontend', 'public', 'sim'))
SIM_FINAL = os.path.join(SIM_ASSETS, 'final')
SIM_RISK = os.path.join(SIM_ASSETS, 'risk')
SIM_ABL = os.path.join(SIM_ASSETS, 'ablation')


def _j(rel):
    return json.load(open(os.path.join(WS, *rel.split('/')), encoding='utf-8'))


def detection():
    d = _j('stage_e/results/stage_e_metrics.json')['detection']; rows = []
    for name, v in d.items():
        rows.append({'Hệ thống': name, 'precision': v['precision'], 'recall': v['recall'], 'F1': v['f1'], 'sai số tâm (m)': v['centre_err_m'], 'hộp/frame': v['per_image'],
                     'recall xe': v['recall_by_group']['vehicle'], 'recall người': v['recall_by_group']['pedestrian'], 'recall 35–50 m': v['recall_by_range']['35-50']})
    return pd.DataFrame(rows)


def occupancy_binary():
    d = _j('stage_f/results/stage_f_metrics.json'); rows = [{'Hệ thống': r['system'], 'IoU occupied': r['IoU_occupied'], 'precision': r['precision'], 'recall': r['recall'], 'ô/frame': r['occupied_cells_per_frame']} for r in d['binary_occupancy']]
    return pd.DataFrame(rows)


def occupancy_sensor_ablation():
    """Ablation cảm biến trên dữ liệu THẬT: cùng U-Net, đổi đầu vào (LiDAR+radar / LiDAR / radar)."""
    d = _j('stage_f/results/stage_f_metrics.json')['learned_per_class']; name = {'lidar_radar': 'LiDAR + radar', 'lidar': 'chỉ LiDAR', 'radar': 'chỉ radar'}
    return pd.DataFrame([{'Đầu vào': name[k], 'mIoU': v['mIoU'], 'IoU static': v['IoU_static'], 'IoU object': v['IoU_object'], 'IoU occupied': v['IoU_occupied(static+object)'],
                          'object precision': v['object_precision'], 'object recall': v['object_recall'], 'độ trễ T4 (ms)': v['latency_ms_T4']} for k, v in d.items()])


def lidar_degradation():
    """Ablation độ dày LiDAR của pipeline classical: full / giữ 50% / giữ 25% / chỉ trong 30 m."""
    d = _j('stage_e/results/stage_e_metrics.json')['robustness']; name = {'full': 'đầy đủ', 'keep50': 'giữ 50% điểm', 'keep25': 'giữ 25% điểm', 'range30': 'chỉ trong 30 m'}
    return pd.DataFrame([{'LiDAR': name[k], 'precision': v['detection']['precision'], 'recall': v['detection']['recall'], 'F1': v['detection']['f1'], 'hộp/frame': v['detection']['per_image'],
                          'recall ô object': v['occupancy']['object_cell_recall'], 'thời gian (s)': v['lidar_path_s']} for k, v in d.items()])


def flow():
    d = _j('stage_g/results/stage_g_reference.json'); rows = []
    for grp, dd in (('học', d['learned']), ('tham chiếu', d['reference'])):
        for name, v in dd.items():
            rows.append({'Nhóm': grp, 'Hệ thống': name, 'EPE (m/s)': v.get('EPE_moving_all'), 'góc lệch trung vị (°)': v.get('angle_median_deg'), 'flow giả trên vật tĩnh (m/s)': v.get('static_object_false_flow_mean')})
    return pd.DataFrame(rows)


def risk():
    d = _j('stage_h/results/risk_metrics.json')['systems']
    return pd.DataFrame([{'Hệ thống': k, 'MAE vs oracle (tất cả)': v['MAE_vs_oracle[all objects]'], 'MAE (vật chuyển động)': v['MAE_vs_oracle[moving objects (>=0.3 m/s)]'], 'Spearman vs oracle': v['Spearman_vs_oracle'],
                          'precision rủi ro cao': v['high_risk_precision'], 'recall rủi ro cao': v['high_risk_recall']} for k, v in d.items()])


def operating_points():
    d = _j('fusion/unified/operating_points.json'); rows = []
    for name, v in d.items():
        for thr, m in v.items():
            rows.append({'Nguồn': name, 'ngưỡng': float(thr), 'hộp/frame': m['per_sample'], 'precision': m['precision'], 'recall': m['recall']})
    return pd.DataFrame(rows)


def sim_ablation():
    p = os.path.join(SIM_DATA, 'ablation', 'tables', 'ablation_summary.csv')
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p)
    keep = ['Code', 'Configuration', 'OccupancyIoU', 'OccupancyMIoU', 'FlowEPE_mps', 'RiskMAE_missAsZero', 'TrackPosRMSE_m', 'LatencyMean_ms', 'RealTimeFactor']
    return df[keep].rename(columns={'Code': 'Mã', 'Configuration': 'Cấu hình', 'OccupancyIoU': 'Occ IoU', 'OccupancyMIoU': 'Occ mIoU', 'FlowEPE_mps': 'Flow EPE (m/s)',
                                    'RiskMAE_missAsZero': 'Risk MAE', 'TrackPosRMSE_m': 'Track RMSE (m)', 'LatencyMean_ms': 'Độ trễ (ms)', 'RealTimeFactor': 'RTF'})
