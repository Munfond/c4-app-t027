# Bản đồ 3D trong Lab

Lab có chế độ **Bản đồ 3D** cho từng frame của nuScenes mini. API `/api/v1/lab/frames/{token}/environment` trả về tối đa 24.000 điểm LiDAR keyframe trong hệ tọa độ xe (`x` tiến, `y` trái, `z` lên), voxel hóa 0,25 m trong bán kính 65 m. Trình xem biến mỗi điểm thành một khối nhỏ, cho phép xoay, thu phóng và xem từ trên/cạnh. Các hộp vật cản của model pretrained đang chọn được vẽ trong cùng hệ tọa độ.

Màu **mặt thấp** lấy ngưỡng chiều cao từ phân vị 15% của các điểm trong bán kính 25 m. Màu **khối cao** là những điểm còn lại. Màu **trong hộp vật cản** lấy theo hình học của hộp 3D đã dự đoán. Đây là phân nhóm hình học của **các bề mặt LiDAR đã quan sát**, chưa phải semantic segmentation được đánh giá bằng nhãn 3D và cũng không dự đoán vùng bị che khuất. Kích thước khối vẽ chỉ để nhìn rõ bề mặt; nó không chứng minh một thể tích thật đã được lấp đầy.

## Đường nâng cấp model

Chưa nên fine-tune model ngay cho bản demo. Ứng viên NVIDIA đúng bài toán là [FB-OCC](https://github.com/NVlabs/FB-BEV): repo chính thức có checkpoint pretrained cho dự đoán occupancy 3D trên nuScenes, nhưng quy trình train/eval công bố dùng 8 GPU và cần dữ liệu/metadata theo cấu trúc riêng. Với VPS Windows CPU hiện tại, hướng khả thi là chạy pretrained offline trên máy GPU phù hợp, xuất cache voxel theo frame rồi mới đưa lên web; không chạy model trực tiếp khi giám khảo mở Lab. Cần thử trên vài frame mini trước và xác nhận phép chiếu, checkpoint, các lớp cùng license của weights.

**NVIDIA SegFormer** là model semantic segmentation **2D**: có thể gán màu cho các điểm LiDAR nhìn thấy qua ảnh camera, nhưng phải dùng calibration và ego pose của từng camera để chiếu nhãn; không thể gọi kết quả đó là dense 3D occupancy. Model occupancy 3D thực sự cần checkpoint, định nghĩa lớp, voxel grid và dữ liệu đánh giá phù hợp (ví dụ [Occ3D](https://github.com/Tsinghua-MARS-Lab/Occ3D)); các artifact occupancy hiện có trong repo là lưới BEV 2D, không đủ để suy ra một bản đồ 3D ngữ nghĩa.

Nếu thêm model về sau, chạy inference/precompute ngoài VPS CPU, lưu cache mỗi frame cùng `model_id`, phiên bản checkpoint và phạm vi dữ liệu. UI cần phân biệt “quan sát”, “nhãn model” và “vùng chưa biết”. Chỉ hiển thị chỉ số accuracy/mIoU sau khi có tập ground truth 3D độc lập và quy trình đánh giá tái lập được.
