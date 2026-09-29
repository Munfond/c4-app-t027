% Stage G -> MATLAB: occupancy + ground-velocity flow (Level-1 FLOW_CONTRACT layout: flowX/flowY single m/s, NaN where not occupied).
% Ego frame at time t: grid rows = +x forward, columns = +y left, 0.5 m cells, +/-50 m. Flow is GROUND velocity in the current ego axes (static ~ 0).
here = fileparts(mfilename('fullpath'));
S = load(fullfile(here, 'flow_predictions.mat'));
idx = 5; c = (-S.extent_m + S.cell_m / 2 : S.cell_m : S.extent_m - S.cell_m / 2)';   % column vector
f = figure('Visible', 'off', 'Position', [100 100 1300 480]);
gx = squeeze(S.gt_flowX(idx, :, :)); gy = squeeze(S.gt_flowY(idx, :, :)); px = squeeze(S.flowX(idx, :, :)); py = squeeze(S.flowY(idx, :, :)); cls = squeeze(S.occupancy_class(idx, :, :));
subplot(1, 2, 1); hold on; axis equal; grid on; set(gca, 'XDir', 'reverse'); xlim([-50 50]); ylim([-50 50]);
[r, cc] = find(isfinite(gx)); r = r(1:3:end); cc = cc(1:3:end); ii = sub2ind(size(gx), r, cc); quiver(c(cc), c(r), gy(ii), gx(ii), 0, 'Color', [0 0.5 0]); title('GT flow (annotated objects)'); xlabel('y left [m]'); ylabel('x forward [m]');
subplot(1, 2, 2); hold on; axis equal; grid on; set(gca, 'XDir', 'reverse'); xlim([-50 50]); ylim([-50 50]);
[r, cc] = find(cls == 2 & isfinite(px)); r = r(1:3:end); cc = cc(1:3:end); ii = sub2ind(size(px), r, cc); quiver(c(cc), c(r), py(ii), px(ii), 0, 'Color', [0.85 0.1 0.1]); title('learned T4 flow at predicted object cells'); xlabel('y left [m]');
exportgraphics(f, fullfile(here, 'stage_g_matlab_sample5.png'), 'Resolution', 80);
fprintf('val=%d | GT flow cells (sample %d)=%d | predicted occupied cells=%d | future channels: %s\n', size(S.flowX, 1), idx, nnz(isfinite(gx)), nnz(isfinite(px)), strjoin({'0.5s', '1.0s'}, ', '));
