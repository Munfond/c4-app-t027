"""Giao diện web của lab (mốc 1). Chạy:  .venv_local\\Scripts\\streamlit run web\\app.py
Chọn frame nuScenes-mini ở thanh trái, bấm tab chức năng ở giữa. Nhãn "chạy live" / "tính sẵn" ghi rõ nguồn của mỗi kết quả."""
import os, sys
import numpy as np
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panels as P
import tables as TB
import tracking as TR
import matlab_bridge as MB

st.set_page_config(page_title='Camera–LiDAR–Radar Lab', layout='wide')


@st.cache_resource(show_spinner='Đọc bảng nuScenes-mini...')
def get_ds():
    return P.load_dataset()


@st.cache_resource(show_spinner='Nạp trọng số...')
def get_occ(variant):
    return P.load_occ_model(variant)


@st.cache_resource(show_spinner='Nạp trọng số...')
def get_flow(variant):
    return P.load_flow_model(variant)


@st.cache_data(show_spinner=False)
def get_det(name):
    return P.read_det_csv(name)


@st.cache_data(show_spinner=False)
def get_gt():
    return P.read_gt_csv()


@st.cache_data(show_spinner=False)
def get_risk_pre():
    return P.load_risk_precomputed()


@st.cache_data(show_spinner='Chạy tracker...')
def get_tracks(model, thr):
    return TR.run_tracking(get_ds(), get_det(model), thr)


@st.cache_data(show_spinner=False, max_entries=64)
def bev_inputs(tok):
    return get_ds().bev_inputs(tok)


@st.cache_data(show_spinner=False, max_entries=64)
def labels(tok):
    return get_ds().labels(tok)


@st.cache_data(show_spinner=False, max_entries=64)
def gt_flow(tok):
    return get_ds().gt_flow(tok)


ds = get_ds()
# ---------------- thanh trái: chọn frame ----------------
st.sidebar.title('Chọn dữ liệu')
split = st.sidebar.radio('Tập', ['val', 'train'], help='val = 81 frame (model chưa thấy khi train). train = 323 frame model đã học, số đo trên tập này KHÔNG phản ánh hiệu năng tổng quát.')
n = len(ds.by_split[split])
idx = st.sidebar.slider(f'Frame ({split})', 0, n - 1, 5 if split == 'val' else 100)
tok = ds.token(split, idx)
scene = ds.scene[ds.sample[tok]['scene_token']]['name']
st.sidebar.caption(f'scene {scene} · token {tok[:8]}')
if split == 'train':
    st.sidebar.warning('Frame train: model đã học frame này.')


@st.cache_data(show_spinner=False, max_entries=32)
def cam_images(tok):
    return P.fig_cameras(get_ds(), tok)


with st.sidebar.expander('Ảnh camera của frame', expanded=False):
    for name, im in cam_images(tok):
        st.image(im, caption=name, width='stretch')
has_pre = split == 'val'                              # kết quả tính sẵn (Kaggle/MATLAB) chỉ có cho 81 frame val, sample_idx = idx
st.sidebar.markdown('---')
engine_ok = MB.is_available()
if engine_ok:
    if MB._eng is None:
        if st.sidebar.button('Khởi động MATLAB Engine (~15 s)', help='Cần cho các nút chạy live bằng MATLAB: risk, classical'):
            with st.spinner('Đang mở MATLAB nền...'):
                MB.engine()
            st.rerun()
    else:
        st.sidebar.success('MATLAB Engine đang chạy')
else:
    st.sidebar.info('Không có MATLAB Engine: các nút live bằng MATLAB tắt, vẫn xem được kết quả tính sẵn.')
engine_on = engine_ok and MB._eng is not None
st.sidebar.caption('Nguồn kết quả:\n- **chạy live**: tính ngay trên CPU máy này\n- **tính sẵn**: đọc file đã tính trên Kaggle (BEVFusion/CRN cần CUDA)')

st.title('Lab hợp nhất Camera–LiDAR–Radar · nuScenes-mini')
NAMES = ['Camera', 'LiDAR + Radar', 'Occupancy (live)', 'Flow (live)', 'Detection (tính sẵn)', 'Tracking', 'Risk heatmap', 'Classical (MATLAB live)', 'Ablation', 'Mô phỏng Level 1', 'Chỉ số & giới hạn']
section = st.radio('Chức năng', NAMES, horizontal=True, label_visibility='collapsed', key='section')

# ---------------- Camera ----------------
if section == NAMES[0]:
    st.subheader('6 camera thật của frame')
    imgs = P.fig_cameras(ds, tok)
    for row in (imgs[:3], imgs[3:]):
        cols = st.columns(3)
        for c, (name, im) in zip(cols, row):
            c.image(im, caption=name, width='stretch')

# ---------------- LiDAR + Radar ----------------
if section == NAMES[1]:
    st.subheader('Point cloud LiDAR và radar (hệ ego, x tiến / y trái)')
    c1, c2 = st.columns([1, 3])
    with c1:
        show_l = st.checkbox('Hiện LiDAR', True)
        sel = [r for r in P.RADARS if st.checkbox(r, True, key='rad' + r)]
        show_inp = st.checkbox('Hiện 7 kênh input BEV của U-Net', False)
    fig, info = P.fig_lidar_radar(ds, tok, show_l, sel)
    with c2:
        st.pyplot(fig)
    c1.metric('Điểm LiDAR', f'{info["lidar_points"]:,}'); c1.write({k: v for k, v in info['radar_points'].items()}); c1.caption(f'vẽ trong {info["ms"]:.0f} ms')
    if show_inp:
        t0 = __import__('time').time(); x = bev_inputs(tok); st.pyplot(P.fig_inputs_bev(x)); st.caption(f'dựng input BEV 7 kênh 200×200 (ô 0,5 m): {(__import__("time").time() - t0) * 1000:.0f} ms (lần đầu; sau đó lấy từ cache)')

# ---------------- Occupancy ----------------
if section == NAMES[2]:
    st.subheader('Occupancy BEV do U-Net tự train dự đoán (chạy live trên CPU)')
    c1, c2 = st.columns([1, 4])
    variant = c1.selectbox('Biến thể', list(P.OCC_FILES), help='lidar_radar = bản chính (7 kênh); lidar / radar = chỉ một cảm biến')
    with_label = c1.checkbox('So với nhãn (chậm hơn ~1 s)', True)
    model, ck = get_occ(variant); x = bev_inputs(tok); pred, ms = P.predict_occ(model, ck, x)
    gt = iou = None
    if with_label:
        gt = labels(tok); iou = P.iou_frame(pred, gt)
    with c2:
        st.pyplot(P.fig_occupancy(ds, tok, pred, gt, iou))
    c1.metric('Suy luận (CPU)', f'{ms:.0f} ms'); c1.write({'ô static': int((pred == 1).sum()), 'ô object': int((pred == 2).sum())})
    if iou:
        c1.write({k: round(v, 3) for k, v in iou.items()})
    c1.caption('Nhãn static là pseudo-GT dựng từ LiDAR (không phải nhãn người). mIoU val 0,549 trên 81 frame.')

# ---------------- Flow ----------------
if section == NAMES[3]:
    st.subheader('Flow (vận tốc mặt đất) do U-Net học (chạy live)')
    st.warning('Flow học được CHƯA dùng được: EPE 3,52 m/s trên val so với 3,79 của baseline zero-flow. Tab này để bạn tự kiểm tra, không phải kết quả tốt.')
    c1, c2 = st.columns([1, 4]); variant = c1.selectbox('Biến thể', list(P.FLOW_FILES), key='fv')
    model, ck = get_flow(variant); o, ms = P.predict_flow(model, ck, ds, bev_inputs, tok); gtf, valid = gt_flow(tok); stt = P.flow_stats(o, gtf, valid)
    with c2:
        st.pyplot(P.fig_flow(ds, tok, o, gtf, valid))
    c1.metric('Suy luận (CPU, gồm nạp lịch sử)', f'{ms:.0f} ms')
    c1.write({k: (None if v is None else round(v, 2)) for k, v in stt.items()})
    c1.caption(f'{"có" if ck["warp"] else "không"} bù chuyển động ego · dùng {ck["T"]} frame')

# ---------------- Detection ----------------
if section == NAMES[4]:
    st.subheader('Hộp 3D của các detector trên ảnh camera thật')
    if not has_pre:
        st.info('Detection chỉ có cho 81 frame val (tính trên Kaggle GPU, không chạy lại được trên máy này). Chọn tập val ở thanh trái.')
    else:
        st.caption('Đây là kết quả TÍNH SẴN (CSV trong exports/L3E, fusion/unified). Checkpoint official đã thấy mini-val lúc huấn luyện nên không so công bằng với bản our_*.')
        c1, c2 = st.columns([1, 4])
        names = c1.multiselect('Model', list(P.DET_SRC), default=['official_cl', 'our_cl', 'crn'])
        thr = c1.slider('Ngưỡng score', 0.0, 0.9, 0.3, 0.05)
        det = {m: get_det(m) for m in names}
        fig, cnt = P.fig_detections(ds, tok, idx, names, det, get_gt(), thr)
        with c2:
            st.pyplot(fig)
        c1.write(cnt)

# ---------------- Tracking ----------------
if section == NAMES[5]:
    st.subheader('Tracking trên chuỗi frame liên tiếp của scene val (2 Hz)')
    if not has_pre:
        st.info('Tracking chạy trên detection tính sẵn của 81 frame val. Chọn tập val ở thanh trái.')
    else:
        st.caption('Tracker tự viết đơn giản (Hungarian, vận tốc hằng, bù chuyển động ego), tham số chọn trước, không tinh chỉnh trên val. MOTA-lite là số tự tính, KHÔNG phải benchmark nuScenes tracking.')
        c1, c2 = st.columns([1, 3])
        m = c1.selectbox('Nguồn detection', list(P.DET_SRC), index=1, key='trm')
        thr = c1.slider('Ngưỡng score', 0.1, 0.9, 0.5 if m in ('crn', 'fused') else 0.3, 0.05, key='trt')
        frames, met = get_tracks(m, thr)
        seq = [i for i in range(len(ds.by_split['val'])) if ds.scene[ds.sample[ds.token('val', i)]['scene_token']]['name'] == scene]
        c1.write(met)
        c1.caption(f'scene {scene}: frame val {seq[0]}–{seq[-1]}')
        trail = c1.slider('Vệt đường đi (frame)', 0, 12, 6, key='trtrail')
        with c2:
            st.pyplot(P.fig_tracks(ds, frames, seq, idx, trail=trail))
        st.caption(f'Frame {idx}: {len(frames.get(idx, []))} track đang hoạt động.')

# ---------------- Risk ----------------
if section == NAMES[6]:
    st.subheader('Risk heatmap (computeRiskFields của Level 1, MATLAB)')
    st.warning('Điểm risk KHÔNG hiệu chuẩn, không phải xác suất va chạm. Oracle = GT occupancy + GT flow.')
    mode = st.radio('Nguồn', ['Tính sẵn (81 frame val, đã chạy bằng MATLAB)', 'Live (MATLAB Engine, mọi frame)'], horizontal=True)
    box_gt = ds.boxes(tok)
    vmax = st.slider('Thang màu (risk tối đa hiển thị)', 0.1, 0.6, 0.3, 0.05)
    if mode.startswith('Tính sẵn'):
        if not has_pre:
            st.info('Chỉ có cho val. Chọn tập val, hoặc dùng chế độ Live.')
        else:
            O, S = get_risk_pre()
            c1, c2 = st.columns([1, 4])
            sysn = c1.selectbox('Hệ thống', P.RISK_SYSTEMS[1:], index=2)
            c1.caption(P.RISK_NOTE[sysn])
            R = O['risk_' + sysn][idx]; Ro = O['risk_oracle'][idx]; T = O['ttc_' + sysn][idx]
            with c2:
                st.pyplot(P.fig_risk(ds, tok, [R, Ro], [sysn, 'oracle'], box_gt, vmax))
            c1.write({k: (round(v, 3) if isinstance(v, float) else v) for k, v in P.risk_stats(R, T).items()})
            c1.caption(f'oracle risk max {Ro.max():.3f} · ego {np.hypot(*S["ego_v"][idx]):.1f} m/s')
    else:
        if not engine_ok:
            st.error('Chưa cài matlabengine hoặc không tìm thấy mã Level 1.')
        elif not engine_on:
            st.info('Bấm "Khởi động MATLAB Engine" ở thanh trái (một lần, ~15 s).')
        else:
            import time as _t
            c1, c2 = st.columns([1, 4])
            sysn = c1.selectbox('Occupancy đầu vào', ['learned_occ (U-Net live)', 'classical (MATLAB live)'])
            v, w = P.ego_motion(ds, tok)
            t0 = _t.time()
            if sysn.startswith('learned'):
                model, ck = get_occ('lidar_radar')
                pred, _ms = P.predict_occ(model, ck, bev_inputs(tok))
                occ = pred > 0
            else:
                Pp, _i = ds.keyframe_lidar(tok)
                occ, _o = MB.classical_live(Pp)
            R, T = MB.risk_live(occ, 0.9, None, None, v, w)
            dt = (_t.time() - t0) * 1000
            with c2:
                st.pyplot(P.fig_risk(ds, tok, [R], [sysn], box_gt, vmax))
            c1.write({k: (round(val, 3) if isinstance(val, float) else val) for k, val in P.risk_stats(R, T).items()})
            c1.metric('Occupancy + MATLAB risk', f'{dt:.0f} ms')
            c1.caption(f'ego {np.hypot(*v):.1f} m/s · không có flow (frame bất kỳ chưa có detection tính sẵn). Ở val khớp kết quả tính sẵn (sai khác < 1e-7).')
    with st.expander('Bảng chỉ số các hệ thống (81 frame val)'):
        st.dataframe(TB.risk(), width='stretch')

# ---------------- Classical (MATLAB live) ----------------
if section == NAMES[7]:
    st.subheader('Pipeline classical Level 1 chạy live bằng MATLAB Engine')
    if not engine_ok:
        st.error('Chưa cài matlabengine.')
    elif not engine_on:
        st.info('Bấm "Khởi động MATLAB Engine" ở thanh trái (một lần, ~15 s).')
    else:
        import time as _t
        t0 = _t.time()
        Pp, _i = ds.keyframe_lidar(tok)
        occ, objs = MB.classical_live(Pp)
        dt = (_t.time() - t0) * 1000
        c1, c2 = st.columns([1, 3])
        c1.metric('MATLAB: xử lý LiDAR + occupancy + detection', f'{dt:.0f} ms')
        c1.write({'ô occupied': int(occ.sum()), 'vật thể chấp nhận': int(len(objs)), 'xe': int((objs[:, 5] == 1).sum()) if len(objs) else 0, 'người': int((objs[:, 5] == 2).sum()) if len(objs) else 0})
        c1.caption('Classical chỉ dùng hình học: nhiều hộp thừa/đứt (precision 0,43 trên val, xem tab Ablation). Xanh lá = GT.')
        with c2:
            st.pyplot(P.fig_classical(ds, tok, Pp, occ, objs, ds.boxes(tok)))

# ---------------- Ablation ----------------
if section == NAMES[8]:
    st.subheader('Ablation: cảm biến, model và độ dày LiDAR')
    st.warning('Đọc kèm giới hạn: mini-val 81 frame · official bị nhiễm · nhãn static là pseudo-GT. Mọi bảng là kết quả tính sẵn từ các stage.')
    st.markdown('#### Dữ liệu thật (nuScenes-mini)')
    st.markdown('**Occupancy: đổi đầu vào cảm biến của cùng một U-Net**')
    st.dataframe(TB.occupancy_sensor_ablation(), width='stretch', hide_index=True)
    st.markdown('**Detection: nguồn cảm biến/model** (Camera+LiDAR, LiDAR-only, Camera+Radar, hợp nhất; classical để so)')
    st.dataframe(TB.detection(), width='stretch', hide_index=True)
    st.markdown('**Điểm vận hành theo ngưỡng score**')
    import matplotlib.figure as _mf
    opf = TB.operating_points()
    fig = _mf.Figure(figsize=(7, 4))
    ax = fig.subplots()
    for name, g in opf.groupby('Nguồn'):
        ax.plot(g['recall'], g['precision'], 'o-', label=name)
    ax.set_xlabel('recall'); ax.set_ylabel('precision'); ax.grid(alpha=.3); ax.legend(fontsize=8); ax.set_title('precision–recall theo ngưỡng 0,3–0,7')
    st.pyplot(fig)
    st.markdown('**Pipeline classical khi LiDAR thưa hơn**')
    st.dataframe(TB.lidar_degradation(), width='stretch', hide_index=True)
    st.markdown('**Flow**')
    st.dataframe(TB.flow(), width='stretch', hide_index=True)
    st.markdown('**Risk theo hệ thống**')
    st.dataframe(TB.risk(), width='stretch', hide_index=True)
    st.markdown('#### Mô phỏng Level 1 (Unreal, kịch bản tổng hợp, 7 cấu hình)')
    sa = TB.sim_ablation()
    if sa is None:
        st.info('Không tìm thấy kết quả ablation Level 1.')
    else:
        st.dataframe(sa, width='stretch', hide_index=True)
        st.caption('Cùng một kịch bản, seed 42; camera dùng detector oracle, radar là mô hình giả lập: đây là kết quả mô phỏng, không so trực tiếp với dữ liệu thật.')
        cols = st.columns(2)
        for i, f in enumerate(['ablation_leave_one_out.png', 'ablation_occupancy_iou.png', 'ablation_risk.png', 'ablation_latency.png']):
            pth = os.path.join(TB.SIM_ABL, 'figures', f)
            if os.path.exists(pth):
                cols[i % 2].image(pth, caption=f, width='stretch')

# ---------------- Mô phỏng Level 1 ----------------
if section == NAMES[9]:
    st.subheader('Sản phẩm mô phỏng Level 1 (MATLAB/Simulink + Unreal)')
    st.caption('Kết quả có sẵn trong cam_lidar_radar_ws/outputs/main/outputs/runs (kịch bản mô phỏng tổng hợp, không phải dữ liệu nuScenes).')
    vids = [('Demo sản phẩm', os.path.join(TB.SIM_FINAL, 'videos', 'demo_product.mp4')), ('Demo kỹ thuật', os.path.join(TB.SIM_FINAL, 'videos', 'demo_engineering.mp4')), ('Risk heatmap', os.path.join(TB.SIM_RISK, 'videos', 'risk.mp4'))]
    vs = [v for v in vids if os.path.exists(v[1])]
    if not vs:
        st.info('Không tìm thấy video Level 1.')
    else:
        pick = st.radio('Video', [v[0] for v in vs], horizontal=True)
        path = dict(vs)[pick]
        st.video(open(path, 'rb').read())
        st.caption(f'{os.path.basename(path)} · {os.path.getsize(path) / 1e6:.1f} MB')
    figs = [(n, os.path.join(TB.SIM_FINAL, 'figures', n + '.png')) for n in ['product_view', 'engineering_view', 'evaluation_view', 'semantic_view', 'occupancy3d_view']]
    figs = [f for f in figs if os.path.exists(f[1])]
    if figs:
        st.markdown('#### Các góc nhìn')
        for tb, f in zip(st.tabs([f[0] for f in figs]), figs):
            tb.image(f[1], width='stretch')
    pdf = os.path.join(TB.SIM_FINAL, 'report', 'final_report.pdf')
    if os.path.exists(pdf):
        st.markdown('#### Báo cáo cuối')
        st.download_button('Tải final_report.pdf', open(pdf, 'rb').read(), file_name='final_report.pdf')
        pg = st.select_slider('Trang', options=list(range(1, 7)), value=1)
        pimg = os.path.join(TB.SIM_FINAL, 'report', f'final_report_page{pg}.png')
        if os.path.exists(pimg):
            st.image(pimg, width='stretch')

# ---------------- Metrics ----------------
if section == NAMES[10]:
    st.subheader('Chỉ số đã tính (đọc từ file kết quả của từng stage)')
    st.warning('Đọc kèm giới hạn: nuScenes-mini (81 frame val) không phải benchmark đầy đủ · checkpoint official bị nhiễm trên mini-val · nhãn static là pseudo-GT · điểm risk chưa hiệu chuẩn, không phải xác suất va chạm.')
    for title, rel in [('Stage E: classical vs learned', 'stage_e/results/stage_e_metrics.json'), ('Stage F: occupancy học', 'stage_f/results/stage_f_metrics.json'),
                       ('Stage G: flow', 'stage_g/results/stage_g_reference.json'), ('Stage H: risk', 'stage_h/results/risk_metrics.json'), ('Fusion: điểm vận hành', 'fusion/unified/operating_points.json')]:
        with st.expander(title):
            js = P.read_json(rel)
            st.json(js) if js is not None else st.write('không tìm thấy', rel)
    st.markdown('**Chưa có:** xuất video/báo cáo từ web, upload dữ liệu riêng.')
