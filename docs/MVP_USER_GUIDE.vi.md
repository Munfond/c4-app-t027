# Hướng dẫn đầy đủ MVP Perception Lab

## 1. Bắt đầu ở đâu?

Trên máy phục hồi hiện tại, mở `http://127.0.0.1:3111/lab`. Ba trang chính là **Lab**, **Compare**, **Benchmarks**. Nút **Hướng dẫn** ở header giải thích nhanh; nút **Agent** mở panel cạnh workspace. Trên màn hình hẹp, panel và workspace xếp dọc.

Luồng demo ngắn: **Cảm biến → Kết quả mô hình → Compare → Benchmarks → Agent / CARLA → capture PPO 20 → Reference / trace**. Dùng bản ghi đã hoàn tất trước; không cần khởi động simulator để phát lại.

## 2. Cảm biến: hiểu cảnh trước khi đọc model

1. Mở **Thiết lập**, chọn scene và frame. MVP nuScenes mini-val có scene-0103 (40 frame), scene-0916 (41 frame).
2. Chọn **Camera 360°**: sáu góc nhìn trước/sau dùng chung frame. Bấm một camera để xem lớn. Ảnh phải qua bộ lọc riêng tư; bộ lọc tự động vẫn có thể bỏ sót khuôn mặt/biển số.
3. Chọn **LiDAR + Radar**: hai lớp chung hệ tọa độ ego. Bỏ tick từng sensor để ẩn, bật lại để đối chiếu. Tick này chỉ thay hiển thị, không chạy lại model hoặc kiểm chứng ablation.
4. LiDAR cho vị trí/hình dạng bề mặt. Radar hiển thị điểm đo và tốc độ; mở **Số đo & bộ lọc** để xem chi tiết. Radar không được gán lớp người/xe bằng cách nhìn màu.
5. **Màu LiDAR → Phân đoạn** hiển thị màu ngữ nghĩa khi frame có output phù hợp. Đọc badge nguồn để phân biệt dự đoán và tham chiếu.
6. Kéo để xoay, cuộn để zoom. Đổi góc nhìn 3D / mặt đường / BEV. Dấu ego và vòng khoảng cách giúp đọc vị trí; vùng không có điểm không đồng nghĩa chắc chắn thông thoáng.

## 3. Timeline và playback

**Phát / Tạm dừng**, frame trước/sau, thanh tua, tốc độ và **Lặp** cùng điều khiển frame của workspace. nuScenes keyframe khoảng 0,5 giây; đây không phải video camera 30 FPS. Thời gian trên timeline là timestamp dữ liệu, không phải cam kết inference realtime.

Trong capture CARLA, Play phát lại camera + occupancy + reference đồng bộ. Số `1/20`, `20/20` là tiến độ phát lại; tiến độ `capture` khi chạy job là tiến độ thu dữ liệu. Hai loại tiến độ khác nhau. Tuỳ chọn rút ngắn khoảng trống chỉ đổi nhịp xem các frame có thật, không tạo frame bị thiếu. Mở hướng dẫn tạm dừng playback.

Nếu tải chậm, tạm dừng và xem một frame. Không đổi scene liên tục trong khi đang kiểm tra một chi tiết. Khi frame không có artifact, đọc lỗi và nguồn; không coi hình cũ là kết quả mới.

## 4. Kết quả mô hình

| Bài toán | Input / context | Output và cách đọc |
| --- | --- | --- |
| Detection3D | Sensor tương ứng model; cùng frame ego | Hộp vị trí, kích thước, hướng; hình xe/người dựng theo box là đại diện, không phải Seg3D |
| Seg3D | Point cloud theo frame | Lớp ngữ nghĩa trên từng điểm; SalsaNext transfer là dự đoán thử nghiệm, chưa kiểm định accuracy trên nuScenes |
| Occupancy | Grid đầu vào từ sensor / checkpoint tương ứng | BEV2D trống, nền tĩnh, vật thể; chưa là bản đồ voxel3D đầy đủ |
| Flow | Chuỗi frame theo cấu hình temporal | Chuyển động ước lượng; chất lượng còn hạn chế, không coi mũi tên là chuyển động đã xác nhận |
| Risk | Occupancy, motion và heuristic của cấu hình | Điểm rủi ro chưa hiệu chuẩn, không phải xác suất va chạm; không điều khiển xe |

Tên **LiDAR pretrained** chỉ xác định model/reference và sensor của bản xuất; không suy ra kiến trúc PointPillars nếu artifact chưa chứng minh. **BEVFusion** dùng Camera+LiDAR; **CRN** dùng Camera+Radar và có thể dùng làm baseline khác tổ hợp sensor. **Hợp nhất hậu xử lý** kết hợp output ở mức vật thể, không phải một checkpoint joint-fusion ba sensor mới.

MVP ưu tiên output pretrained để trực quan. Model của đội và các chỉ số nghiên cứu vẫn có trong Benchmarks. Model là `precomputed` khi UI ghi như vậy; thao tác xem frame không chạy inference nặng trên server.

## 5. Compare và Benchmarks

Trong **Compare**, chọn chung scene, frame, ngưỡng điểm rồi chọn model A/B. Hai BEV dùng chung góc nhìn. So vị trí/hình dạng và khoảng cách, không kết luận model tốt hơn chỉ vì có nhiều box hơn.

Trong **Benchmarks**, chọn nhóm Detection / Occupancy / Flow / Risk. Đọc phạm vi 81 frame mini-val, đơn vị, hướng tốt của metric và nguồn artifact. Không so trực tiếp IoU nuScenes với IoU CARLA vì nguồn nhãn, miền dữ liệu và valid mask khác nhau. Checkpoint official có thể đã thấy mini-val khi train; các con số này không phải benchmark độc lập công bằng. Flow còn yếu; Risk chưa hiệu chuẩn.

Một số chỉ số cần giải thích khi trình bày:

- **Occupied IoU**: mức chồng khớp vùng có vật/tĩnh giữa model và reference. Không phải tỷ lệ nhận ra từng người/xe.
- **Object IoU / object-cell recall**: chất lượng trên ô vật thể tham chiếu; CARLA hiện dùng footprint actor và vùng semantic LiDAR quan sát được. Recall trên ô không phải pedestrian detection recall.
- **mAP / NDS**: nhóm đánh giá detection 3D theo protocol của nguồn benchmark; không so ngang với IoU occupancy.
- **EPE / ADE / FDE**: sai số vector/chuyển động theo thời gian; phải xem đơn vị và horizon của artifact.
- **p95 latency**: 95% mẫu đo không vượt thời gian này. Đọc rõ đo model-only hay feature+model; số CPU không phải FPS toàn hệ thống hoặc chi phí GPU.

## 6. Dùng agent

Agent có hai nguồn: **nuScenes replay** và **CARLA**. Replay biến đổi dữ liệu ghi sẵn, không mô phỏng phần cứng ngoài đời. CARLA tạo capture bằng simulator và worker riêng.

### Chỉ lập cấu hình

Nhập yêu cầu rồi bấm **Chỉ lập cấu hình để tôi kiểm tra trước**. Ví dụ:

> Lập cấu hình CARLA Town01, trời quang, 2 xe, 0 người, 4 frame, seed 42, camera FOV 60°. Chỉ dùng occupancy_lidar và căn chỉnh intensity thử nghiệm. Chưa chạy.

Bot điền cấu hình nháp vào form. Đọc map/weather/frame/model/sensor trước khi bấm **Tạo thí nghiệm**. Lập cấu hình không tự tạo capture.

### Kiểm chứng cấu hình

**Gửi & kiểm chứng** gọi LLM để tạo study có baseline và các ứng viên trong miền schema. Ví dụ:

> So cấu hình LiDAR 600k với 300k và 150k điểm/giây trong Town01 trời quang, 2 xe, 0 người, 4 frame. Dùng căn chỉnh intensity thử nghiệm. IoU được giảm tối đa 0,02; kiểm tra cả chất lượng ô vật thể.

Worker chạy các trial tuần tự, đo metric và so với cùng reference. LLM không được tự thay số đo hoặc override lựa chọn của evaluator. Kết luận có thể là **giảm dữ liệu**, **giữ cấu hình gốc**, hoặc **chưa đủ bằng chứng**. Giảm điểm/byte không phải chứng minh giảm điện năng hoặc chi phí GPU.

**Kiểm chứng 2 mức LiDAR** là đường thủ công không dùng LLM; UI ghi rõ số capture/frame và các ngưỡng. Preset camera 60/90/110 chỉ điền góc nhìn, chưa tạo lượt chạy. FOV là góc nhìn, không phải điểm lấy nét; occupancy LiDAR không dùng ảnh camera hiện tại.

### Giải thích và review

Chọn study trong **Lượt đánh giá**. Mở trial để xem cấu hình, checkpoint, metric, trạng thái và lý do loại ứng viên. **Diễn giải** gọi LLM đọc evidence; số đo và lựa chọn Python vẫn là nguồn kiểm chứng. Tải evidence JSON để kiểm tra run/reference/report hash.

Engineer ghi tên, verdict và lý do đánh giá. Tên hiện tự khai báo, không phải hệ thống xác thực vai trò. Không tạo review giả để demo. Review không tự huấn luyện lại policy.

### Agent chưa làm được gì?

Agent không lái xe, không huấn luyện checkpoint mới theo một câu chat, không tự đổi model camera/radar trong vòng occupancy CARLA và không bảo đảm an toàn ngoài thực tế. Mưa/sương mù trong preview RGB chưa chứng minh suy giảm LiDAR/radar vật lý. ROS2, MultiDiscrete và weather-robustness là phần nghiên cứu chưa nghiệm thu.

## 7. RL và PPO: demo có bằng chứng

**RL = Reinforcement Learning (học tăng cường)**. **PPO = Proximal Policy Optimization**, thuật toán RL dùng để học policy chọn input LiDAR cho frame kế tiếp.

Nguồn native gồm 12 cấu hình vật lý, 48 capture và 960 outcome, chia train/validation/test theo route. PPO chạy 8.192 bước; checkpoint chọn bằng validation rồi giữ nguyên. Trong capture online, policy chỉ đọc raw LiDAR đang chọn và latency hiện tại; GT/reference chỉ dùng đánh giá sau capture. Đây là inference online, không cập nhật optimizer trong lúc chạy.

Mở bot→CARLA→**PPO trong CARLA**. Bảng 20 frame so đối chứng và PPO trên route 112 / seed 212, reference SHA khớp. Cả hai occupied IoU 78,93%, object IoU 30,60%; PPO giữ 32 kênh/600k ở 19 quyết định. Kết luận hiện tại **chưa cải thiện baseline**. Cả 12 sensor vẫn chạy; không gọi đây là tắt sensor hoặc tiết kiệm điện.

Mở PPO 20→Play→Reference→chọn actor. Khoảng cách/kích thước là metadata tham chiếu; viền trên camera là phép chiếu hình học, chưa xét che khuất và không phải detection ảnh. Tải trace để đọc action hiện tại và action áp dụng frame sau.

## 8. Khi có lỗi hoặc chưa có kết quả

| Trạng thái | Ý nghĩa / hành động |
| --- | --- |
| queued | Chưa có worker xử lý; không phải đang có kết quả mới |
| running · capture | Simulator đang thu frame; metric xuất hiện sau inference/evaluation |
| succeeded / completed | Lượt hoàn tất; chọn output rồi Play/Reference |
| failed / Signal11 | CARLA native đã crash; mở chi tiết kỹ sư, giữ lượt lỗi. Bấm **Xem bản ghi đã hoàn tất** để quay về kết quả có thật |
| GPU chưa sẵn sàng | Kiểm tra `nvidia-smi`; không ép launch hoặc reset driver tự động |
| RAM chưa đủ | Cần 10 GiB khả dụng trước launch, không phải 10 GiB tổng RAM; không hạ guard để né lỗi |
| Camera503 | Thiếu ảnh processed/anonymizer; không bật trả raw để né bộ lọc |
| LLM chưa bật / HTTP401,402,429 | Kiểm tra provider,key,model và tài khoản/giới hạn; không lặp request tự động |
| Production Experiments503 | API thí nghiệm chưa được opt-in trên server; localkey không tự trở thành key Render |

Preset đã nghiệm thu trên máy hiện tại là Town01/clear/2 xe/0 người. Town03 đang crash ở Vulkan graphics pipeline khi tải map; workaround asyncPSO đã thử không hiệu quả và đã bỏ. Không tự đổi map của yêu cầu thất bại, không dùng nó làm evidence thành công.

## 9. Khởi động local trên máy hiện tại

Hai terminal riêng, tại `/home/lam/WorkSpace/vinuni-buildphase/P-027-recovery-20261013`:

```bash
bash scripts/run_local_mvp.sh backend
```

```bash
bash scripts/run_local_mvp.sh frontend
```

Lab ở `http://127.0.0.1:3111/lab`; health ở `http://127.0.0.1:8000/health`. Worker chỉ cần cho lượt mới:

```bash
bash scripts/run_local_mvp.sh worker
```

Không bật worker cạnh capture standalone hoặc worker khác. Trước CARLA: GPU khỏe, RAM khả dụng>=10 GiB. `Ctrl+C` dừng tiến trình trong terminal. Khi cập nhật frontend: build thành công, dừng frontend cũ rồi mở release mới; không build vào bản đang phục vụ. Sau reboot cần mount lại dữ liệu Windows read-only nếu raw nuScenes nằm ở đó. Không reset/xóa backup.

## 10. Setup trên máy khác

CodeGit không chứa runtime CARLA, full nuScenes, local `.env` hoặc mọi artifact nghiên cứu. Chuẩn bị Python 3.12, Node 22, dataset theo điều khoản nuScenes và các asset đã kiểm tra theo [hướng dẫn chuyển assets](MVP_PORTABLE_ASSETS.vi.md).

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Điền đường dẫn LAB_DATA_ROOT,NUSC_ROOT,CAMERA_CACHE_DIR cho máy này.
.venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Ở terminal khác:

```bash
cd frontend
npm ci
npm run build -- --webpack
npm run start -- --hostname 127.0.0.1 --port 3111
```

Runtime inference/training là phụ thuộc riêng; web readers không cần CUDA. Để chạy model, CARLA hoặc train PPO thật, dùng các hướng dẫn research/runtime tương ứng; không tự coi việc cài requirements web là đã cài simulator và model runtime.

## 11. OpenRouter

Backend hỗ trợ hai provider tách biệt. Với OpenRouter, đặt trong `.env` local hoặc secret/environment của backendhosting:

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<key-cua-ban>
EXPERIMENT_AGENT_ENABLED=true
EXPERIMENT_AGENT_MODEL=openai/gpt-4o-mini
MODEL_NAME=openai/gpt-4o-mini
```

Restart backend sau khi đổi env. Không đặt key trong biến`NEXT_PUBLIC_*`, frontend, notebook, log hoặc commit. Key OpenRouter chỉ gửi tới`https://openrouter.ai/api/v1`; không fallback sang key OpenAI khi thiếu key của provider đã chọn. LangChain helper là phần optional; agent MVP gọi HTTP trực tiếp.

Lời yêu cầu, tool schema và metadata/evidence cần giải thích có thể gửi tới provider. Luồng này không gửi ảnh camera, point cloud hay file trọng số. Chỉ thao tác **Gửi/Diễn giải** mới gọi LLM; đọc preview/evidence không gọi. Kết nối và tool-call tổng hợp công khai (cộng 2+3) đã được kiểm tra thật; kiểm tra plan/study/summary với payload dự án vẫn cần xác nhận phạm vi dữ liệu gửi ra ngoài.

Tham khảo [OpenRouter Quickstart](https://openrouter.ai/docs/quickstart). Key local không tự cập nhật env Render hoặc tài khoản của thành viên khác.

## 12. Deploy và runner

Vercel phục vụ frontend; `API_INTERNAL_URL` phải trỏ backend Render tương ứng. Các env được đọc khi build cần redeploy frontend sau khi đổi. Backend phải có DB/catalog, perception/cache và processedmedia phù hợp; chỉ có code không đủ để hiện mọi dữ liệu.

Render free không phải máy CARLA GPU. Rawdataset, inferenceworker và simulator cần runtime riêng; gói trong `deploy/artifacts/native-ppo-demo.zip` mang cặp đối chứng/PPO 20 frame đã kiểm định. Docker tự cài gói; `/api/v1/evidence/*` chỉ cho đọc, không tạo job hoặc gọi LLM. Gói perception mới cũng chứa Seg3D cho đủ 81 frame. API thí nghiệmproduction mặc định opt-in; chỉ bật với storage writable, giới hạn truy cập/quota và môi trường chạy phù hợp. Không hứa liveCARLA trên server không có simulator.

**Runner GitHub chỉ chạy CI**, không tự deploybackend, không thay GPUworker CARLA. Nếu runneroffline, vẫn làm việc/test local; các check GitHub sẽ chờ. Merge phải tuân theo rule thực tế của repo, không bypass required check. Push/merge không tự chuyển `.env` hay local asset chưa được đóng gói tới cloud.

Xem [nghiệm thu từng tính năng](MVP_ACCEPTANCE_20261014.vi.md), [luồng nativePPO](NATIVE_ONLINE_SELECTOR.vi.md), [kiến trúc](../ARCHITECTURE.md) và [deploy](DEPLOYMENT.vi.md). Những mục chưa nghiệm thu được ghi rõ, không suy ra “mọi tính năng đã xong” từ build xanh.


## 13. Demo trong 90 giây

1. Lab → Cảm biến: bật/tắt LiDAR và Radar, đổi BEV/3D rồi bấm Play. Giải thích đây là điểm đo.
2. Camera 360°: xem cùng frame; chuyển Kết quả mô hình → Seg3D để thấy lớp ngữ nghĩa. Đọc badge dự đoán/tham chiếu.
3. Compare: đổi hai model trên cùng frame; Benchmarks: đọc Occupancy và cảnh báo phạm vi đánh giá.
4. Mở Agent → CARLA → PPO trong CARLA → Xem PPO 20 frame → Play → Reference. Nói rõ đây là bản ghi inference, PPO giữ baseline và chưa chứng minh cải thiện.
5. Local: chọn study `f5961716` trong Lượt đánh giá. Baseline occupied IoU 83,2%; 300k là 65,2%, 150k là 42,9%. Reference giống nhau, nên giữ cấu hình gốc. Đây là kiểm chứng thủ công 4 frame/cấu hình, không phải test PPO 20 frame.

Các bước xem bản ghi không cần runner CI, simulator hoặc token LLM. Không tạo thí nghiệm mới chỉ để lấp thời gian demo.


### Kiểm tra hội thoại ngày14/10

Agent OpenRouter đã được kiểm tra thật ở luồng đề xuất, tạo study và tóm tắt số đo có sẵn. Môi trường (map/thời tiết/seed/camera) và cấu hình LiDAR ứng viên được tách riêng: cùng môi trường chỉ có một baseline, các cấu hình300k/150k nằm trong profiles. Nếu đề xuất bị trùng môi trường, agent có tối đa một lượt sửa; vẫn sai thì báo lỗi để dùng form, không tạo job từ đề xuất sai. Plan không tự chạy; worker mới thực hiện capture. Bản cloud chỉ đọc không tự bật hội thoại chỉ vì máy local đã có key.
