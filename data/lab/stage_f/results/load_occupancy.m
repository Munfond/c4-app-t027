% Stage F -> MATLAB: BEV occupancy (ego frame). Grid rows = +x forward, columns = +y left, 0.5 m cells, +/-50 m.
% Classes: 0 free, 1 static (LiDAR-derived pseudo-GT), 2 object (annotated box footprint).
here = fileparts(mfilename('fullpath'));
S = load(fullfile(here, 'occupancy_predictions.mat'));
idx = 5; ext = S.extent_m; res = S.cell_m; c = -ext + res / 2 : res : ext - res / 2;
cmap = [0.07 0.07 0.07; 0.55 0.55 0.55; 0.9 0.64 0];
f = figure('Visible', 'off', 'Position', [100 100 1500 420]);
panels = {squeeze(S.gt(idx, :, :)), squeeze(double(S.classical_lidar_occ(idx, :, :))), squeeze(S.pred_lidar_radar(idx, :, :)), squeeze(S.pred_radar(idx, :, :))};
titles = {'label', 'classical LiDAR occupancy', 'learned LiDAR+radar', 'learned radar only'};
for k = 1:4
    subplot(1, 4, k); imagesc(c, c, panels{k}, [0 2]); colormap(gca, cmap); axis xy equal tight; set(gca, 'XDir', 'reverse');
    xlabel('y left [m]'); ylabel('x forward [m]'); title(titles{k});
end
exportgraphics(f, fullfile(here, 'stage_f_matlab_sample5.png'), 'Resolution', 80);
fprintf('val samples=%d grid=%dx%d | label occupied cells (sample %d)=%d | learned LiDAR+radar occupied=%d\n', size(S.gt, 1), size(S.gt, 2), size(S.gt, 3), idx, nnz(S.gt(idx, :, :) > 0), nnz(S.pred_lidar_radar(idx, :, :) > 0));
