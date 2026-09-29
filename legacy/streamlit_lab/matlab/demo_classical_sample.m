function demo_classical_sample(split, idx)
%DEMO_CLASSICAL_SAMPLE Pipeline CLASSICAL của dự án (Level 1, không sửa mã) chạy trên MỘT frame nuScenes-mini thật đọc trực tiếp từ data/.
%   demo_classical_sample('val', 5)     % frame val số 5 (đánh số từ 0, giống Python và sample_idx trong exports)
%   demo_classical_sample('train', 100) % bất kỳ frame nào trong 404 keyframe
% Dùng nguyên processLidarScan, buildBevOccupancy, extractLidarDetections (toolbox thật nếu có, nếu thiếu tự dùng shim).
% Vẽ: điểm LiDAR (xám), ô occupied classical, cụm classical (cam), GT (xanh lá); với frame val có thêm box của model Camera+LiDAR
% tự train (tím) và official (đỏ) từ exports/L3E. Ảnh lưu ở reports/local_runs.
if nargin < 1, split = 'val'; end
if nargin < 2, idx = 5; end
ws = fileparts(fileparts(mfilename('fullpath'))); data = fullfile(ws, 'data');
proj = 'D:\Vinuni\endgame\cam_lidar_radar\cam_lidar_radar_ws';
addpath(genpath(fullfile(proj, 'src'))); addpath(fullfile(proj, 'config'));
if ~all(cellfun(@(f) exist(f, 'file') > 0, {'pointCloud', 'pcfitplane', 'pcsegdist', 'objectDetection'}))
    addpath(fullfile(ws, 'stage_e', 'matlab', 'shims')); fprintf('toolbox thiếu -> dùng shim\n');
end
J = @(n) jsondecode(fileread(fullfile(data, 'v1.0-mini', [n '.json'])));
fprintf('đọc bảng nuScenes...\n'); sample = J('sample'); scene = J('scene'); sd = J('sample_data'); cs = J('calibrated_sensor'); ego = J('ego_pose'); ann = J('sample_annotation'); inst = J('instance'); cats = J('category');
sceneName = containers.Map({scene.token}, {scene.name});
valScenes = {'scene-0103', 'scene-0916'}; trainScenes = {'scene-0061', 'scene-0553', 'scene-0655', 'scene-0757', 'scene-0796', 'scene-1077', 'scene-1094', 'scene-1100'};
want = valScenes; if strcmp(split, 'train'), want = trainScenes; end
keep = arrayfun(@(s) any(strcmp(sceneName(s.scene_token), want)), sample);
T = table(string({sample(keep).scene_token})', double([sample(keep).timestamp])', string({sample(keep).token})', 'VariableNames', {'scene', 'ts', 'token'});
T = sortrows(T, {'scene', 'ts'}); tok = char(T.token(idx + 1)); ts = T.ts(idx + 1) / 1e6;
sdTok = {sd.token}; isKey = [sd.is_key_frame]'; sdSample = string({sd.sample_token})'; fn = string({sd.filename})';
k = find(isKey & sdSample == tok & contains(fn, 'LIDAR_TOP'), 1); lid = sd(k);
csMap = containers.Map({cs.token}, num2cell(1:numel(cs))); egoMap = containers.Map({ego.token}, num2cell(1:numel(ego)));
c = cs(csMap(lid.calibrated_sensor_token)); e = ego(egoMap(lid.ego_pose_token)); Re = qR(e.rotation); te = e.translation(:)';
fid = fopen(fullfile(data, strrep(lid.filename, '/', filesep)), 'rb'); raw = fread(fid, [5 Inf], 'float32')'; fclose(fid);
fprintf('frame %s[%d] token %s scene %s | %d LiDAR points\n', split, idx, tok(1:8), sceneName(sample(find(strcmp({sample.token}, tok), 1)).scene_token), size(raw, 1));

cfg = unifiedBevConfig(); cfg.bev.xBounds_m = [-50 50]; cfg.bev.yBounds_m = [-50 50]; cfg.bev.resolution_m = 0.5;
cfg.occupancy.self.bounds_m = [-1.0 3.7; -1.1 1.1; -0.3 1.9]; cfg.urban.lidar.horizontalFov_deg = 360;
cfg.sensors.lidar.translation_m = reshape(c.translation, 1, 3); cfg.sensors.lidar.rotationMatrix = qR(c.rotation);
t0 = tic; cloud = processLidarScan(struct('points', double(raw(:, 1:3)), 'timestamp', ts), cfg); bev = buildBevOccupancy(cloud, cfg);
[~, cl] = extractLidarDetections(cloud, createPose('ego', 'world', eye(3), [0 0 0]), cfg, ts); dt = toc(t0);
acc = cl([cl.accepted]); acc = acc(ismember({acc.class}, {'vehicle', 'pedestrian'}));
fprintf('classical: %d occupied cells, %d clusters, %d accepted objects (%d vehicle, %d pedestrian) in %.2f s\n', nnz(bev.occupied), numel(cl), numel(acc), nnz(strcmp({acc.class}, 'vehicle')), nnz(strcmp({acc.class}, 'pedestrian')), dt);

gtc = {'vehicle.car', 'vehicle.truck', 'vehicle.bus.bendy', 'vehicle.bus.rigid', 'vehicle.trailer', 'vehicle.construction', 'vehicle.motorcycle', 'vehicle.bicycle', 'human.pedestrian.adult', ...
       'human.pedestrian.child', 'human.pedestrian.construction_worker', 'human.pedestrian.police_officer', 'movable_object.trafficcone', 'movable_object.barrier'};
instCat = containers.Map({inst.token}, {inst.category_token}); catName = containers.Map({cats.token}, {cats.name});
gt = zeros(0, 5); for a = ann(strcmp({ann.sample_token}, tok))'
    if ~any(strcmp(catName(instCat(a.instance_token)), gtc)), continue; end
    p = Re' * (a.translation(:) - te'); R = Re' * qR(a.rotation); gt(end + 1, :) = [p(1) p(2) a.size(1) a.size(2) atan2(R(2, 1), R(1, 1))]; %#ok<AGROW>
end
f = figure('Visible', 'off', 'Position', [100 100 900 900]); hold on; axis equal; grid on; set(gca, 'Color', 'k', 'XDir', 'reverse'); xlim([-50 50]); ylim([-50 50]);
P = cloud.points; scatter(P(:, 2), P(:, 1), 1, [0.5 0.5 0.5], '.');
[rr, cc] = find(bev.occupied); sp = bev.spec; scatter(sp.yCenters(cc), sp.xCenters(rr), 6, [0.9 0.9 0.2], 's', 'filled');
for a = acc, plot(a.corners([1:end 1], 2), a.corners([1:end 1], 1), '-', 'Color', [1 0.55 0], 'LineWidth', 1.5); end
for g = gt', drawBox(g(1), g(2), g(3), g(4), g(5), [0.2 1 0.2], 1); end
leg = {'LiDAR', 'classical occupied', 'classical objects', 'GT'};
if strcmp(split, 'val')
    L = load(fullfile(ws, 'exports', 'L3E', 'l3e_predictions.mat')); O = load(fullfile(ws, 'exports', 'L3E', 'own_models_predictions.mat'));
    draw(L.pred_lidar_camera, idx + 1, [1 0.2 0.2]); draw(O.pred_our_bevfusion, idx + 1, [0.75 0.4 1]); leg = [leg, {'official Camera+LiDAR (score>=0.3)', 'our Camera+LiDAR (score>=0.3)'}];
end
plot(0, 0, 'c^', 'MarkerFaceColor', 'c'); xlabel('y left [m]'); ylabel('x forward [m]'); title(sprintf('classical (project code) on %s[%d]: green = GT', split, idx), 'Color', 'k');
out = fullfile(ws, 'reports', 'local_runs'); if ~exist(out, 'dir'), mkdir(out); end
png = fullfile(out, sprintf('matlab_classical_%s%d.png', split, idx)); exportgraphics(f, png, 'Resolution', 90); fprintf('đã lưu %s\n', png);
end

function R = qR(q)
w = q(1); x = q(2); y = q(3); z = q(4);
R = [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w); 2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w); 2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)];
end
function drawBox(cx, cy, w, l, yaw, col, lw)
c = cos(yaw); s = sin(yaw); u = [1 1 -1 -1 1] * l / 2; v = [1 -1 -1 1 1] * w / 2;
plot(cy + s * u + c * v, cx + c * u - s * v, '-', 'Color', col, 'LineWidth', lw);
end
function draw(T, i, col)
for j = reshape(find(T.sample_idx == i & T.score >= 0.3), 1, []), drawBox(T.x(j), T.y(j), T.w(j), T.l(j), T.yaw(j), col, 1.2); end
end
