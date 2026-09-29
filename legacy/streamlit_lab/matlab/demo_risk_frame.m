function demo_risk_frame(idx, system)
%DEMO_RISK_FRAME Tính lại risk heatmap (computeRiskFields của Level 1) cho MỘT frame val, với hệ thống perception chọn được, và vẽ cùng oracle.
%   demo_risk_frame(51, 'learned_detflow')
%   system: oracle | classical | learned_occ | learned_detflow | learned_zeroflow | learned_flownet   (idx từ 0)
% Đầu vào lấy từ stage_h/risk_inputs.mat (tạo bằng stage_h/prepare_risk_inputs.py). Risk là điểm KHÔNG hiệu chuẩn, không phải xác suất va chạm.
if nargin < 1, idx = 51; end
if nargin < 2, system = 'learned_detflow'; end
ws = fileparts(fileparts(mfilename('fullpath')));
proj = 'D:\Vinuni\endgame\cam_lidar_radar\cam_lidar_radar_ws'; addpath(genpath(fullfile(proj, 'src'))); addpath(fullfile(proj, 'config'));
S = load(fullfile(ws, 'stage_h', 'risk_inputs.mat')); k = idx + 1;
cfg = riskMapConfig(); cfg.bev.xBounds_m = [-51.3 48.7]; cfg.bev.yBounds_m = [-50 50]; cfg.bev.resolution_m = 0.5; cfg.risk.ego.length_m = 4.084; cfg.risk.ego.width_m = 1.730;
tbl = struct('oracle', {{'occ_oracle', 'flowX_oracle', 'flowY_oracle', 1}}, 'classical', {{'occ_classical', '', '', 0.9}}, 'learned_occ', {{'occ_learned', '', '', 0.9}}, ...
             'learned_detflow', {{'occ_detflow', 'flowX_det', 'flowY_det', 0.9}}, 'learned_zeroflow', {{'occ_detflow', '', '', 0.9}}, 'learned_flownet', {{'occ_flownet', 'flowX_net', 'flowY_net', 0.9}});
function r = risk_for(name)
    d = tbl.(name); occ = logical(reshape(S.(d{1})(k, :, :), 200, 200));
    if isempty(d{2}), fx = nan(200, 200); fy = nan(200, 200); else, fx = reshape(S.(d{2})(k, :, :), 200, 200); fy = reshape(S.(d{3})(k, :, :), 200, 200); end
    r = computeRiskFields(cfg, occ, d{4} * ones(200, 200), fx, fy, struct('velocity', S.ego_v(k, :), 'yawRate', S.ego_yawrate(k)));
end
t0 = tic; R = risk_for(system); Ro = risk_for('oracle'); dt = toc(t0);
fprintf('frame %d | ego %.1f m/s | %s: max risk %.3f, occupied cells %d, min TTC %.2f s | oracle: max risk %.3f | 2 x computeRiskFields = %.0f ms\n', idx, hypot(S.ego_v(k, 1), S.ego_v(k, 2)), system, max(R.risk(:)), nnz(R.valid), min(R.ttcSeconds(:)), max(Ro.risk(:)), dt * 1000);
obj = S.objects(S.objects(:, 1) == k, :); [~, o] = sort(hypot(obj(:, 2), obj(:, 3))); obj = obj(o, :);
f = figure('Visible', 'off', 'Position', [100 100 1500 620]); c = -49.75:0.5:49.75;
for p = 1:2
    subplot(1, 2, p); if p == 1, M = R.risk; ttl = system; else, M = Ro.risk; ttl = 'oracle (GT occupancy + GT flow)'; end
    imagesc(c, c, M, [0 0.6]); set(gca, 'YDir', 'normal'); axis equal tight; colormap(gca, hot); hold on;
    for j = 1:size(obj, 1), o_ = obj(j, :); cs_ = cos(o_(6)); sn = sin(o_(6)); u = [1 1 -1 -1 1] * o_(5) / 2; v = [1 -1 -1 1 1] * o_(4) / 2; plot(o_(3) + sn * u + cs_ * v, o_(2) + cs_ * u - sn * v, 'c-', 'LineWidth', 0.6); end
    plot(0, 0, 'g^', 'MarkerFaceColor', 'g'); title(ttl, 'Interpreter', 'none'); xlabel('y left [m]'); ylabel('x forward [m]'); colorbar;
end
% imagesc trục: cột = y, hàng = x -> hiển thị x ngang; chuyển về quy ước x tiến lên bằng cách hoán vị ở trên (M') và đảo y
for p = 1:2, subplot(1, 2, p); set(gca, 'XDir', 'reverse'); end
out = fullfile(ws, 'reports', 'local_runs'); if ~exist(out, 'dir'), mkdir(out); end
png = fullfile(out, sprintf('matlab_risk_val%d_%s.png', idx, system)); exportgraphics(f, png, 'Resolution', 80); fprintf('đã lưu %s\n', png);
end
