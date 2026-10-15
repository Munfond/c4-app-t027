# Chat với agent và kiểm tra cấu hình LiDAR

Trang `http://localhost:3000/agent` có trong menu **Sensor Agent**.
Nhập prompt, đặt mức giảm occupied IoU tuyệt đối cho phép và số frame mỗi cấu hình.
Nút **Gửi & chạy thí nghiệm** gọi agent thật, tạo study và enqueue trial baseline.
Worker thực hiện CARLA/capture/inference rồi tự enqueue cấu hình kế tiếp; đóng
trang không dừng worker. Dừng bằng nút **Dừng study**.

Mỗi prompt tạo một study độc lập, không mang ngữ cảnh từ study trước. Nếu muốn
cảnh cao tốc, mưa hoặc sương mù, nêu lại trong prompt. Ngưỡng IoU và số frame
trên form được ưu tiên hơn giá trị mặc định mà LLM đề xuất.

## Chạy trên máy Windows + WSL hiện tại

CARLA phải chạy trước. Tại thư mục repo, mở hai terminal PowerShell:

```powershell
<VENV>\Scripts\python.exe -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

```powershell
<VENV>\Scripts\python.exe -m scripts.experiment_worker
```

Chỉ mở một worker điều khiển CARLA. Backend và worker dùng chung `.env`:
`EXPERIMENT_ROOT=<CARLA_ROOT>/runs/sensor-chat`. API key/model cấu hình ở backend,
không đưa key vào frontend. Có thể thêm `CARLA_FOLLOW_EGO=true` để CARLA bám theo
xe và `CARLA_REALTIME_CAPTURE=true` để điều tiết theo thời gian thực.

Frontend chạy trong WSL với Node 22. Phiên kiểm tra dùng runtime portable
`~/.local/share/p027-node/node-v22.16.0-linux-x64/bin` (checksum đã xác minh).
Trong terminal WSL tại `frontend`, thêm runtime đó vào PATH nếu chưa có Node.
Đặt `API_INTERNAL_URL=http://<địa-chỉ-Windows-từ-default-gateway-WSL>:8000`,
rồi chạy `node node_modules/next/dist/bin/next dev --hostname 0.0.0.0 --port 3000`.
Địa chỉ gateway có thể thay đổi khi khởi động WSL; đọc bằng `ip route`.
Nếu frontend/backend cùng hệ điều hành thì không cần đặt API_INTERNAL_URL,
mặc định là `http://127.0.0.1:8000`.

## Kết quả trên giao diện

- Tiến độ từng profile và lỗi CARLA/inference nếu có.
- Bảng IoU, chênh lệch IoU, MB/s payload LiDAR, giảm dữ liệu và p95 model latency.
- Chỉ đánh dấu đạt nếu trial thành công, reference khớp baseline và giảm IoU
  nằm trong ngưỡng. Reference không khớp được hiển thị là không so sánh được.
- Camera RGB và output occupancy cùng frame; tải input NPZ, geometry và báo cáo JSON.
- Agent đọc metric và giải thích sau khi hoàn tất; lỗi LLM không làm mất metric
  hay dữ liệu, có thể bấm nút giải thích để thử lại.
- Lịch sử được đọc từ backend để mở lại study sau khi tải lại trang.

## Giới hạn

Hiện chỉ có adapter CARLA cho checkpoint `occupancy_lidar`. Agent đề xuất tối đa
3 cấu hình ngoài baseline, tối đa 3 cảnh, mỗi trial tối đa 20 frame. Đây là so
sánh các ứng viên, chưa có vòng tự tìm ngưỡng liên tiếp hoặc chứng minh tối ưu
toàn cục. Mỗi study không dùng lại checkpoint khác nhau để so sánh.

Ngưỡng giảm IoU tương đối với baseline không đảm bảo baseline đạt chất lượng
tuyệt đối của ứng dụng. Nhãn đánh giá là occupancy proxy. Thời tiết mưa/sương mù
thay đổi RGB, chưa xác minh suy giảm vật lý LiDAR. Cần mở rộng mô hình cảm biến
và đánh giá nhiều scene/seed trước khi kết luận phù hợp môi trường xấu.
