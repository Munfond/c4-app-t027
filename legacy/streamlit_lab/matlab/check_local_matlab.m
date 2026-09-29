function ok = check_local_matlab()
%CHECK_LOCAL_MATLAB Kiểm tra toàn bộ phía MATLAB của workspace: dữ liệu, các file .mat, các loader load_*.m và hai demo.
%   matlab -batch "cd('D:\Vinuni\endgame\cam_lidar_radar\cam_lidar_radat_real_ws'); addpath('matlab'); check_local_matlab"
ws = fileparts(fileparts(mfilename('fullpath'))); res = {};
function rec(name, pass, msg)
    res(end + 1, :) = {name, pass, msg}; fprintf('[%s] %-34s %s\n', ternary(pass, 'PASS', 'FAIL'), name, msg);
end
function r = ternary(c, a, b), if c, r = a; else, r = b; end, end
w = @(varargin) fullfile(ws, varargin{:});

% 1) dữ liệu nuScenes-mini
try
    s = jsondecode(fileread(w('data', 'v1.0-mini', 'sample.json'))); n = numel(s);
    L = dir(w('data', 'samples', 'LIDAR_TOP', '*.bin')); C = dir(w('data', 'samples', 'CAM_FRONT', '*.jpg'));
    rec('data/ nuScenes-mini', n == 404 && numel(L) == 404 && numel(C) == 404, sprintf('%d samples, %d LiDAR bin, %d CAM_FRONT jpg', n, numel(L), numel(C)));
catch e, rec('data/ nuScenes-mini', false, e.message); end

% 2) các file .mat: kích thước đúng
try
    S = load(w('exports', 'L3E', 'l3e_predictions.mat')); O = load(w('exports', 'L3E', 'own_models_predictions.mat')); R = load(w('exports', 'L3E', 'camera_radar_predictions.mat'));
    U = load(w('fusion', 'unified', 'unified_pretrained.mat'));
    rec('exports/L3E/*.mat', numel(S.samples.sample_idx) == 81 && numel(S.pred_lidar_camera.x) > 0 && numel(O.pred_our_bevfusion.x) > 0, sprintf('81 val samples; official CL %d boxes; our CL %d boxes; camera+radar %d boxes', numel(S.pred_lidar_camera.x), numel(O.pred_our_bevfusion.x), numel(R.pred_camera_radar.x)));
    rec('fusion/unified', numel(U.unified.x) > 0, sprintf('%d fused objects', numel(U.unified.x)));
catch e, rec('mat predictions', false, e.message); end
try
    F = load(w('models', 'occupancy', 'matlab', 'occupancy_predictions.mat')); G = load(w('models', 'temporal_flow', 'matlab', 'flow_predictions.mat'));
    rec('occupancy/flow .mat', size(F.gt, 1) == 81 && size(F.gt, 2) == 200, sprintf('occupancy gt %s | flow fields: %d', mat2str(size(F.gt)), numel(fieldnames(G))));
catch e, rec('occupancy/flow .mat', false, e.message); end

% 3) chạy các script loader có sẵn (mỗi script tự lưu png)
loaders = {w('exports', 'L3E', 'load_l3e.m'), w('exports', 'L3E', 'load_camera_radar.m'), w('exports', 'L3E', 'check_own.m'), w('fusion', 'unified', 'load_unified.m'), ...
           w('models', 'occupancy', 'matlab', 'load_occupancy.m'), w('models', 'temporal_flow', 'matlab', 'load_flow.m')};
for i = 1:numel(loaders)
    [~, nm] = fileparts(loaders{i});
    try, evalc('evalin(''base'', [''run('''''' strrep(loaders{i}, '''''''', '''''''''''''''') '''''')''])'); rec(['script ' nm], true, 'chạy xong'); catch e, rec(['script ' nm], false, e.message); end
    close all force;
end

% 4) hai demo
try, evalc('demo_classical_sample(''val'', 5)'); rec('demo_classical_sample', exist(w('reports', 'local_runs', 'matlab_classical_val5.png'), 'file') > 0, 'val[5] -> reports/local_runs'); catch e, rec('demo_classical_sample', false, e.message); end
try, evalc('demo_risk_frame(51, ''learned_detflow'')'); rec('demo_risk_frame', exist(w('reports', 'local_runs', 'matlab_risk_val51_learned_detflow.png'), 'file') > 0, 'val[51] -> reports/local_runs'); catch e, rec('demo_risk_frame', false, e.message); end
close all force;
ok = all([res{:, 2}]); fprintf('MATLAB CHECK %s (%d/%d)\n', ternary(ok, 'PASS', 'FAIL'), nnz([res{:, 2}]), size(res, 1));
end
