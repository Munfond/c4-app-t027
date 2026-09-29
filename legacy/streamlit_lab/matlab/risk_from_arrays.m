function [risk, ttc] = risk_from_arrays(occ, prob, fx, fy, egoV, yawRate)
%RISK_FROM_ARRAYS computeRiskFields (Level 1, không sửa) cho một lưới 200x200; gọi từ web qua MATLAB Engine.
% Cấu hình giống stage_h/matlab/run_risk_bridge.m: lưới x -51.3..48.7 (tâm thân xe là gốc), y +-50, ô 0.5 m, xe Zoe 4.084 x 1.730 m.
% occ logical 200x200, prob độ tin cậy của ô occupied (0.9 = nhãn chưa hiệu chuẩn của dự án, 1 = oracle), fx/fy flow m/s (NaN = không có).
persistent cfg
if isempty(cfg)
    proj = 'D:\Vinuni\endgame\cam_lidar_radar\cam_lidar_radar_ws';
    addpath(genpath(fullfile(proj, 'src'))); addpath(fullfile(proj, 'config'));
    cfg = riskMapConfig();
    cfg.bev.xBounds_m = [-51.3 48.7]; cfg.bev.yBounds_m = [-50 50]; cfg.bev.resolution_m = 0.5;
    cfg.risk.ego.length_m = 4.084; cfg.risk.ego.width_m = 1.730;
end
f = computeRiskFields(cfg, logical(occ), prob * ones(200, 200), fx, fy, struct('velocity', egoV(:)', 'yawRate', yawRate));
risk = f.risk; ttc = f.ttcSeconds;
end
