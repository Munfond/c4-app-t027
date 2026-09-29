# Phase 11 — Evaluation & Sensor Ablation

Scenario `risk_heatmap_001`, 61 tick (6.1 s), seed 42, cùng log sensor/truth/vùng đánh giá cho 7 cấu hình. Số liệu sinh tự động từ kết quả đo; N/A = không hợp lệ.

| Cfg | Cấu hình | Occ IoU | Occ mIoU | Flow EPE (m/s) | Risk MAE (miss=0) | Risk cov | Track RMSE (m) | Latency (ms) | RTF | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|
| C | Camera only | 0.154 | 0.336 | 0.365 | 0.0749 | 0.962 | 0.415 | 267 | 0.375 | COMPLETED |
| L | LiDAR only | 0.966 | 0.231 | 0.216 | 0.0189 | 1 | 0.153 | 392 | 0.255 | COMPLETED |
| R | Radar only | 0.269 | 0 | 0.281 | 0.0312 | 1 | 0.187 | 300 | 0.334 | COMPLETED |
| CR | Camera + Radar | 0.323 | 0.478 | 0.288 | 0.0291 | 1 | 0.168 | 358 | 0.28 | COMPLETED |
| CL | Camera + LiDAR | 0.966 | 0.975 | 0.203 | 0.0186 | 1 | 0.155 | 494 | 0.202 | COMPLETED |
| LR | LiDAR + Radar | 0.96 | 0.217 | 0.312 | 0.0225 | 1 | 0.151 | 398 | 0.251 | COMPLETED |
| CLR | Camera + LiDAR + Radar | 0.96 | 0.962 | 0.298 | 0.0217 | 1 | 0.146 | 358 | 0.28 | COMPLETED |

## Nhận xét từ số liệu

- Occupancy IoU cao nhất: **CL** (0.966).
- Occupancy IoU thấp nhất: **C** (0.154).
- Flow EPE thấp nhất: **CL** (0.203 m/s); N/A ở: không.
- Risk MAE (vật không phát hiện tính 0) thấp nhất: **CL** (0.019).
- Bỏ camera khỏi CLR (→ LR): IoU 0.96 → 0.96, mIoU 0.962 → 0.217, flow EPE 0.298 → 0.312 m/s, risk MAE 0.0217 → 0.0225.
- Bỏ LiDAR khỏi CLR (→ CR): IoU 0.96 → 0.323, mIoU 0.962 → 0.478, flow EPE 0.298 → 0.288 m/s, risk MAE 0.0217 → 0.0291.
- Bỏ radar khỏi CLR (→ CL): IoU 0.96 → 0.966, mIoU 0.962 → 0.975, flow EPE 0.298 → 0.203 m/s, risk MAE 0.0217 → 0.0186.
- Hiệu năng (CPU, mọi nhánh chẩn đoán bật): latency trung bình 267–494 ms/tick, RTF 0.20–0.37 (RTF < 1: chậm hơn thời gian thực).

## Điều kiện kiểm tra

- attempted7: PASS
- failuresHaveReason: PASS
- sameScenarioSeedLogTicks: PASS
- naHasReason: PASS
- fullConfigurationHasOccupancyFlowRisk: PASS

## N/A và giới hạn

- Detection mAP: Không có detection evaluator (mAP): detection chỉ được đánh giá ở mức track (evaluateObjectTracks); camera dùng detector oracle.
- GPU: Pipeline chạy trên CPU (không có mạng học sâu); không đo GPU.
- Simulation per config: Simulation Unreal chạy một lần và ghi cả ba sensor; ablation xử lý cùng log nên thời gian simulation không phụ thuộc cấu hình.
- Simulation Unreal: N/A (dùng lại log của run 20260922_141941_risk_a05251ce).
- Ablation tắt đầu vào của sensor trên cùng log; camera dùng detector oracle (nhãn semantic), radar là mô hình radarDataGenerator có nhiễu mô phỏng, ego pose đúng; một kịch bản.
