"""Cầu nối MATLAB Engine: chạy computeRiskFields (Level 1, không sửa) và pipeline classical trên frame bất kỳ.
Engine khởi động một lần (~15 s) và giữ suốt phiên; nếu chưa cài `matlabengine` hoặc không có MATLAB thì is_available() trả False và web ẩn tính năng live."""
import os, threading
import numpy as np

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJ = r'D:\Vinuni\endgame\cam_lidar_radar\cam_lidar_radar_ws'
_lock = threading.Lock()
_eng = None


def is_available():
    try:
        import matlab.engine                                 # noqa: F401
        return os.path.isdir(PROJ)
    except Exception:
        return False


def engine():
    global _eng
    with _lock:
        if _eng is None:
            import matlab.engine
            _eng = matlab.engine.start_matlab()
            _eng.addpath(_eng.genpath(os.path.join(PROJ, 'src')), nargout=0); _eng.addpath(os.path.join(PROJ, 'config'), nargout=0)
            _eng.addpath(os.path.join(WS, 'matlab'), nargout=0)
    return _eng


def _m(a):
    import matlab
    return matlab.double(np.asarray(a, dtype=float).tolist())


def risk_live(occ, prob, fx, fy, ego_v, yaw_rate):
    """occ (200,200) bool, fx/fy (200,200) m/s ego axes hoặc None (không có flow). Trả (risk, ttc) (200,200) float32.
    Cùng cấu hình như stage_h/matlab/run_risk_bridge.m (lưới x -51.3..48.7 để tâm thân xe là gốc, xe Zoe 4,084 x 1,730 m)."""
    e = engine()
    nan = np.full((200, 200), np.nan)
    r = e.risk_from_arrays(_m(occ.astype(float)), float(prob), _m(nan if fx is None else fx), _m(nan if fy is None else fy), _m(np.array(ego_v, float).reshape(1, 2)), float(yaw_rate), nargout=2)
    return np.array(r[0], dtype=np.float32), np.array(r[1], dtype=np.float32)


def classical_live(points_xyz):
    """points_xyz (N,3) LiDAR trong hệ ego (không xoá thân xe). Trả (occupied (200,200) bool, [(cx,cy,w,l,yaw,class)] các vật thể được chấp nhận)."""
    e = engine()
    occ, objs = e.classical_from_points(_m(points_xyz), nargout=2)
    occ = np.array(occ, dtype=bool); objs = np.array(objs, dtype=float).reshape(-1, 6) if len(objs) else np.zeros((0, 6))
    return occ, objs
