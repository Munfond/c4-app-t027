function [occ, objs] = classical_from_points(pts)
%CLASSICAL_FROM_POINTS Pipeline classical Level 1 (processLidarScan -> buildBevOccupancy -> extractLidarDetections) cho điểm LiDAR đã ở hệ ego (N x 3).
% Gọi từ web qua MATLAB Engine. Trả occ logical 200x200 (hàng = +x, cột = +y, ô 0.5 m) và objs (M x 6) = [cx cy w l yaw class], class 1 = vehicle, 2 = pedestrian.
persistent cfg
if isempty(cfg)
    proj = 'D:\Vinuni\endgame\cam_lidar_radar\cam_lidar_radar_ws'; ws = fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(fullfile(proj, 'src'))); addpath(fullfile(proj, 'config'));
    if ~all(cellfun(@(f) exist(f, 'file') > 0, {'pointCloud', 'pcfitplane', 'pcsegdist', 'objectDetection'})), addpath(fullfile(ws, 'stage_e', 'matlab', 'shims')); end
    cfg = unifiedBevConfig(); cfg.bev.xBounds_m = [-50 50]; cfg.bev.yBounds_m = [-50 50]; cfg.bev.resolution_m = 0.5;
    cfg.occupancy.self.bounds_m = [-1.0 3.7; -1.1 1.1; -0.3 1.9]; cfg.urban.lidar.horizontalFov_deg = 360;
    cfg.sensors.lidar.translation_m = [0 0 0]; cfg.sensors.lidar.rotationMatrix = eye(3);       % điểm đã ở hệ ego
end
cloud = processLidarScan(struct('points', double(pts), 'timestamp', 0), cfg);
g = buildBevOccupancy(cloud, cfg); occ = logical(g.occupied);
[~, cl] = extractLidarDetections(cloud, createPose('ego', 'world', eye(3), [0 0 0]), cfg, 0);
objs = zeros(0, 6);
for a = reshape(cl([cl.accepted]), 1, [])
    k = find(strcmp(a.class, {'vehicle', 'pedestrian'}), 1); if isempty(k), continue; end
    C = a.corners; ctr = mean(C, 1); al = (C(1, :) + C(2, :)) / 2 - (C(3, :) + C(4, :)) / 2;
    objs(end + 1, :) = [ctr(1) ctr(2) norm(C(1, :) - C(2, :)) norm(al) atan2(al(2), al(1)) k]; %#ok<AGROW>
end
end
