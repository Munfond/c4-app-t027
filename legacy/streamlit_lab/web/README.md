# Web lab

Giao diện web chạy trên máy bạn bằng Streamlit. Đã kiểm thử ngày 26/09/2026: chạy headless từng mục ở val và train (không lỗi), chụp giao diện bằng trình duyệt thật, và đối chiếu các phép tính live với kết quả tính sẵn.

## Chạy

```powershell
cd D:\Vinuni\endgame\cam_lidar_radar\cam_lidar_radat_real_ws
.venv_local\Scripts\pip install streamlit matlabengine        # một lần (matlabengine cần MATLAB R2026a đã cài)
.venv_local\Scripts\streamlit run web\app.py --server.address localhost
```
Trình duyệt mở ở `http://localhost:8501`. Lần đầu mất 30–50 s (đọc bảng nuScenes, nạp trọng số). Tắt: `Ctrl+C`. `--server.address localhost` để chỉ máy bạn truy cập được.
Không có `matlabengine` vẫn chạy: các mục live bằng MATLAB tự tắt, phần còn lại không ảnh hưởng.

## Dùng

Thanh trái: chọn tập (`val` 81 frame, `train` 323 frame), kéo thanh trượt chọn frame, ô mở rộng **Ảnh camera của frame** (6 camera của frame đang chọn; kéo mép thanh trái để phóng to), nút **Khởi động MATLAB Engine** (~15 s, một lần mỗi phiên). Hàng lựa chọn phía trên chọn chức năng; chỉ chức năng đang chọn được tính.

| Mục | Nội dung | Nguồn |
|---|---|---|
| Camera | 6 camera thật | đọc từ `data/` |
| LiDAR + Radar | point cloud, 5 radar theo màu, 7 kênh input BEV | đọc từ `data/` |
| Occupancy | U-Net tự train (lidar_radar/lidar/radar), so nhãn kèm IoU | **live** (CPU, ~0,15 s) |
| Flow | U-Net flow T1/T2/T4/T4_nowarp, so GT | **live** (CPU, ~0,14 s) |
| Detection | hộp 3D trên 6 ảnh camera + BEV, chọn model và ngưỡng | tính sẵn (81 val) |
| Tracking | tracker tự viết trên chuỗi frame của scene, vệt đường đi, MOTA-lite so GT | tính từ detection tính sẵn (81 val) |
| Risk heatmap | `computeRiskFields` Level 1: tính sẵn 5 hệ thống so oracle (val) hoặc **live bằng MATLAB Engine** cho mọi frame (occupancy U-Net hoặc classical) | tính sẵn / live |
| Classical (MATLAB live) | processLidarScan → occupancy → detection của Level 1, trên frame bất kỳ | live (MATLAB, ~2,5–5 s) |
| Ablation | bảng: đầu vào cảm biến của U-Net, nguồn detection, LiDAR thưa, flow, risk, và ablation 7 cấu hình của mô phỏng Level 1 | tính sẵn |
| Mô phỏng Level 1 | 3 video (sản phẩm, kỹ thuật, risk), 5 góc nhìn, báo cáo PDF từ `cam_lidar_radar_ws\outputs\main\outputs\runs` | có sẵn |
| Chỉ số & giới hạn | json kết quả Stage E–H | tính sẵn |

## Đối chiếu live với tính sẵn (đã đo)
- Risk live (MATLAB Engine) trên val[51]: sai khác tối đa 1,5e-8 so với `stage_h/risk_out.mat`; occupancy U-Net khớp 100% ô; occupancy classical live khớp 100% ô (882 ô) và 28 vật thể như demo MATLAB.
- Vận tốc ego tính lại từ ego pose khớp `risk_inputs.mat` (8,2763 m/s).

## Cấu trúc
- `app.py`: giao diện và cache (model nạp một lần, input BEV cache theo frame).
- `panels.py`: tính và vẽ (tái dùng `tools/local`). `tables.py`: dựng bảng từ file kết quả. `tracking.py`: tracker và đo MOTA-lite. `matlab_bridge.py`: MATLAB Engine.
- `matlab/risk_from_arrays.m`, `matlab/classical_from_points.m`: hai hàm MATLAB do web gọi (mã Level 1 không sửa).

## Giới hạn
- Detection (BEVFusion, CRN) chỉ hiển thị kết quả tính sẵn cho 81 val vì cần CUDA; tracking phụ thuộc vào đó nên cũng chỉ val.
- Risk live không có flow (frame bất kỳ chưa có detection tính sẵn), nên khác các hệ thống có flow trong bảng tính sẵn.
- Tracker tự viết, tham số chọn trước, không tinh chỉnh trên val; MOTA-lite tự định nghĩa (GT có ≥ 5 điểm LiDAR/radar và ≤ 50 m; khớp tâm 2 m), không phải benchmark nuScenes tracking. ID switch còn nhiều ở cụm xe đỗ.
- Video/ablation Level 1 là kịch bản mô phỏng tổng hợp (camera dùng detector oracle), không so trực tiếp với dữ liệu thật.
- Chưa có: upload dữ liệu riêng, xuất video/báo cáo từ web.
- Cảnh báo bắt buộc khi đọc số: mini-val, official bị nhiễm, nhãn static là pseudo-GT, risk chưa hiệu chuẩn, flow học chưa dùng được.
