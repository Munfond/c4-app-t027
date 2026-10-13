# CARLA native và căn chỉnh đầu vào thử nghiệm

Ngày 13/10/2026, server CARLA 0.9.16 phục hồi đã tạo capture thật trên Town01. Camera RGB 640×360, LiDAR, reference và checkpoint occupancy chạy được. Đây là kiểm chứng tích hợp và chẩn đoán có giới hạn, chưa chứng minh an toàn ADAS hoặc online RL.

## Những gì đã chạy

- FOV 60°, 90°, 110°: mỗi cấu hình 2 frame, sensor ghi đúng FOV; ảnh giải mã được. Occupancy LiDAR không dùng camera nên không lấy metric occupancy để kết luận FOV tốt hơn.
- Capture gần ego: 4 frame, 2 xe có footprint trong vùng đánh giá. Reference có 106 object-cell; đầu vào gốc cho object-cell recall 0%. UI có lớp Reference để thấy rõ bỏ sót.
- Một người đi bộ: smoke 4 frame thành công; không suy diễn thành pedestrian detection benchmark.
- Sương mù và mưa: mỗi môi trường 2 frame. RGB thay đổi nhưng đầu vào LiDAR và metric của hai lần này giống nhau. CARLA WeatherParameters chưa là mô hình suy hao sensor vật lý; không gọi đây là chứng minh độ bền trước mưa/sương mù.
- Các lần Town03 / traffic 8 xe + 8 người gặp SIG11. Giữ trạng thái failed và log; chưa xác định nguyên nhân. Không đưa clip thiếu vào training.

Preset UI chọn Town01, 2 xe, 0 người, 4 frame và spawn gần ego. Guard 10 GiB RAM khả dụng vẫn áp dụng trước khi khởi động simulator. Capture chạy từng job; tiến độ chỉ tăng khi đã ghi cặp camera/LiDAR.

## Vì sao cần kiểm tra intensity

Mức trung bình kênh intensity trên ô có điểm: nuScenes **training split** khoảng 0,05962; 4 frame CARLA calibration khoảng 0,91914. Adapter thử nghiệm dùng một gain cố định 0,0648643347, chỉ nhân kênh intensity. Gain được chốt trước khi xem kết quả hai route mới, không fit từ nhãn và không thay checkpoint.

| Capture đánh giá | Đầu vào | Occupied IoU | Object IoU | Object-cell recall |
| --- | --- | ---: | ---: | ---: |
| Town01 route 17, seed 73 · 4 frame | Gốc | 25,8% | 0% | 0% |
| Cùng capture | Căn chỉnh thử nghiệm | 76,6% | 16,9% | 85,1% |
| Town01 route 31, seed 97 · 4 frame | Gốc | 33,1% | 0% | 0% |
| Cùng capture | Căn chỉnh thử nghiệm | 80,6% | 55,6% | 88,1% |
| Fog / Rain · mỗi capture 2 frame | Gốc | 38,2% | 0% | 0% |
| Cùng capture | Căn chỉnh thử nghiệm | 82,5% | 45,5% | 92,6% |

**Recall cao không đồng nghĩa segmentation hoàn thiện.** Object IoU 16,9% ở route 17 cho thấy vẫn có nhiều ô dự đoán sai. Chỉ 8 frame đánh giá cùng một map; cần map/route/sensor held-out lớn hơn. Reference gồm ô LiDAR quan sát được, proxy static theo chiều cao và footprint actor; không là semantic ground truth toàn cảnh.

Đầu vào gốc là mặc định. Trong form CARLA có lựa chọn căn chỉnh thử nghiệm, chỉ bật khi manifest và checkpoint khớp SHA. Job đóng băng hash lúc enqueue, kiểm tra lại trước capture và trước inference. Không sửa raw NPZ, nhãn, checkpoint hoặc report PPO nuScenes. Dữ liệu native này **chưa được admit cho training RL**.

## Đối chiếu và chạy lại

Trong `/lab`, mở bot → công cụ thí nghiệm. Danh sách có các capture FOV/mưa/sương mù đã chạy; chọn model hoặc Reference, Play/Pause, kéo thanh frame. Bản căn chỉnh là một job khác tái sử dụng đúng capture camera/reference, có adapter SHA riêng.

Nguồn evidence nằm ở `eval/recovery-mvp-2026-10-13`:

- `native-fov-captures.json`: FOV thực tế, ảnh, trạng thái smoke.
- `native-pilot-coverage.json`: coverage và các job failed.
- `native-input-domain-diagnostic.json`: thống kê train/calibration.
- `native-intensity-preregistered-plan.json` + `.sha256`: kế hoạch/gain trước evaluation.
- `native-intensity-heldout-evaluation.json` + `.sha256`: confusion matrix và raw SHA trên hai route mới.
- `native-input-{fog,rain}-diagnostic.json` + `.sha256`: kiểm tra bổ sung, không refit.
- `native-input-adapter.json` + `.sha256`: manifest experimental được runtime sử dụng; không là trọng số train mới.
- `native-published-preview.json`: capture/job preview và nguồn raw.

Tái đánh giá capture hoàn chỉnh có sẵn, không khởi động CARLA và không fit lại:

```bash
.venv-recovery312/bin/python -m scripts.evaluate_native_input_adapter \
  data/experiments/<capture-id>/capture \
  --output data/adapter-evaluation-new.json
```

Không ghi đè evidence cũ. Bước tiếp theo là thiết kế split native theo route/map, coverage và reference audit; sau đó thu bộ profile sensor có đo chất lượng/latency. Bộ 12–24 profile và MultiDiscrete trong kế hoạch gốc vẫn chưa hoàn tất. PPO offline 3 mức giữ điểm hiện có là kết quả riêng, không dùng các con số CARLA này để tô lại báo cáo PPO.
