import cv2
import sys
import time
import os

# Thêm thư mục gốc vào sys.path để import được src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.anonymizer import AnonymizerService

def main():
    if len(sys.argv) < 2:
        print("Sử dụng: python scripts/test_anonymize.py <đường_dẫn_ảnh_input>")
        return

    input_path = sys.argv[1]
    output_path = "anonymized_output.jpg"

    # 1. Đọc ảnh
    frame = cv2.imread(input_path)
    if frame is None:
        print(f"Lỗi: Không thể đọc ảnh từ {input_path}")
        return

    print(f"Đã đọc ảnh kích thước: {frame.shape}")

    # 2. Khởi tạo service (Lúc này YOLO sẽ tải weights)
    anonymizer = AnonymizerService()

    # 3. Chạy làm mờ và đo thời gian
    start_time = time.time()

    # Warmup chạy nháp (vì lần predict đầu tiên của PyTorch luôn chậm do khởi tạo GPU/CPU cache)
    _ = anonymizer.anonymize_frame(frame)

    # Chạy thật để đo FPS/Latency
    start_time = time.time()
    result_frame = anonymizer.anonymize_frame(frame)
    latency = (time.time() - start_time) * 1000  # ms

    print(f"[Thành công] Đã làm mờ ảnh. Độ trễ (Latency): {latency:.2f} ms")

    # 4. Lưu ảnh kết quả
    cv2.imwrite(output_path, result_frame)
    print(f"Đã lưu ảnh kết quả tại: {output_path}")

if __name__ == "__main__":
    main()
