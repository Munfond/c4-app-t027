# Báo cáo cuối Level 3 — Advanced Research Lite trên dữ liệu thật (nuScenes-mini)

Ngày: 25/09/2026. Workspace: `cam_lidar_radat_real_ws`. Bảng trạng thái và bằng chứng: `PROJECT_STATE.md`. Hình tổng quan: `reports/level3_overview.png` (mọi ô đều render từ các lần chạy của dự án).

## 1. Mục tiêu và phạm vi

Chứng minh chuỗi **DATA → MODEL (pretrained / tự train) → INFERENCE → PREDICTION → EVALUATION → SO SÁNH VỚI CLASSICAL**, rồi đưa kết quả sang MATLAB (BEV, occupancy, risk). Không nhằm đạt SOTA và không train trên dữ liệu đầy đủ.

**Quy ước số liệu (bắt buộc khi trình bày):**
- Mọi số là **nuScenes-mini VAL: 81 keyframe, 2 scene** (scene-0103, scene-0916). Không phải benchmark nuScenes đầy đủ; không so trực tiếp với số trong bài báo.
- Checkpoint **official** đã train trên nuScenes trainval (có chứa các scene mini) nên điểm trên mini VAL **bị contaminated**: chỉ là "tham chiếu tích hợp", không chứng minh khả năng tổng quát hoá.
- Checkpoint **của dự án** chỉ train trên mini TRAIN (323 keyframe, 8 scene); VAL không dùng để train hay chọn model (báo cáo epoch cuối).
- Ba lớp `trailer`, `construction_vehicle`, `barrier` không có GT trong VAL, nên mAP tối đa 0.70.
- Một seed cho mỗi cấu hình; chênh lệch cỡ 0.01 chưa kết luận được.

## 2. Câu chuyện trình bày

```text
Pretrained integration -> LiDAR tự train -> Camera+LiDAR tự train -> nhánh Radar -> hybrid fusion
   -> so sánh với classical -> occupancy học được -> temporal/flow -> cầu nối MATLAB risk
```

## 3. Bảng tổng hợp theo nhánh (mini VAL, 81 mẫu)

| Nhánh | Official pretrained (contaminated) mAP / NDS | Của dự án (mini TRAIN) mAP / NDS | Ghi chú |
|---|---|---|---|
| LiDAR-only | 0.543 / 0.563 | **0.210 / 0.232** | tự train từ đầu 15 epoch; val còn tăng khi dừng (chưa hội tụ) |
| Camera + LiDAR | 0.570 / 0.576 | **0.192 / 0.207** | thấp hơn LiDAR-only tự train: nhánh camera overfit 323 mẫu |
| Camera + Radar (CRN R18) | 0.433 / 0.476 | chưa làm (optional) | audit dữ liệu radar PASS; pretrained PASS |
| Hybrid late fusion CL x CR | 0.574 / 0.578 | 0.436 / 0.415 (CL tự train x CRN) | không hơn Camera+LiDAR đứng riêng trong sai số ±0.003 |

Số official chạy lại trong môi trường đóng băng lệch tới 0.003 so với lần đầu (nhiễu GPU): 0.545 / 0.566 và 0.572 / 0.576.

## 4. Kết quả từng giai đoạn (tóm tắt, chi tiết ở README của từng thư mục)

| Giai đoạn | Kết quả chính | Tài liệu |
|---|---|---|
| Đóng băng môi trường, pretrained, export ego, MATLAB import | PASS; tái lập trong sai số ±0.003 | `frozen/`, `exports/L3E` |
| Visualization dữ liệu thật | 81/81 mẫu: 6 camera, box 3D, LiDAR BEV, GT so với dự đoán | `notebooks/bev-real-viz/out/viz` |
| Stage A, B (tự train) | chuỗi TRAIN → CHECKPOINT → RELOAD → INFERENCE → EVAL → EXPORT → MATLAB PASS; một patch nguồn duy nhất (`np.long`) trên đường train | `models/lidar_only`, `models/camera_lidar` |
| Stage C Camera+Radar | audit radar: 5 radar, 404 keyframe mỗi loại, 0 file thiếu; CRN R18 pretrained chạy trên mini | `models/camera_radar` |
| Stage D hybrid | Hungarian trong BEV, Unified Object List; +0.004 mAP nằm trong nhiễu; đổi precision lấy recall | `fusion/README.md` |
| Stage E classical vs learned | classical (code Level 1, không chỉnh ngưỡng; chạy bằng toolbox thật): P 0.43, R 0.50, F1 0.46 | `stage_e/README.md` |
| Stage F occupancy | mIoU 0.549; IoU vùng chiếm 0.423 (quy tắc tương thích nhãn 0.384; classical 0.289) | `models/occupancy` |
| Stage G temporal / flow | occupancy mIoU 0.569 (1 frame 0.552); **flow học được không dùng được** | `models/temporal_flow` |
| Stage H risk bridge | risk gần oracle hơn khi perception tốt hơn; flow suy ra từ detection tốt hơn flow học được | `stage_h/README.md` |

## 5. Phát hiện chính

1. **Learned so với classical:** trên dữ liệu thật, pipeline classical của Level 1 (đặt nguyên, ngưỡng viết cho cảnh Unreal) đạt F1 0.46, khá với xe (recall 0.63) và yếu với người (0.18). Các model learned **pretrained** đạt F1 0.76–0.90 nhưng bị contaminated, nên không phải so sánh công bằng. So với model **tự train** (không contaminated) kết quả đảo chiều theo ngưỡng (F1 0.26–0.32 ở score 0.5, khoảng 0.60 ở score 0.3): chưa kết luận được trên 81 mẫu.
2. **Thêm camera vào model tự train không giúp** (0.192 so với 0.210): 323 mẫu quá ít cho nhánh ảnh. Fusion của model official cho +0.03 mAP, nhưng đó là hiệu ứng của huấn luyện trên trainval.
3. **Hybrid late fusion không có lợi rõ về AP/NDS**; nó chủ yếu đổi precision lấy recall và làm tâm box lệch nhẹ (mATE 0.439 so với 0.411). Với nhánh Camera+LiDAR yếu, box hợp nhất thừa hưởng hướng và vận tốc yếu nên NDS còn thấp hơn CRN đứng riêng (0.415 so với 0.476).
4. **Occupancy học được** tốt hơn quy tắc tương thích nhãn +0.039 IoU và grid classical +0.13, nhưng nhãn `static` là pseudo-GT suy từ LiDAR và model học đúng định nghĩa nhãn đó; radar chỉ cộng thêm +0.013 và radar-only gần như vô dụng (0.098). Object trong occupancy yếu (IoU 0.196 so với 0.475–0.587 của footprint từ detection).
5. **Temporal:** thêm frame quá khứ cải thiện occupancy (+0.017 mIoU) và bù chuyển động ego là bắt buộc (không bù thì tệ hơn cả 1 frame). Flow học được: EPE 3.52 m/s so với zero-flow 3.79, gây flow giả 1.7 m/s ở vật tĩnh, làm dự báo tương lai xấu đi.
6. **Flow suy ra từ vận tốc detection** dùng được (EPE 1.26–1.74 m/s, góc trung vị 4–5°, flow giả ≈ 0) nhưng số đo đến từ model official (contaminated) và chỉ phủ 62–74% ô chuyển động; với detector tự train thì không hơn zero-flow.
7. **Risk (Level 1 trên dữ liệu thật):** điểm oracle tương quan 0.85 với khoảng cách tiếp cận gần nhất (kiểm tra công thức hợp lý). Trên 1210 vật có oracle ≥ 0.1: tương quan hạng với oracle 0.94 (occupancy học + flow detection), 0.92 (không flow), 0.86 (classical), 0.74 (flow học được). Lợi ích của flow chỉ 19.9% (dưới ngưỡng 25% của dự án) vì ego chạy ~5 m/s nên tốc độ tiến lại gần bị chi phối bởi chuyển động ego.

## 6. Thời gian chạy (đo ở phần cứng khác nhau, chỉ để tham khảo)

| Thành phần | Số đo | Điều kiện |
|---|---|---|
| BEVFusion LiDAR-only (official ckpt) | 0.30 s / iteration | Kaggle T4, batch 1, gồm nạp dữ liệu |
| BEVFusion Camera+LiDAR (official ckpt) | 0.52 s / iteration | như trên |
| U-Net occupancy (Stage F) / temporal (Stage G) | 3.75 ms / 3.8 ms mỗi frame | T4, 1.9 M tham số, bộ nhớ đỉnh ≈ 1.1 GB |
| Classical LiDAR (ROI, ground, occupancy, cluster) | 0.189 s / frame | MATLAB, CPU cục bộ, toolbox thật |
| Classical radar rasterise | 0.057 s / frame | MATLAB, CPU cục bộ |
| `computeRiskFields` | 3–9 ms / frame | MATLAB, CPU cục bộ |
| Huấn luyện Stage A / B | 0.43 s / 0.84 s mỗi iteration; bộ nhớ đỉnh 2.0 GB / 4.8 GB | T4, batch 1 + tích luỹ 4, AMP |

Chưa đo: latency của CRN; đo lại tất cả nhánh trên cùng một phần cứng (còn trong `NEXT_ACTIONS.md`).

## 7. Những điều KHÔNG được tuyên bố

- Không tuyên bố kết quả mini là benchmark nuScenes hay so với số trong bài báo.
- Không dùng điểm official trên mini làm bằng chứng khả năng tổng quát hoá.
- Không tuyên bố risk là xác suất va chạm hoặc đã được kiểm chứng: risk là điểm không hiệu chuẩn và không có GT risk trên mini.
- Không tuyên bố flow học được hoạt động; không tuyên bố đã có `our_camera_radar.pth`.
- Không tuyên bố occupancy `static` là GT thật (pseudo-GT từ LiDAR); chỉ số occupancy không so được với Occ3D / SurroundOcc / TPVFormer.
- Không tuyên bố classical "kém" tuyệt đối: ngưỡng của nó thiết kế cho cảnh mô phỏng và không được chỉnh lại.

## 8. Việc chưa làm và đề xuất

- Own Camera+Radar training (`our_camera_radar.pth`): khả thi trên T4 (CRN R18, ResNet-18 ImageNet), cần driver Lightning riêng; đã đặt là optional.
- Flow học lại từ chuỗi **sweep** (0.05–0.1 s) thay vì keyframe cách 0.5 s, kèm lớp tương quan chuyển động; chưa thử.
- Train lâu hơn / tối ưu Stage A, B: chỉ sau khi có bằng chứng cần thiết (theo quyết định của người dùng).
- Đo latency thống nhất trên một phần cứng; robustness của model learned với LiDAR thưa (mới đo cho classical).

## 9. Câu hỏi phản biện dự kiến và câu trả lời trung thực

- *"Vì sao Camera+LiDAR của mình kém LiDAR-only?"* — 323 mẫu; loss train giảm (1.10) còn VAL không cải thiện; nhánh camera overfit.
- *"Model official đạt 0.57, sao của mình 0.19?"* — official train trên trainval (contaminated trên mini) và trên khoảng 28 nghìn mẫu; của mình train 323 mẫu; hai số không cùng thang.
- *"Flow học được đâu?"* — không dùng được; dùng flow từ detection; nguyên nhân giả thuyết (chưa kiểm chứng): ít dữ liệu, keyframe cách 0.5 s.
- *"Risk có đúng không?"* — chưa kiểm chứng; chỉ đo độ nhạy của điểm risk theo chất lượng perception.

## 10. Tái lập

Xem `README.md` (lệnh chạy lại từ workspace) và `TOOLING.md` (Kaggle). Số liệu Stage E/F/G/H tái lập được bằng các script `evaluate_*.py` từ artifact có sẵn; checkpoint có manifest `models/CHECKPOINTS.sha256`.
